"""Claude Code CLI: spawn `claude -p`, take stdout."""
import json
import re
import shutil
import time

import oscompat

from . import events, stream
from .base import Provider, Request, Result

# what the CLI accepts for --permission-mode
PERMISSION_MODES = {"acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"}

# config key -> CLI flag. Order is fixed so the argv is reproducible.
TOOL_FLAGS = (
    ("available", "--tools"),
    ("allowed", "--allowedTools"),
    ("disallowed", "--disallowedTools"),
    ("permission_mode", "--permission-mode"),
)
# known under `tools` but not a flag of its own: appended to `allowed` (the student's one-click allows)
TOOL_EXTRA = "allowed_extra"
TEXT_EVENT_EVERY = 2.0      # seconds between "text"/"thinking" events


def _quoted_twins(rules):
    """Where the repo or projects path still has a space (no 8.3 short name), the engine types it
    double-quoted; add the rule with that path quoted so it matches too."""
    import workspace
    twins = []
    for p in {oscompat.command_path(workspace.REPO), oscompat.command_path(workspace.projects_dir())}:
        if " " not in p:
            continue
        for r in rules:
            m = re.search(re.escape(p) + r"[^\s)]*", r)
            if m:
                q = r[:m.start()] + '"' + m.group(0) + '"' + r[m.end():]
                if q not in rules and q not in twins:
                    twins.append(q)
    return twins


class _Turn:
    """What one streamed turn has shown so far. Fed line by line from the reader thread."""

    def __init__(self, on_event=None):
        self.on_event = on_event
        self.lines = []
        self.texts = []
        self.steps = []
        self.uses = {}                  # tool_use_id -> (name, input)
        self.denied = {}                # tool_use_id (or an index key) -> entry
        self.result = None
        self.events = 0                 # JSON event lines seen: tells a stream from plain text
        self._last_soft = {}

    def _emit(self, kind, label, tool=None):
        if not self.on_event:
            return
        ev = {"kind": kind, "label": label, "ts": time.time()}
        if tool:
            ev["tool"] = tool
        try:
            self.on_event(ev)
        except Exception:
            pass

    def _soft(self, kind, label):
        now = time.monotonic()
        if now - self._last_soft.get(kind, -1e9) >= TEXT_EVENT_EVERY:
            self._last_soft[kind] = now
            self._emit(kind, label)

    def feed(self, line):
        self.lines.append(line)
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            ev = json.loads(line)
        except ValueError:
            return
        if not isinstance(ev, dict):
            return
        self.events += 1
        kind = ev.get("type")
        if kind == "assistant":
            content = (ev.get("message") or {}).get("content")
            for part in content if isinstance(content, list) else []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use":
                    name, inp = str(part.get("name") or ""), part.get("input") or {}
                    self.uses[part.get("id")] = (name, inp)
                    lab = events.label(name, inp)
                    self.steps.append(lab)
                    self._emit("tool", lab, name)
                elif part.get("type") == "text" and str(part.get("text") or "").strip():
                    self.texts.append(part["text"])
                    self._soft("text", "Writing the answer")
                elif part.get("type") == "thinking":
                    self._soft("thinking", "Thinking")
        elif kind == "system" and ev.get("subtype") == "permission_denied":
            tid = ev.get("tool_use_id") or f"#{len(self.denied)}"
            name = str(ev.get("tool_name") or "")
            inp = (self.uses.get(tid) or (name, {}))[1]
            self.denied[tid] = {"tool": name, "input": inp if isinstance(inp, dict) else {},
                                "reason": str(ev.get("message") or ""),
                                "compound": ev.get("decision_reason_type") == "subcommandResults"}
            self._emit("denied", "Denied: " + events.label(name, inp), name)
        elif kind == "result":
            self.result = ev

    def partial_text(self):
        return "\n\n".join(self.texts)

    def denials(self):
        """Stream events merged with the result's permission_denials, by tool_use_id."""
        out = dict(self.denied)
        for d in (self.result or {}).get("permission_denials") or []:
            if not isinstance(d, dict):
                continue
            tid = d.get("tool_use_id") or f"#r{len(out)}"
            inp = d.get("tool_input") if isinstance(d.get("tool_input"), dict) else {}
            cur = out.get(tid)
            if cur is None:
                out[tid] = {"tool": str(d.get("tool_name") or ""), "input": inp, "reason": "", "compound": False}
            elif not cur["input"]:
                cur["input"] = inp
        return list(out.values())

    def final(self):
        """(text, meta, error) once the stream is over."""
        obj = self.result
        meta = {}
        if self.steps:
            meta["steps"] = list(self.steps)
        den = self.denials()
        if den:
            meta["denied"] = den
        if obj is None:
            return None, meta, ""
        usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
        extra = {"usage": {k: usage[k] for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                 "cache_creation_input_tokens") if isinstance(usage.get(k), int)},
                 "cost_usd": obj.get("total_cost_usd"), "engine_ms": obj.get("duration_ms"),
                 "turns": obj.get("num_turns"),
                 "models": sorted((obj.get("modelUsage") or {}).keys()) if isinstance(obj.get("modelUsage"), dict) else []}
        meta.update({k: v for k, v in extra.items() if v not in (None, {}, [])})
        text = obj.get("result")
        if obj.get("is_error") or not isinstance(text, str):
            return "", meta, (str(text or obj.get("subtype") or "the engine reported an error"))[:400]
        return text, meta, ""


