"""A Playwright driver for the behaviour metrics: the installed Chrome (channel="chrome"), a throw-away profile (never the owner's),
DOM snapshots with timestamps, network timing. The metric reads the rendered DOM and the HTTP API behind it (A2, UI facts).

    with Browser(base_url, project) as b:
        b.goto_tab("pcb")
        s = b.snap("after-place")          # {"t": epoch s, "label", "tab", "text", "notes": [...], ...}
"""
from __future__ import annotations

import time
from typing import Any

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # reported by the metric as an error, never as a pass
    sync_playwright = None

VIEWPORT = {"width": 1366, "height": 768}      # P0-4 states its limits "at 1366 x 768"

# What a note/banner of the page looks like in the DOM: any element that carries a tone class. The snapshot keeps the class list and
# the text, so a metric decides what the tone was (green = ok/good, amber = warn, red = bad).
_SNAP_JS = r"""
() => {
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
                     return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const txt = e => (e.innerText || '').replace(/[ \t]+/g, ' ').trim();
  const notes = [...document.querySelectorAll('#view [class*="note"], #view [class*="banner"], #view [class*="alert"], #view [class*="toast"], #view [role="status"], #view [role="alert"], #toast, .toast')]
      .filter(vis).map(e => ({cls: e.className && e.className.baseVal === undefined ? String(e.className) : '', text: txt(e).slice(0, 1500), full: (e.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 4000),
                              bold: [...e.querySelectorAll('b, strong')].map(x => txt(x)).slice(0, 3),
                              rect: (r => [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)])(e.getBoundingClientRect()),
                              details: [...e.querySelectorAll('details')].map(d => ({open: d.open, summary: txt(d.querySelector('summary') || d).slice(0, 80)}))}));
  const buttons = [...document.querySelectorAll('#view button, #view a, #chat button')].filter(vis)
      .map(e => ({text: txt(e).slice(0, 80), act: e.dataset.act || '', disabled: !!e.disabled || e.getAttribute('aria-disabled') === 'true'}));
  return {url: location.href, view: (document.querySelector('#view') || {innerText: ''}).innerText || '', notes, buttons,
          nav: [...document.querySelectorAll('#nav button')].map(e => ({text: txt(e), tab: e.dataset.tab || e.dataset.page || ''}))};
}
"""


class Browser:
    def __init__(self, base_url: str, project: str, headless: bool = True, viewport: dict | None = None):
        if sync_playwright is None:
            raise RuntimeError("playwright is not installed in this python")
        self.base, self.project, self.headless = base_url.rstrip("/"), project, headless
        self.viewport = viewport or VIEWPORT
        self.snaps: list[dict] = []
        self.requests: list[dict] = []
        self.console: list[dict] = []
        self._pw = self._browser = self.page = None

    def __enter__(self) -> "Browser":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(channel="chrome", headless=self.headless)       # own temp profile
        ctx = self._browser.new_context(viewport=self.viewport)
        self.page = ctx.new_page()
        self.page.on("request", lambda r: self.requests.append({"t": time.time(), "m": r.method, "u": r.url}) if "/api/" in r.url else None)
        self.page.on("console", lambda m: self.console.append({"t": time.time(), "type": m.type, "text": m.text[:500]}))
        self.page.on("dialog", lambda d: (self.console.append({"t": time.time(), "type": "dialog", "text": d.message[:300]}), d.dismiss()))
        self.page.goto(f"{self.base}/?project={self.project}")
        self.page.wait_for_selector("#nav [data-tab]", timeout=20000)
        return self

    def __exit__(self, *exc) -> None:
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    # -- navigation
    def goto_tab(self, tab: str, settle: float = 1.5) -> None:
        self.page.click(f'#nav [data-tab="{tab}"], #nav [data-page="{tab}"]')
        self.page.wait_for_timeout(int(settle * 1000))

    def reload(self, settle: float = 2.0, timeout: float = 120.0) -> float:
        """Reload and wait for the page to be usable again; returns the seconds that took (a busy server answers slowly: that is data)."""
        t0 = time.time()
        self.page.reload(timeout=int(timeout * 1000))
        self.page.wait_for_selector("#nav [data-tab]", timeout=int(timeout * 1000))
        took = time.time() - t0
        self.page.wait_for_timeout(int(settle * 1000))
        return took

    def click_act(self, act: str, **data: str) -> None:
        sel = f'[data-act="{act}"]' + "".join(f'[data-{k}="{v}"]' for k, v in data.items())
        self.page.click(sel)

    # -- reading
    def snap(self, label: str = "") -> dict:
        s: dict[str, Any] = self.page.evaluate(_SNAP_JS)
        s.update(t=time.time(), label=label)
        self.snaps.append(s)
        return s

    def text(self, selector: str = "#view") -> str:
        return self.page.inner_text(selector)

    def js(self, expr: str) -> Any:
        return self.page.evaluate(expr)

    def api(self, path: str, data: dict | None = None) -> Any:
        """The HTTP API behind the page, called from the page (same origin, same cookies)."""
        return self.page.evaluate(
            "async ([p, d]) => { const r = await fetch(p, d ? {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(d)} : {}); "
            "let b; try { b = await r.json(); } catch (e) { b = await r.text(); } return {status: r.status, body: b}; }", [path, data])

    def wait_text(self, needle: str, timeout: float = 60, selector: str = "#view") -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if needle in self.page.inner_text(selector):
                return True
            time.sleep(0.5)
        return False
