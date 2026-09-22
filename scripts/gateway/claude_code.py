"""Claude Code CLI: spawn `claude -p`, take stdout."""
import shutil
import subprocess

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


class ClaudeCodeProvider(Provider):
    id = "claude_code"
    title = "Claude Code CLI"
    status = "implemented"
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
                value = ",".join(str(v) for v in value)
            argv += [flag, str(value)]
        return argv

    def _tool_problem(self):
        cfg = self.config.get("tools") or {}
        if not isinstance(cfg, dict):
            return "agent.providers.claude_code.tools must be an object"
        unknown = set(cfg) - {k for k, _ in TOOL_FLAGS}
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
        if not shutil.which(cmd):
            return False, f"`{cmd}` is not on PATH"
        problem = self._tool_problem()
        if problem:
            return False, problem
        return True, ""

    def describe(self):
        d = super().describe()
        cfg = self.config.get("tools") or {}
        set_keys = [k for k, _ in TOOL_FLAGS if cfg.get(k) is not None]
        d["tools"] = ", ".join(f"{k}={cfg[k]}" for k in set_keys) if set_keys \
            else "the CLI's own settings"
        return d

    def complete(self, request: Request) -> Result:
        ok, why = self.available()
        if not ok:
            return Result(provider=self.id, error=why)

        cmd = self.config.get("command", "claude")
        args = list(self.config.get("args") or ["-p", "--output-format", "text"])
        model = request.model or self.config.get("model") or ""
        argv = [cmd, *args, *self._tool_argv(), request.prompt]
        if model:
            argv += ["--model", model]

        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=request.timeout,
                                  cwd=request.options.get("cwd") or None)
        except FileNotFoundError:
            return Result(provider=self.id, error=f"`{cmd}` is not on PATH")
        except subprocess.TimeoutExpired:
            return Result(provider=self.id,
                          error=f"timed out after {request.timeout}s")

        if proc.returncode != 0:
            return Result(provider=self.id, model=model,
                          error=(proc.stderr or "").strip()[:400] or
                                f"exit {proc.returncode}")
        return Result(text=proc.stdout, provider=self.id, model=model)
