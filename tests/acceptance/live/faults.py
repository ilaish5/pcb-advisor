"""Fault injectors for live metrics. Each is oracle-owned and acts from outside the product: network, files, processes.

- blackhole_proxy(): an HTTP(S) proxy that accepts and never answers (JLC/LCSC/URL sources hang: a long wait).
- refusing_proxy(): a port nobody listens on (JLC/LCSC unreachable at once).
- not_found_server(): an HTTP server that answers 404 for every path (a URL source that is gone).
- kill_engine(srv): kill the running fake engine process(es) of a server (the agent engine dies mid-turn).
- foreign_write(path): a process that is not the agent writes a file (P0-1 / W1 canary).
Server-side env for the network faults: proxy_env(url) -> HTTPS_PROXY/HTTP_PROXY for the product process only.
"""
from __future__ import annotations

import http.server
import os
import pathlib
import signal
import socket
import subprocess
import sys
import threading


class _Hold(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(64)
        self.port = self.sock.getsockname()[1]
        self.conns = []
        self.hits = 0

    def run(self) -> None:
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.hits += 1
            self.conns.append(c)          # never read, never answer: the client waits until its own timeout

    def close(self) -> None:
        for c in self.conns:
            try:
                c.close()
            except OSError:
                pass
        self.sock.close()


def blackhole_proxy() -> _Hold:
    h = _Hold()
    h.start()
    return h


def refusing_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                             # nothing listens there now: connect() is refused
    return port


def proxy_env(port: int) -> dict:
    url = f"http://127.0.0.1:{port}"
    return {"HTTPS_PROXY": url, "HTTP_PROXY": url, "https_proxy": url, "http_proxy": url,
            "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}


class _NotFound(http.server.BaseHTTPRequestHandler):
    hits: list = []

    def do_GET(self):  # noqa: N802
        _NotFound.hits.append(self.path)
        body = b"<html><body><h1>404 Not Found</h1></body></html>"
        self.send_response(404)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_HEAD = do_GET

    def log_message(self, *a):
        pass


def not_found_server() -> http.server.ThreadingHTTPServer:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _NotFound)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def engine_pids(srv) -> list[int]:
    d = srv.home / "fake-engine" / "pid"
    return [int(p.name) for p in d.glob("*") if p.name.isdigit()] if d.is_dir() else []


def kill_engine(srv) -> list[int]:
    killed = []
    for pid in engine_pids(srv):
        try:
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))      # Windows has no SIGKILL: os.kill(…, SIGTERM) terminates the process there
            killed.append(pid)
        except ProcessLookupError:
            pass
    return killed


def foreign_write(path: pathlib.Path, text: str) -> int:
    """Write `text` to `path` from a separate process (its own PID, not the agent's tool); returns that PID."""
    code = "import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(sys.argv[2])"
    pr = subprocess.run([sys.executable, "-I", "-c", code, str(path), text], check=True)
    return pr.returncode
