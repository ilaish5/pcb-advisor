"""Claude Code CLI: spawn `claude -p`, take stdout."""
import shutil
import subprocess

from .base import Provider, Request, Result


class ClaudeCodeProvider(Provider):
    id = "claude_code"
    title = "Claude Code CLI"
    status = "implemented"
    doc = "Runs the `claude` binary on PATH. No API key here - the CLI owns auth."

    def available(self):
        if not self.config.get("enabled", True):
            return False, "claude_code is disabled in config"
        cmd = self.config.get("command", "claude")
        if not shutil.which(cmd):
            return False, f"`{cmd}` is not on PATH"
        return True, ""

    def complete(self, request: Request) -> Result:
        ok, why = self.available()
        if not ok:
            return Result(provider=self.id, error=why)

        cmd = self.config.get("command", "claude")
        args = list(self.config.get("args") or ["-p", "--output-format", "text"])
        model = request.model or self.config.get("model") or ""
        argv = [cmd, *args, request.prompt]
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
