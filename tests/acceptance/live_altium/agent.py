"""Talk to the product's agent over its HTTP API (one chat turn = one POST /api/chat, answered when the agent has finished).
Nothing here imports product code (A2). A turn costs money: observations are cached and metrics share them."""
from __future__ import annotations

import threading
import time

from . import env


def tail_chat(state: dict, n: int = 6) -> list[dict]:
    return list((state or {}).get("chat") or [])[-n:]


def ask(base: str, project: str, text: str, timeout: float = 900, session: str | None = None) -> dict:
    """POST one message; returns {"code", "body", "t0", "t1", "reply", "chat_after"}. `reply` is the text of the agent's last message."""
    q = f"?project={project}" + (f"&session={session}" if session else "")
    t0 = time.time()
    code, body = env.http(f"{base}/api/chat{q}", {"text": text}, timeout=timeout)
    t1 = time.time()
    scode, st = env.http(f"{base}/api/state{q}", timeout=60)
    chat = (st or {}).get("chat") if isinstance(st, dict) else []
    reply = ""
    for m in reversed(chat or []):
        if m.get("role") == "agent":
            reply = m.get("text", "")
            break
    return {"code": code, "body": body, "t0": t0, "t1": t1, "reply": reply, "chat_after": chat or []}


def ask_with_background(base: str, project: str, text: str, background, timeout: float = 900) -> dict:
    """`ask` while `background(stop_event)` runs in its own thread (its own work, not the agent's)."""
    stop = threading.Event()
    th = threading.Thread(target=background, args=(stop,), daemon=True)
    th.start()
    try:
        return ask(base, project, text, timeout)
    finally:
        stop.set()
        th.join(timeout=30)
