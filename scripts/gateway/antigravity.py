"""Antigravity CLI (agy): spawn `agy -p`, take stdout.

Same shape as claude_code.py.  The two CLIs share a print-mode interface —
prompt on stdin, answer on stdout — so the provider is deliberately simple:
build the argv, run it, return whatever came back.

Differences from Claude Code:
  - No per-tool allow/deny flags.  Permissions are all-or-nothing via
    --dangerously-skip-permissions or --mode accept-edits.
  - An optional `effort` key (low | medium | high | xhigh | max) maps to
    --effort, which has no Claude Code equivalent.
"""
import shutil
import subprocess

from .base import Provider, Request, Result


_AGY_MODELS_CACHE = None

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
        return True, ""

    def describe(self):
        global _AGY_MODELS_CACHE
        d = super().describe()
        if _AGY_MODELS_CACHE is None:
            cmd = self.config.get("command", "agy")
            if shutil.which(cmd):
                try:
                    out = subprocess.check_output([cmd, "models"], stderr=subprocess.DEVNULL, text=True)
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
        d["models"] = _AGY_MODELS_CACHE
        return d

    def complete(self, request: Request) -> Result:
        ok, why = self.available()
        if not ok:
            return Result(provider=self.id, error=why)

        cmd = self.config.get("command", "agy")
        args = list(self.config.get("args") or [
            "-p", "-", "--output-format", "text",
            "--dangerously-skip-permissions",
        ])
        
        # agy expects the prompt as a CLI argument, not on stdin for text format
        if "-" in args:
            idx = args.index("-")
            args[idx] = request.prompt

        model = request.model or self.config.get("model") or ""
        argv = [cmd, *args]
        if model:
            argv += ["--model", model]

        try:
            proc = subprocess.run(
                argv,
                capture_output=True, text=True,
                timeout=request.timeout,
                cwd=request.options.get("cwd") or None,
            )
        except FileNotFoundError:
            return Result(provider=self.id, error=f"`{cmd}` is not on PATH")
        except subprocess.TimeoutExpired:
            return Result(provider=self.id,
                          error=f"timed out after {request.timeout}s")

        if proc.returncode != 0:
            return Result(provider=self.id, model=model,
                          error=(proc.stderr or "").strip()[:400]
                                or f"exit {proc.returncode}")
        return Result(text=proc.stdout, provider=self.id, model=model)