class ClaudeCodeProvider(Provider):
    id = "claude_code"
    title = "Claude Code CLI"
    status = "implemented"
    workspace_access = True
    doc = "Runs the `claude` binary on PATH. No API key here - the CLI owns auth."

    # ------------------------------------------------------------- tools
    #
    # The CLI is an agent in its own right: it can read files, grep, run
    # commands. We do not take that away, and we do not hand it out either -
    # every key below defaults to null, and a null key means the flag is never
    # passed, so the CLI's own settings decide exactly as if this tool did not
    # exist. Set a key and you are deliberately overriding those settings for
    # the turns pcb-advisor drives.
    #
    #   available        --tools           the built-in set it may draw from.
    #                                      "" disables every tool, "default" is all.
    #   allowed          --allowedTools    pre-approved, no prompt. Patterns work:
    #                                      ["Read", "Grep", "Bash(git status)"]
    #   disallowed       --disallowedTools refused outright. Wins over allowed.
    #   permission_mode  --permission-mode acceptEdits | auto | bypassPermissions |
    #                                      manual | dontAsk | plan
    #
    # A list is joined with commas; a string is passed through. "" is a real
    # value (it is how --tools disables everything), which is why the "do not
    # pass this" signal is null and not the empty string.

    def _tool_argv(self):
        cfg = self.config.get("tools") or {}
        argv = []
        for key, flag in TOOL_FLAGS:
            value = cfg.get(key)
            if value is None:
                continue                       # the CLI's own settings stand
            if isinstance(value, (list, tuple)):
                # "Bash({python} scripts/x.py *)" becomes python3 on a Mac and
                # python or py on Windows - whatever the engine's shell will type
                if key == "allowed":
                    value = [*value, *(cfg.get(TOOL_EXTRA) or [])]
                rules = [oscompat.py(str(v)) for v in value]
                # On Windows the engine also has a PowerShell tool that Bash(...) rules do
                # not cover; without the twin a script run through it is denied.
                rules += [f"PowerShell({r[5:]}" for r in rules
                          if r.startswith("Bash(") and f"PowerShell({r[5:]}" not in rules]
                rules += _quoted_twins(rules)
                value = ",".join(rules)
            argv += [flag, str(value)]
        return argv

    def has_workspace(self):
        """`--tools ""` disables every tool, so the engine is back to text-only
        and must not be told to go and read things."""
        return str((self.config.get("tools") or {}).get("available", "x")) != ""

    def _tool_problem(self):
        cfg = self.config.get("tools") or {}
        if not isinstance(cfg, dict):
            return "agent.providers.claude_code.tools must be an object"
        unknown = set(cfg) - {k for k, _ in TOOL_FLAGS} - {TOOL_EXTRA}
        if unknown:
            return f"unknown tools key(s): {', '.join(sorted(unknown))}"
        mode = cfg.get("permission_mode")
        if mode is not None and mode not in PERMISSION_MODES:
            return (f"permission_mode '{mode}' is not one of "
                    f"{', '.join(sorted(PERMISSION_MODES))}")
        return ""

    # ------------------------------------------------------------- run

    def available(self):
        if not self.config.get("enabled", True):
            return False, "claude_code is disabled in config"
        cmd = self.config.get("command", "claude")
        if not oscompat.which(cmd):
            return False, f"`{cmd}` is not on PATH"
        problem = self._tool_problem()
        if problem:
            return False, problem
        return True, ""

    def describe(self):
        d = super().describe()
        cfg = self.config.get("tools") or {}
        set_keys = [k for k, _ in TOOL_FLAGS if cfg.get(k) is not None]
        d["models"] = [{"id": "opus", "name": "Opus"}, {"id": "sonnet", "name": "Sonnet"}]
        d["tools"] = ", ".join(f"{k}={cfg[k]}" for k in set_keys) if set_keys \
            else "the CLI's own settings"
        return d

    def complete(self, request: Request) -> Result:
        ok, why = self.available()
        if not ok:
            return Result(provider=self.id, error=why,
                          meta={"error_kind": "not_installed"} if "not on PATH" in why else {})

        cmd = self.config.get("command", "claude")
        args = list(self.config.get("args") or ["-p", "-", "--output-format", "text"])
        model = request.model or self.config.get("model") or ""
        # --add-dir is variadic like the tool flags: it goes right after the
        # fixed args and before another flag, so it never eats a tool pattern
        # and nothing but a flag ever follows it (the prompt is on stdin).
        add = []
        for d in request.options.get("add_dirs") or []:
            add += ["--add-dir", str(d)]
        argv = [oscompat.resolve(cmd), *args, *add, *self._tool_argv()]
        if model:
            argv += ["--model", model]
        effort = self.config.get("effort")
        if effort:
            argv += ["--effort", effort]

        # The prompt goes on stdin, never as an argument. --allowedTools and
        # friends are variadic: anything after them is read as another tool
        # name, so a trailing prompt argument is silently swallowed and the CLI
        # exits with "Input must be provided". stdin also sidesteps ARG_MAX and
        # lets a tool pattern contain spaces - Bash(python3 scripts/x.py *).
        turn = _Turn(request.options.get("on_event"))
        try:
            rc, err, ended = stream.run(
                argv, stdin_text=request.prompt, cwd=request.options.get("cwd") or None,
                env=oscompat.child_env(), total_timeout=request.timeout,
                idle_timeout=request.options.get("idle_timeout"),
                cancel=request.options.get("cancel"), on_line=turn.feed)
        except FileNotFoundError:
            return Result(provider=self.id, error=f"`{cmd}` is not on PATH",
                          meta={"error_kind": "not_installed"})

        text, meta, failed = turn.final()
        if ended != "done":
            meta["partial"] = True
            meta["error_kind"] = ended if ended != "stopped" else "stopped"
            idle = request.options.get("idle_timeout")
            msg = {"stopped": "stopped",
                   "idle_timeout": f"no output for {idle}s",
                   "total_timeout": f"timed out after {request.timeout}s"}[ended]
            return Result(text=turn.partial_text(), provider=self.id, model=model, meta=meta, error=msg)
        if text is None and not failed and turn.events:
            failed = "the engine ended without a result"
        if failed or rc != 0:
            message = failed or (err or "").strip()[:400] or f"exit {rc}"
            kind, retry = events.classify(failed, err, rc)
            meta["error_kind"] = kind
            if retry:
                meta["retry_at"] = retry
            return Result(text=turn.partial_text() if not text else text, provider=self.id, model=model,
                          meta=meta, error=message)
        if text is None:                                  # plain text passthrough (an older config)
            text = "\n".join(turn.lines)
        return Result(text=text, provider=self.id, model=model, meta=meta)

    @staticmethod
    def _parse(stdout):
        """(text, meta, error) from a finished stdout: stream-json lines (the result is the last
        `result` line), the older single JSON object, or plain text, which passes through."""
        raw = (stdout or "").strip()
        if not raw.startswith("{"):
            return stdout, {}, ""
        turn = _Turn()
        for line in raw.splitlines():
            turn.feed(line)
        if turn.result is None:
            try:                                          # one object spread over several lines
                obj = json.loads(raw)
            except ValueError:
                if turn.events:
                    return turn.partial_text(), turn.final()[1], "the engine ended without a result"
                return stdout, {}, ""
            if not isinstance(obj, dict) or obj.get("type") != "result":
                if turn.events:
                    return turn.partial_text(), turn.final()[1], "the engine ended without a result"
                return stdout, {}, ""
            turn.result = obj
        text, meta, err = turn.final()
        return text, meta, err
