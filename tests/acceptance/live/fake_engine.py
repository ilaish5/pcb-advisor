"""The oracle's stand-in for the agent engine CLI (`claude -p - --output-format stream-json`). The product runs it as its
engine command (live/server.py points the config at it). It is NOT product code: it plays a turn the oracle scripted.

A turn script is a JSON file in $ACC_FAKE_ENGINE_DIR/queue/ (oldest name first, consumed once); with none queued,
default.json, else a short plain reply. Script keys:
  steps   [{"tool": "Read", "input": {...}, "delay": s, "result": "..."} | {"sleep": s} | {"text": "...", "delay": s}]
  final   the final message text (it may hold the product's ```json {"actions": [...]}``` block)
  die     true: exit 137 after the steps with no result line (the engine crashed or was killed)
  stall   seconds of total silence before anything is printed (P0-2 stall canary)
  error   a result line with is_error true and this text
Every run writes prompts/<n>.txt (the prompt it was given), pid/<pid> (so a fault injector can kill it) and log.jsonl.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

D = pathlib.Path(os.environ.get("ACC_FAKE_ENGINE_DIR") or ".")


def out(obj) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def log(**kw) -> None:
    with open(D / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.time(), "pid": os.getpid(), **kw}) + "\n")


def take_script() -> dict:
    q = D / "queue"
    if q.is_dir():
        for p in sorted(q.glob("*.json")):
            done = D / "done"
            done.mkdir(exist_ok=True)
            try:
                p.rename(done / p.name)
            except OSError:
                continue
            return json.loads((done / p.name).read_text(encoding="utf-8"))
    dflt = D / "default.json"
    if dflt.is_file():
        return json.loads(dflt.read_text(encoding="utf-8"))
    return {"final": "OK."}


def main() -> int:
    D.mkdir(parents=True, exist_ok=True)
    prompt = sys.stdin.read() if not sys.stdin.isatty() else ""
    (D / "prompts").mkdir(exist_ok=True)
    n = len(list((D / "prompts").glob("*.txt")))
    (D / "prompts" / f"{n:04d}.txt").write_text(prompt, encoding="utf-8")
    (D / "pid").mkdir(exist_ok=True)
    pidf = D / "pid" / str(os.getpid())
    pidf.write_text(json.dumps({"start": time.time(), "argv": sys.argv[1:]}), encoding="utf-8")
    s = take_script()
    log(event="start", n=n, script=s.get("name", ""))
    try:
        if s.get("stall"):
            time.sleep(float(s["stall"]))
        out({"type": "system", "subtype": "init", "session_id": f"fake-{os.getpid()}", "model": "fake"})
        for i, st in enumerate(s.get("steps") or []):
            if "sleep" in st:
                time.sleep(float(st["sleep"]))
                continue
            time.sleep(float(st.get("delay", 0.3)))
            if "tool" in st:
                tid = f"toolu_{os.getpid()}_{i}"
                out({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tid, "name": st["tool"],
                                                                    "input": st.get("input") or {}}]}})
                out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid,
                                                               "content": st.get("result", "ok"),
                                                               "is_error": bool(st.get("is_error"))}]}})
            elif "text" in st:
                out({"type": "assistant", "message": {"content": [{"type": "text", "text": st["text"]}]}})
        if s.get("die"):
            log(event="die")
            os._exit(137)
        final = s.get("final", "OK.")
        if s.get("error"):
            out({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": s["error"],
                 "total_cost_usd": 0, "duration_ms": 1, "num_turns": 1, "usage": {"input_tokens": 1, "output_tokens": 1}})
            log(event="end", error=True)
            return 1
        out({"type": "assistant", "message": {"content": [{"type": "text", "text": final}]}})
        out({"type": "result", "subtype": "success", "is_error": False, "result": final, "total_cost_usd": 0,
             "duration_ms": 1, "num_turns": 1, "usage": {"input_tokens": 1, "output_tokens": 1}})
        log(event="end")
        return 0
    finally:
        try:
            pidf.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
