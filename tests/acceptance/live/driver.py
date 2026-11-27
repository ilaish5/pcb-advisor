"""Playwright driver: open the product page in a real browser, record DOM snapshots with timestamps and every /api/*
response the page received. A metric reads these records (A1: the rendered DOM and the HTTP responses behind it).

Browser choice: ACCEPTANCE_BROWSER_CHANNEL=chrome (the owner's Windows PC) -> channel="chrome"; otherwise Playwright's
own Chromium, falling back to the cloud box's pre-installed one at /opt/pw-browsers/chromium.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
from urllib.parse import urlparse

VIEWPORT = {"width": 1366, "height": 768}       # ACCEPTANCE P0-4, F-I(f), T-H measure at 1366 x 768
FALLBACK_CHROMIUM = "/opt/pw-browsers/chromium"


def launch(pw):
    ch = os.environ.get("ACCEPTANCE_BROWSER_CHANNEL")
    if ch:
        return pw.chromium.launch(channel=ch)
    try:
        return pw.chromium.launch()
    except Exception:
        if os.path.exists(FALLBACK_CHROMIUM):
            return pw.chromium.launch(executable_path=FALLBACK_CHROMIUM, args=["--no-sandbox"])
        raise


# What one DOM snapshot keeps: visible text of the page regions a student reads, plus every element that looks like a
# status (busy/progress/toast/banner/error). Computed in the page, no product code: plain DOM queries.
SNAPSHOT_JS = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
  const pick = sel => [...document.querySelectorAll(sel)].filter(vis).map(el => ({
      cls: String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className || ''),
      tag: el.tagName.toLowerCase(), text: (el.innerText || '').trim().slice(0, 4000),
      box: (r => [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)])(el.getBoundingClientRect())}));
  return {
    t: Date.now() / 1000,
    url: location.href,
    body: (document.body.innerText || '').slice(0, 200000),
    status: pick('[class*="busy"],[class*="progress"],[class*="toast"],[class*="banner"],[class*="err"],[class*="warn"],[role="alert"],[role="status"],[aria-busy="true"],.spin,[class*="spinner"],[class*="running"]'),
  };
}
"""


class Page:
    """One browser page on the live server. Use as a context manager."""

    def __init__(self, base_url: str, project: str, viewport: dict | None = None, record_api: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.project = project
        self.viewport = viewport or VIEWPORT
        self.record_api = record_api
        self.api: list[dict] = []          # {t, method, path, status, body(json or None)}
        self.snaps: list[dict] = []
        self.console: list[str] = []
        self._pw = self._browser = self.page = None
        self._rec = None
        self._stop = threading.Event()

    def __enter__(self) -> "Page":
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        try:
            self._browser = launch(self._pw)
        except BaseException:                  # a failed launch must not leave Playwright's event loop running (every later metric then fails with 'Sync API inside the asyncio loop')
            self._pw.stop()
            raise
        self.page = self._browser.new_page(viewport=self.viewport)
        self.page.on("console", lambda m: self.console.append(f"{m.type}: {m.text}"))
        if self.record_api:
            self.page.on("response", self._on_response)
        return self

    def __exit__(self, *exc) -> None:
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    def _on_response(self, resp) -> None:
        u = urlparse(resp.url)
        if not u.path.startswith("/api/"):
            return
        body = None
        try:
            if "json" in (resp.headers.get("content-type") or ""):
                body = resp.json()
        except Exception:
            body = None
        self.api.append({"t": time.time(), "method": resp.request.method, "path": u.path, "query": u.query,
                         "status": resp.status, "body": body})

    def _settle(self, cap_ms: int = 6000) -> None:
        """Wait for the page to load, then for the network to go idle, with a cap: the app polls its status, so on some machines the network
        never goes idle (Windows: 30 s timeout). The fixed wait that follows every call is what lets the page settle."""
        self.page.wait_for_load_state("load")
        try:
            self.page.wait_for_load_state("networkidle", timeout=cap_ms)
        except Exception:                                  # playwright TimeoutError: carry on, the page is loaded
            pass

    # -- navigation
    def open(self, stage: str | None = None, wait_ms: int = 2500, query: str = "") -> "Page":
        url = f"{self.base_url}/?project={self.project}" + (f"&{query}" if query else "")
        self.page.goto(url)
        self._settle()
        self.page.wait_for_timeout(wait_ms)
        if stage:
            self.stage(stage)
        return self

    def stage(self, stage: str, wait_ms: int = 2500) -> None:
        """Open a stage the way the nav does (the nav item's click)."""
        nav = self.page.locator(f'[data-act="nav"][data-tab="{stage}"], [data-nav="{stage}"], [data-stage="{stage}"]')
        if nav.count():
            nav.first.click()
        else:                                              # the page's own navigation function, as a nav click calls it
            self.page.evaluate("s => go('workspace', s)", stage)
        self.page.wait_for_timeout(wait_ms)

    def reload(self, wait_ms: int = 2500) -> None:
        self.page.reload()
        self._settle()
        self.page.wait_for_timeout(wait_ms)

    # -- recording
    def snapshot(self, label: str = "") -> dict:
        s = self.page.evaluate(SNAPSHOT_JS)
        s["label"] = label
        self.snaps.append(s)
        return s

    def record_while(self, fn, every: float = 1.5, max_s: float = 900.0, until=None) -> list[dict]:
        """Run fn() (which starts an operation) and take a DOM snapshot every `every` s until until(snapshot) is true or
        max_s passes. Snapshots are taken on this thread (Playwright's sync API is single-threaded)."""
        start = len(self.snaps)
        fn()
        t_end = time.time() + max_s
        while time.time() < t_end:
            s = self.snapshot("rec")
            if until and until(s):
                break
            self.page.wait_for_timeout(int(every * 1000))
        return self.snaps[start:]

    def text(self) -> str:
        return self.page.inner_text("body")

    def eval(self, js: str, arg=None):
        return self.page.evaluate(js, arg) if arg is not None else self.page.evaluate(js)

    def save(self, folder: pathlib.Path, name: str) -> pathlib.Path:
        folder.mkdir(parents=True, exist_ok=True)
        p = folder / f"{name}.json"
        p.write_text(json.dumps({"snaps": self.snaps, "api": [{k: v for k, v in a.items() if k != "body"} for a in self.api],
                                 "console": self.console[-200:]}, indent=1, default=str), encoding="utf-8")
        return p
