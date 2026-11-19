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
import shutil
import subprocess
import time

import oscompat

from . import events, stream
from .base import Provider, Request, Result


_AGY_MODELS_CACHE = None          # the models this agy listed, read once per server run


def parse_models(out):
    """`agy models` lines are "<id>\t<name>"; anything else (e.g. "Fetching available models...") is not a model."""
    models = []
    for line in (out or "").splitlines():
        if "\t" not in line:
            continue
        mid, _, name = line.partition("\t")
        mid, name = mid.strip(), name.strip()
        if mid and " " not in mid:
            models.append({"id": mid, "name": name or mid})
    return models


def list_models(cmd):
    """Whatever this agy offers today ([] when it is missing, fails or hangs)."""
    if not shutil.which(cmd):
        return []
    try:
        # describe() runs while the settings page loads, so a CLI that
        # hangs here must not hang the server with it
        out = subprocess.check_output([oscompat.resolve(cmd), "models"], stderr=subprocess.DEVNULL,
                                      **oscompat.TEXT, timeout=10)
    except Exception:
        return []
    return parse_models(out)


def clip_text(t):
    t = str(t)
    return t if len(t) <= events.CALL_CUT else t[:events.CALL_CUT] + f"...[+{len(t) - events.CALL_CUT} chars]"

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
        if not _AGY_MODELS_CACHE:
            # read once per server run (models Antigravity adds show up after a restart);
            # a failed listing is not kept, so the next page load tries again
            _AGY_MODELS_CACHE = list_models(self.config.get("command", "agy")) or None
        d["models"] = list(_AGY_MODELS_CACHE or [])
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
            # the model name already carries the level (gemini-4-hydrogen-high);
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

    NAME_KEYS = ("tool", "tool_name", "toolName", "name", "display_name", "displayName", "action", "step", "kind")
    INPUT_KEYS = ("input", "args", "arguments", "params", "parameters", "command", "cmd")
    RESULT_KEYS = ("result", "output", "stdout", "response", "content", "text")
    SKIP_EVENTS = ("assistant", "user", "result", "system", "init", "thinking", "text", "message", "usage")

    @classmethod
    def _calls(cls, lines, stamps):
        """(calls, raw_events) from agy's stream-json lines. agy's step events are not documented, so this is tolerant: any
        JSON event that is not the prompt, the answer text or the final result and that names a tool, action or command is a call;
        an event whose name says result/output/end/done closes the latest open call of that name. Events it cannot place at all
        are kept raw (capped) so the debugger still sees them."""
        calls, raw = [], []
        for raw_line, ts in zip(lines, stamps):
            line = raw_line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            kind = str(ev.get("event") or ev.get("type") or "").lower()
            su = ev.get("step_update")
            if kind == "step_update" and isinstance(su, dict):
                # agy's real shape: {"event":"step_update","step_update":{"step_index":2,"state":"ACTIVE"|"DONE",
                # "step_type":"tool","tool_name":"run_command","tool_info":{"name","parameters","output"}}}
                if su.get("step_type") != "tool":
                    continue
                info = su.get("tool_info") if isinstance(su.get("tool_info"), dict) else {}
                name = str(su.get("tool_name") or info.get("name") or "tool")
                inp = info.get("parameters") if isinstance(info.get("parameters"), dict) else {}
                out = info.get("output")
                text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str) if out is not None else ""
                state = str(su.get("state") or "").upper()
                failed = state in ("ERROR", "FAILED", "CANCELED", "CANCELLED") or bool(su.get("error") or info.get("error"))
                if failed and not text:
                    text = str(su.get("error") or info.get("error") or state)
                idx = su.get("step_index")
                call = next((c for c in reversed(calls) if c.get("step") == idx and idx is not None), None)
                if call is None:
                    if len(calls) >= events.MAX_CALLS:
                        continue
                    call = {"ts": ts, "step": idx, "tool": name,
                            "label": events._clip(f"{name} {json.dumps(inp, ensure_ascii=False, default=str)}"),
                            "input": events.clip_input(inp), "failed": False, "error": False}
                    calls.append(call)
                if text:
                    call["result"] = clip_text(text)
                if su.get("duration_seconds") is not None:
                    call["seconds"] = su["duration_seconds"]
                if state != "ACTIVE":
                    call.update(failed=failed, error=failed, result_ts=ts)
                continue
            if kind in cls.SKIP_EVENTS:
                continue
            body = ev
            for k in ("tool", "step", "action", "tool_call", "toolCall"):          # {"event": "tool_call", "tool": {"name": ..., "args": ...}}
                if isinstance(ev.get(k), dict):
                    body = {**ev, **ev[k]}
                    break
            name = next((str(body[k]) for k in cls.NAME_KEYS if isinstance(body.get(k), str) and body[k] and k != "kind"), "")
            if not name and kind and not any(w in kind for w in ("tool", "step", "action", "command", "run", "exec")):
                if len(raw) < 30:
                    raw.append({"ts": ts, "event": clip_text(line)})
                continue
            name = name or kind
            inp = next((body[k] for k in cls.INPUT_KEYS if body.get(k) not in (None, "")), {})
            inp = inp if isinstance(inp, dict) else {"command": inp}
            res = next((body[k] for k in cls.RESULT_KEYS if body.get(k) not in (None, "")), None)
            closing = any(w in kind for w in ("result", "output", "end", "done", "complete", "finish"))
            failed = bool(body.get("is_error") or body.get("error") or str(body.get("status") or "").upper() in ("ERROR", "FAILED", "FAILURE") or
                          (isinstance(body.get("exit_code"), int) and body["exit_code"] != 0) or (isinstance(body.get("exitCode"), int) and body["exitCode"] != 0))
            text = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, default=str) if res is not None else ""
            if body.get("error") and not text:
                text = str(body["error"])
            if closing:
                open_ = next((c for c in reversed(calls) if c["tool"] == name and "result" not in c), None)
                if open_ is not None:
                    open_.update(result=clip_text(text), failed=failed, error=failed, result_ts=ts)
                    continue
            if len(calls) < events.MAX_CALLS:
                call = {"ts": ts, "tool": name, "label": events._clip(f"{name} {json.dumps(inp, ensure_ascii=False, default=str)}"),
                        "input": events.clip_input(inp), "failed": failed, "error": failed}
                if text:
                    call["result"] = clip_text(text)
                calls.append(call)
        return calls, ([] if calls else raw)

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

        lines, stamps, last_text = [], [], [-1e9]
        on_event = request.options.get("on_event")

        def on_line(raw):
            lines.append(raw)
            stamps.append(events.now_iso())
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
        try:
            calls, raw_events = self._calls(lines, stamps)
            if calls:
                meta["calls"] = calls
            if raw_events:
                meta["raw_events"] = raw_events
        except Exception:         # a debug record must never cost the answer
            pass
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
