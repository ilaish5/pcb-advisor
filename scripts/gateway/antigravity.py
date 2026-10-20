"""Antigravity CLI (agy): spawn `agy -p`, take stdout.

Same shape as claude_code.py, but the prompt travels as one stream-json line
on stdin (no command-line length limit) and the answer is the `result` event.

Differences from Claude Code:
  - No per-tool allow/deny flags.  Permissions are all-or-nothing via
    --dangerously-skip-permissions or --mode accept-edits.
  - An optional `effort` key (low | medium | high | xhigh | max) maps to
    --effort, which has no Claude Code equivalent.
"""
import json
import re
import shutil
import subprocess
import time

import oscompat

from . import events, stream
from .base import Provider, Request, Result


_AGY_MODELS_CACHE = None
_OFFERED = ("gemini-3.1-pro-high", "gemini-3.8-flash-high")

# what agy accepts for --effort
EFFORTS = ("low", "medium", "high", "xhigh", "max")

class AntigravityProvider(Provider):
    id = "antigravity"
    title = "Antigravity CLI"
    status = "implemented"
    workspace_access = True
    doc = "Runs the `agy` binary on PATH. Auth is handled by the CLI itself."

    def available(self):
        if not self.config.get("enabled", True):
            return False, "antigravity is disabled in config"
        cmd = self.config.get("command", "agy")
        if not shutil.which(cmd):
            return False, f"`{cmd}` is not on PATH"
        effort = self.config.get("effort")
        if effort is not None and effort not in EFFORTS:
            return False, f"effort '{effort}' is not one of {', '.join(EFFORTS)}"
        return True, ""

    def describe(self):
        global _AGY_MODELS_CACHE
        d = super().describe()
        if _AGY_MODELS_CACHE is None:
            cmd = self.config.get("command", "agy")
            if shutil.which(cmd):
                try:
                    # describe() runs while the settings page loads, so a CLI that
                    # hangs here must not hang the server with it
                    out = subprocess.check_output([oscompat.resolve(cmd), "models"],
                                                  stderr=subprocess.DEVNULL,
                                                  **oscompat.TEXT, timeout=10)
                    models = []
                    for line in out.strip().split("\n"):
                        if line.strip():
                            parts = line.split(maxsplit=1)
                            if len(parts) >= 1:
                                models.append({"id": parts[0], "name": parts[1] if len(parts)>1 else parts[0]})
                    _AGY_MODELS_CACHE = models
                except Exception:
                    _AGY_MODELS_CACHE = []
            else:
                _AGY_MODELS_CACHE = []
        # the settings page offers Pro and Flash at high effort; the rest of the
        # list is for the CLI, not for a student choosing an engine
        d["models"] = [m for m in _AGY_MODELS_CACHE
                       if re.fullmatch(r"gemini-[\d.]+-(pro|flash)-high", m["id"])
                       and m["id"] in _OFFERED] or _AGY_MODELS_CACHE
        return d

    def _argv(self, request, model):
        """The exact command line. The prompt is NOT in it: it goes on stdin.

        The protocol flags are fixed (`-p= --input-format stream-json
        --output-format stream-json`). A config `args` list is treated as extra
        flags: the legacy print-mode pieces (`-p`, a bare `-`, `--output-format X`,
        `--input-format X`, `-p=`) are dropped from it, everything else
        (e.g. `--dangerously-skip-permissions`, `--mode accept-edits`) is kept.
        """
        extra = list(self.config.get("args") or ["--dangerously-skip-permissions"])
        kept, skip = [], False
        for a in extra:
            if skip:
                skip = False
            elif a in ("--output-format", "--input-format"):
                skip = True
            elif a in ("-p", "-", "-p="):
                pass
            else:
                kept.append(a)
        argv = [oscompat.resolve(self.config.get("command", "agy")),
                "-p=", "--input-format", "stream-json",
                "--output-format", "stream-json", *kept]
        dropped = []
        effort = self.config.get("effort")
        if model:
            # the model name already carries the level (gemini-3.8-flash-high);
            # agy refuses --model together with --effort
            argv += ["--model", model]
            if effort:
                dropped.append("effort")
        elif effort:
            argv += ["--effort", effort]
        for d in request.options.get("add_dirs") or []:
            argv += ["--add-dir", str(d)]
        return argv, dropped

    @staticmethod
    def _parse(stdout):
        """(response, error, denied) from stream-json stdout. Non-JSON lines are noise.
        denied is the list of display names agy auto-denied in headless mode."""
        found = None
        for line in (stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and ev.get("event") == "result":
                found = ev
        if found is None:
            return None, "no result event in agy output", []
        res = found.get("result")
        res = res if isinstance(res, dict) else {}
        status = res.get("status") or found.get("status")
        err = res.get("error") or found.get("error")
        if err:
            return None, str(err if isinstance(err, str) else json.dumps(err))[:400], []
        if status and str(status).upper() != "SUCCESS":
            return None, f"agy status {status}", []
        resp = res.get("response")
        if resp is None:
            resp = found.get("response")
        if resp is None:
            return None, "result event has no response", []
        denied = []
        for d in res.get("denied_actions") or found.get("denied_actions") or []:
            name = (d.get("display_name") or d.get("action")) if isinstance(d, dict) else d
            if name:
                denied.append(str(name))
        if not str(resp).strip():
            if denied:
                return None, (f"agy denied {', '.join(denied)} in headless mode; the "
                              "answer is empty. Enable the tool with an allow-rule or "
                              "--dangerously-skip-permissions (see docs/ENGINES.md)"), denied
            return None, "agy returned an empty answer", []
        return str(resp), "", denied

    @staticmethod
    def _usage(stdout):
        """Token counts from the result event, when agy reports them (the field names vary between versions)."""
        names = {"input_tokens": ("input_tokens", "prompt_tokens", "inputTokens", "promptTokenCount"),
                 "output_tokens": ("output_tokens", "completion_tokens", "outputTokens", "candidatesTokenCount")}
        for line in reversed((stdout or "").splitlines()):
            line = line.strip()
            if not line.startswith("{") or '"result"' not in line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            res = ev.get("result") if isinstance(ev.get("result"), dict) else {}
            raw = next((u for u in (ev.get("usage"), res.get("usage"), ev.get("stats"), res.get("stats"),
                                    res.get("usageMetadata")) if isinstance(u, dict)), {})
            return {k: raw[n] for k, ns in names.items() for n in ns if isinstance(raw.get(n), int)}
        return {}

    def complete(self, request: Request) -> Result:
        ok, why = self.available()
        if not ok:
            return Result(provider=self.id, error=why)

        cmd = self.config.get("command", "agy")
        model = request.model or self.config.get("model") or ""
        argv, dropped = self._argv(request, model)
        meta = {"dropped": dropped} if dropped else {}
        line = json.dumps({"event": "user",
                           "message": {"role": "user", "content": request.prompt}},
                          ensure_ascii=False) + "\n"

        lines, last_text = [], [-1e9]
        on_event = request.options.get("on_event")

        def on_line(raw):
            lines.append(raw)
            # agy's step events are not documented; an assistant event is the one thing we can name
            if on_event and raw.startswith("{") and '"assistant"' in raw and \
                    time.monotonic() - last_text[0] >= 2.0:
                last_text[0] = time.monotonic()
                try:
                    on_event({"kind": "text", "label": "Writing the answer", "ts": time.time()})
                except Exception:
                    pass

        try:
            rc, err, ended = stream.run(
                argv, stdin_text=line, cwd=request.options.get("cwd") or None,
                env=oscompat.child_env(), total_timeout=request.timeout,
                idle_timeout=request.options.get("idle_timeout"),
                cancel=request.options.get("cancel"), on_line=on_line)
        except FileNotFoundError:
            meta["error_kind"] = "not_installed"
            return Result(provider=self.id, error=f"`{cmd}` is not on PATH", meta=meta)

        out, err = "\n".join(lines), (err or "").strip()
        text, problem, denied = self._parse(out)
        usage = self._usage(out)
        if usage:
            meta["usage"] = usage
        if denied:
            meta["denied"] = [{"tool": d, "input": {}, "reason": "", "compound": False} for d in denied]
        if ended != "done":
            idle = request.options.get("idle_timeout")
            meta.update(partial=True, error_kind=ended)
            msg = {"stopped": "stopped", "idle_timeout": f"no output for {idle}s",
                   "total_timeout": f"timed out after {request.timeout}s"}[ended]
            return Result(text=text or "", provider=self.id, model=model, meta=meta, error=msg)

        def fail(message):
            kind, retry = events.classify(message, err, rc)
            meta["error_kind"] = kind
            if retry:
                meta["retry_at"] = retry
            return Result(provider=self.id, model=model, meta=meta, error=message)

        if rc != 0 and text is None:
            return fail(err[:400] or f"exit {rc}: {problem}")
        if text is None and denied:
            return fail(problem)
        if text is None:
            tail = (out.strip()[-200:] + " | " + err[-200:]).strip(" |")
            return fail(f"{problem}: {tail}")
        return Result(text=text, provider=self.id, model=model, meta=meta)
