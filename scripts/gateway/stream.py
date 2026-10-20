"""One Popen runner for every CLI engine: live lines, stop, idle and total timeouts.

`subprocess.run` can only wait. A turn that takes minutes needs three things it cannot give:
see each stdout line as it arrives (progress), kill the engine on request (Stop), and tell
"working quietly" from "stuck" (idle timeout). Reader threads - not `select`, which cannot
watch a pipe on Windows - push stdout/stderr lines; the caller thread only supervises.

Killing means the whole TREE: the engine's shell and every script it started. Windows:
`taskkill /T /F` (the child starts in its own process group). POSIX: the child starts a new
session and the group gets SIGTERM, then SIGKILL after 2 s.
"""
import os
import signal
import subprocess
import threading
import time

import oscompat

POLL = 0.05                 # supervisor tick: cancel/timeouts are noticed within this
KILL_GRACE = 2.0            # POSIX: SIGTERM -> SIGKILL


def kill_tree(proc):
    """End `proc` and everything it started. Never raises."""
    try:
        if oscompat.WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + KILL_GRACE
            while time.monotonic() < deadline and proc.poll() is None:
                time.sleep(0.02)
            try:
                os.killpg(proc.pid, signal.SIGKILL)     # also reaps stragglers that ignored TERM
            except ProcessLookupError:
                pass
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _popen_kwargs():
    if oscompat.WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def run(argv, stdin_text="", cwd=None, env=None, total_timeout=None, idle_timeout=None,
        cancel=None, on_line=None):
    """Run argv, feed stdin_text, call on_line(line) per stdout line (no newline, from a reader
    thread). Returns (returncode, stderr, ended), ended in done | stopped | idle_timeout |
    total_timeout. returncode is None when we had to kill. FileNotFoundError propagates."""
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=cwd, env=env,
                            **oscompat.TEXT, **_popen_kwargs())
    last = [time.monotonic()]
    err_lines = []

    def pump_out():
        try:
            for line in proc.stdout:
                last[0] = time.monotonic()
                if on_line:
                    try:
                        on_line(line.rstrip("\r\n"))
                    except Exception:
                        pass                        # a bad callback must not stop the drain
        except (ValueError, OSError):
            pass

    def pump_err():
        try:
            for line in proc.stderr:
                err_lines.append(line)
        except (ValueError, OSError):
            pass

    def feed():
        try:
            proc.stdin.write(stdin_text or "")
            proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass                                    # the child may exit before reading it all

    threads = [threading.Thread(target=t, daemon=True) for t in (pump_out, pump_err, feed)]
    for t in threads:
        t.start()

    started = time.monotonic()
    ended = "done"
    while proc.poll() is None:
        now = time.monotonic()
        if cancel is not None and cancel.is_set():
            ended = "stopped"
        elif total_timeout and now - started > total_timeout:
            ended = "total_timeout"
        elif idle_timeout and now - last[0] > idle_timeout:
            ended = "idle_timeout"
        if ended != "done":
            kill_tree(proc)
            break
        time.sleep(POLL)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    for t in threads[:2]:
        t.join(timeout=3)                           # grandchildren holding the pipe open: do not wait on them
    rc = proc.returncode if ended == "done" else None
    return rc, "".join(err_lines), ended
