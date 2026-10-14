"""
Live check of the JLC-facing workflows PCB Advisor relies on, with the synthetic test board of
scripts/jlc_testboard.py. NOT part of the pytest run: it talks to jlcpcb.com and jlcdfm.com and uploads
the synthetic board (never a real design).

    python scripts/jlc_live.py [--out DIR] [--mixed] [--skip dfm,quote,assembly,parts] [--profile EDGE_PROFILE]

Writes DIR (default docs/bench-runs/jlc-live-<YYYY-MM-DD>/): report.md, results.json and small evidence
(JLC's JSON answers, JLC's board renders, two cropped screenshots, the board zips, the BOM/CPL).

Anonymous only. It never logs in, never saves to a cart, never orders. Where a step needs an account it
records the login wall and stops. Steps:
  board     regenerate the board in both export formats (JLC's Altium 26 recipe, the advisor's OutJob)
  parts     scripts/jlc.py lookups vs the part-detail endpoint the JLCPCB site uses
  dfm       jlcdfm.com: login state, one upload attempt through the web app, the built-in rule set it
            serves (checks and Danger/Warning thresholds), and the demo report PDF fed to scripts/dfm.py
  quote     jlcpcb.com/quote: upload each zip through the web app, capture JLC's parse (size, layers,
            min line, holes, files) and JLC's board render; check drill hits against pads in the render
  assembly  BOM/CPL written by the advisor's own exporters; the quote page's assembly NEXT step
The browser is headless Edge driven over CDP (stdlib only); the site's own API answers are read from the
network traffic of the page. --profile reuses an Edge profile (close Edge first); a logged-in profile is
detected and reported, but the logged-in flows are not automated.
"""
import argparse
import base64
import datetime as dt
import hashlib
import io
import json
import math
import os
import pathlib
import select
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlparse

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "skills"))
import jlc_testboard as tb  # noqa: E402

EDGE = os.environ.get("PCB_ADVISOR_EDGE") or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DFM_HOME = "https://jlcdfm.com/"
DFM_API = "https://jlcdfm.com/api/overseas-dfm-service"
DFM_DEMO = "https://jlcdfm.com/viewer?pcbUploadFileId=633178306861395970&demo=1"
QUOTE = "https://jlcpcb.com/quote"
CART_API = "https://cart.jlcpcb.com/api/overseas-core-platform"
UA = "Mozilla/5.0 (pcb-advisor jlc_live; synthetic test board)"
PART_CODES = ["C20814", "C207075", "C25804"]          # C25804: a Basic 0603 resistor
EXPECT = {"C20814": "RUILON SMD1812P260TF/16"}
MIL = 0.0254


# =========================================================================== CDP (headless Edge)
class WS:
    def __init__(self, url):
        u = urlparse(url)
        self.s = socket.create_connection((u.hostname, u.port), timeout=120)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(1)
        if b" 101 " not in buf.split(b"\r\n")[0]:
            raise RuntimeError(f"CDP websocket refused: {buf[:80]!r}")
        self.id, self.events = 0, []

    def _read(self, n):
        b = b""
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise EOFError("CDP socket closed")
            b += c
        return b

    def _frame(self):
        msg = b""
        while True:
            h = self._read(2)
            fin, ln = h[0] & 0x80, h[1] & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._read(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._read(8))[0]
            msg += self._read(ln)
            if fin:
                return msg

    def call(self, method, **params):
        self.id += 1
        data = json.dumps({"id": self.id, "method": method, "params": params}).encode()
        mask, n = os.urandom(4), len(data)
        head = b"\x81" + (bytes([0x80 | n]) if n < 126 else b"\xfe" + struct.pack(">H", n) if n < 65536
                          else b"\xff" + struct.pack(">Q", n))
        self.s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        while True:
            m = json.loads(self._frame())
            if m.get("id") == self.id:
                return m
            self.events.append(m)

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        res = r.get("result", {})
        if "exceptionDetails" in res:
            return None
        return res.get("result", {}).get("value")

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if select.select([self.s], [], [], 0.2)[0]:
                self.events.append(json.loads(self._frame()))

    def shot(self, path, clip=None, scale=1.0):
        params = {"format": "png"}
        if clip:
            params["clip"] = dict(clip, scale=scale)
        r = self.call("Page.captureScreenshot", **params)
        pathlib.Path(path).write_bytes(base64.b64decode(r["result"]["data"]))


class Browser:
    def __init__(self, profile, size="1600,1200"):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.proc = subprocess.Popen([EDGE, "--headless=new", f"--remote-debugging-port={port}",
                                      f"--user-data-dir={pathlib.Path(profile).resolve()}", "--no-first-run",
                                      "--disable-gpu", f"--window-size={size}", "--lang=en-US", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tabs = None
        for _ in range(80):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2))
                if any(t.get("type") == "page" for t in tabs):
                    break
            except Exception:
                time.sleep(0.5)
        if not tabs:
            self.close()
            raise RuntimeError("headless Edge did not start (is the profile in use?)")
        self.ws = WS(next(t for t in tabs if t.get("type") == "page")["webSocketDebuggerUrl"])
        for dom in ("Page", "Runtime", "DOM"):
            self.ws.call(f"{dom}.enable")

    def close(self):
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
        else:
            self.proc.kill()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        time.sleep(1.5)       # let the profile lock go before the next session


class Tap:
    """Pauses matching API responses (Fetch domain, response stage) to read them before the page can
    navigate away, then lets them through. Optionally stops document navigations to a host."""

    def __init__(self, ws, patterns, block=()):
        self.ws, self.log, self.block = ws, [], list(block)
        pats = [{"urlPattern": p, "requestStage": "Response"} for p in patterns]
        pats += [{"urlPattern": f"*{h}*", "requestStage": "Request"} for h in self.block]
        ws.call("Fetch.enable", patterns=pats)

    def process(self):
        evs, self.ws.events = self.ws.events, []
        rest = []
        for e in evs:
            if e.get("method") != "Fetch.requestPaused":
                rest.append(e)
                continue
            p = e["params"]
            rid, req = p["requestId"], p["request"]
            if "responseStatusCode" not in p and "responseErrorReason" not in p:
                if any(h in req["url"] for h in self.block) and p.get("resourceType") == "Document":
                    self.log.append({"blocked": req["url"][:200]})
                    self.ws.call("Fetch.failRequest", requestId=rid, errorReason="BlockedByClient")
                else:
                    self.ws.call("Fetch.continueRequest", requestId=rid)
                continue
            body = None
            r = self.ws.call("Fetch.getResponseBody", requestId=rid).get("result") or {}
            if r:
                raw = base64.b64decode(r["body"]) if r.get("base64Encoded") else r["body"].encode()
                body = raw.decode("utf-8", "replace") if raw[:4] != b"\x89PNG" else "<png>"
            self.log.append({"url": req["url"], "method": req["method"], "status": p.get("responseStatusCode"),
                             "post": (req.get("postData") or "")[:2000], "body": body})
            self.ws.call("Fetch.continueResponse", requestId=rid)
        self.ws.events[:0] = rest

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            self.ws.pump(0.5)
            self.process()

    def find(self, part, contains=None):
        return [r for r in self.log if part in r.get("url", "") and (contains is None or contains in (r.get("body") or ""))]


def accept_cookies(ws):
    ws.js("(()=>{const b=[...document.querySelectorAll('button')].find(e=>/Accept/.test(e.innerText)); if(b) b.click()})()")


def set_file(ws, path):
    doc = ws.call("DOM.getDocument", depth=-1, pierce=True)["result"]["root"]
    ids = ws.call("DOM.querySelectorAll", nodeId=doc["nodeId"], selector="input[type=file]")["result"]["nodeIds"]
    if not ids:
        raise RuntimeError("no file input on the page")
    ws.call("DOM.setFileInputFiles", files=[str(pathlib.Path(path).resolve())], nodeId=ids[0])


def http_get(url, raw=False, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if raw else json.loads(data)


# =========================================================================== JLCDFM rules (served live)
LEVELS = ("Danger", "Warning", "Good", "not reported")


def dfm_level(value_mm, rng):
    """JLCDFM's level for a measured value: ranges are in mil, [danger_below, warning_below, good_below];
    a value at or above the last bound is not listed. Checked against the live demo's statistics (pad
    spacing 8/41/51, pad to board edge 16/32/52, PTH to trace 0/62/38 all reproduce)."""
    if value_mm is None or not rng:
        return None
    v = value_mm / MIL
    lo, mid, hi = rng
    if lo > hi:           # reversed range (larger is worse), e.g. tht2hole
        return "Danger" if v > lo else "Warning" if v > mid else "Good" if v > hi else "not reported"
    return "Danger" if v < lo else "Warning" if v < mid else "Good" if v < hi else "not reported"


def compact_rules(cfg):
    out = {}
    for mod, v in cfg.items():
        if not isinstance(v, dict):
            continue
        for name, r in (v.get("ranges") or {}).items():
            lang = r.get("language") or {}
            out[f"{mod}.{name}"] = {"title": (lang.get("title") or {}).get("en") or r.get("title"),
                                    "what": (lang.get("description") or {}).get("en"),
                                    "range_mil": r.get("range"), "type": r.get("type"), "unit": v.get("unit")}
    return out


# coupon kind -> [(JLCDFM rule key, manifest value key)]
DFM_MAP = {
    "track_space": [("jlc_analysis_signal_outer.lines", "width_mm"), ("jlc_analysis_signal_outer.line2line", "space_mm")],
    "annular_ring": [("jlc_analysis_signal_outer.pth_ar", "ring_mm")],
    "via": [("jlc_analysis_signal_outer.pth_ar", "ring_mm")],
    "drill": [("jlc_analysis_signal_outer.pth_ar", "ring_mm")],
    "copper_to_edge": [("jlc_analysis_signal_outer.line2edge", "edge_mm")],
    "silk_to_pad": [("jlc_analysis_ss.ss2pad", "silk_to_pad_mm")],
    "mask_dam": [("jlc_analysis_sm.bridge", "dam_mm"), ("jlc_analysis_signal_outer.pad2pad", "pad_gap_mm")],
    "silk_width": [("jlc_analysis_ss.ssl_w", "width_mm")],
    "hole_to_hole": [("jlc_analysis_drill.pth_2_pth", "gap_mm")],
    "npth": [],
}


def worst(levels):
    levels = [l for l in levels if l]
    return min(levels, key=LEVELS.index) if levels else None


# =========================================================================== reference claims and the preset
TOL = 0.0005


def reference_verdict(c, m):
    """(claim, verdict) from shared/reference/jlc/pcb-capabilities.en.md (2-layer, 1 oz, routed edge)."""
    k = c["kind"]
    if k == "track_space":
        v = min(m["width_mm"], m["space_mm"])
        return "min track/space 0.10/0.10 mm (1-2 layer, 1 oz) [P1]", "ok" if v >= 0.10 - TOL else "below"
    if k == "annular_ring":
        r = m["ring_mm"]
        return ("PTH ring 2-layer 1 oz: 0.18 abs. min, 0.25 recommended [P1]",
                "ok" if r >= 0.25 - TOL else "at/above min" if r >= 0.18 - TOL else "below")
    if k == "via":
        ok = m["drill_mm"] >= 0.15 - TOL and m["dia_mm"] >= m["drill_mm"] + 0.1 - TOL
        return "min via 0.15/0.25 mm, diameter >= hole + 0.1 [P1]", "ok" if ok else "below"
    if k == "drill":
        return "drill 0.15-6.3 mm on 2 layers [P1]", "ok" if m["drill_mm"] >= 0.15 - TOL else "below"
    if k == "copper_to_edge":
        return "copper to routed edge >= 0.2 mm [P1]", "ok" if m["edge_mm"] >= 0.2 - TOL else "below"
    if k == "silk_to_pad":
        return "pad to silkscreen 0.15 mm [P1]", "ok" if m["silk_to_pad_mm"] >= 0.15 - TOL else "below"
    if k == "mask_dam":
        return ("mask bridge 0.10 mm, green 1 oz [P1] (P2: 2-layer pad gap >= 0.2 mm)",
                "ok" if m["dam_mm"] >= 0.10 - TOL else "below")
    if k == "silk_width":
        return "silk line >= 0.15 mm [P1]", "ok" if m["width_mm"] >= 0.15 - TOL else "below"
    if k == "hole_to_hole":
        lim = 0.2 if c["nominal"].get("what") == "via-via" else 0.45
        return f"hole to hole: via-via 0.2, pad-pad 0.45 mm [P1]", "ok" if m["gap_mm"] >= lim - TOL else "below"
    if k == "npth":
        return "min NPTH 0.50 mm [P1]", "ok" if m["drill_mm"] >= 0.5 - TOL else "below"
    return "", None


def preset_verdict(c, m):
    """What the advisor's JLC preset (config/defaults.json via scripts/rules.py) says about a rule as
    tight as this coupon: worst of same/safer/tighter_ok/below_fab_min/unknown, or None (no rule)."""
    import rules
    preset = {r["kind"]: r for r in rules.get_jlc_preset().get("rules", [])}
    k, checks = c["kind"], []

    def judge(kind, attrs):
        if kind in preset:
            j = rules.judge_rule(kind, {a: f"{v:.4f}mm" for a, v in attrs.items()}, preset[kind])
            checks.append((kind, j["verdict"]))

    if k == "track_space":
        judge("Width", {"MINLIMIT": m["width_mm"]})
        judge("Clearance", {"GAP": m["space_mm"]})
    elif k in ("annular_ring", "via", "drill"):
        judge("MinimumAnnularRing", {"MINIMUMRING": m["ring_mm"]})
        if k != "annular_ring":
            judge("RoutingVias", {"HOLEWIDTH": m["drill_mm"], "WIDTH": m["dia_mm"]})
            judge("HoleSize", {"MINLIMIT": m["drill_mm"]})
    elif k == "silk_to_pad":
        judge("SilkToSolderMaskClearance", {"MINSILKSCREENTOMASKGAP": m["silk_to_mask_mm"]})
    elif k == "npth":
        judge("HoleSize", {"MINLIMIT": m["drill_mm"]})
    if not checks:
        return None, []
    order = ("below_fab_min", "unknown", "tighter_ok", "same", "safer")
    return min((v for _, v in checks), key=order.index), checks


def as_pass(kind, verdict):
    """Normalise the three sources to pass / warn / fail / None (no opinion)."""
    if verdict is None:
        return None
    if kind == "dfm":
        return {"Danger": "fail", "Warning": "warn", "Good": "pass", "not reported": "pass"}[verdict]
    if kind == "ref":
        return "fail" if verdict == "below" else "pass"
    # the coupon value always sits in a floor bound, so "unknown" means "tighter than the preset and no fab
    # minimum stored": the tool would flag it without saying whether JLC can make it
    return {"below_fab_min": "fail", "tighter_ok": "warn", "same": "pass", "safer": "pass", "unknown": "warn"}[verdict]


# =========================================================================== steps
def step_board(work, formats):
    out = work / "board"
    m = tb.generate(out, formats)
    return out, m


def step_parts(res):
    import jlc
    rows = []
    for code in dict.fromkeys(PART_CODES + [p["lcsc"] for p in tb.PARTS]):
        row = {"code": code}
        try:
            p = jlc.part_by_code(code)
            row["tool"] = {k: p.get(k) for k in ("mpn", "manufacturer", "package", "library_type", "stock")} if p else None
        except Exception as exc:
            row["tool_error"] = str(exc)
        try:
            d = http_get(f"{CART_API}/shoppingCart/smtGood/getComponentDetail?componentCode={code}")["data"]
            row["site"] = {"mpn": d.get("componentModelEn"), "manufacturer": d.get("componentBrandEn"),
                           "package": d.get("componentSpecificationEn"),
                           "library_type": {"base": "Basic", "expand": "Extended"}.get(d.get("componentLibraryType"),
                                                                                       d.get("componentLibraryType")),
                           "preferred": d.get("preferredComponentFlag"), "stock": d.get("stockCount"),
                           "name": d.get("componentName")}
        except Exception as exc:
            row["site_error"] = str(exc)
        t, s = row.get("tool"), row.get("site")
        if t and s:
            diffs = [k for k in ("mpn", "manufacturer", "package", "library_type") if (t.get(k) or "") != (s.get(k) or "")]
            st_t, st_s = t.get("stock") or 0, s.get("stock") or 0
            if abs(st_t - st_s) > max(10, 0.02 * max(st_t, st_s)):
                diffs.append("stock")
            row["agree"] = not diffs
            row["diffs"] = diffs
        if code in EXPECT:
            row["expected"] = EXPECT[code]
            row["expected_ok"] = bool(s and s.get("name") == EXPECT[code] and t and t.get("mpn") and t["mpn"] in EXPECT[code])
        rows.append(row)
    res["parts"] = rows


def step_dfm_rules(res, out):
    cfg_list = http_get(f"{DFM_API}/pcbDfm/getDfmConfigFile")["data"]
    f = cfg_list[0]
    raw = http_get(f"{DFM_API}/file/downloadByFileAccessId?fileAccessId={f['fileAccessId']}&fileType={f['fileType']}",
                   raw=True)
    cfg = json.loads(raw)
    rules_c = compact_rules(cfg)
    (out / "jlcdfm_rules.json").write_text(json.dumps({"source": f"{DFM_API}/pcbDfm/getDfmConfigFile",
                                                       "file_name": f.get("fileName"),
                                                       "sha256": hashlib.sha256(raw).hexdigest(),
                                                       "fetched": dt.datetime.now().isoformat(timespec="seconds"),
                                                       "level_rule": "value(mil) < r[0] Danger, < r[1] Warning, < r[2] Good, else not listed",
                                                       "rules": rules_c}, indent=1, ensure_ascii=False), encoding="utf-8")
    res["dfm_rules"] = {"count": len({r["title"] for r in rules_c.values()}), "file": f.get("fileName"),
                        "sha256": hashlib.sha256(raw).hexdigest()}
    return rules_c


def step_dfm_upload(res, out, zip_path, profile):
    """One upload attempt through jlcdfm.com's own page; records the login wall."""
    b = Browser(profile, size="1400,900")
    rec = {}
    try:
        ws = b.ws
        tap = Tap(ws, [f"{DFM_API}*"])
        ws.call("Page.navigate", url=DFM_HOME)
        tap.pump(10)
        accept_cookies(ws)
        g = tap.find("/getAll")
        rec["login_state"] = json.loads(g[0]["body"])["data"] if g and g[0].get("body") else None
        set_file(ws, zip_path)
        tap.pump(20)
        up = tap.find("/pcbDfm/uploadGerber")
        rec["upload"] = {"status": up[0]["status"], "body": (up[0]["body"] or "")[:500]} if up else None
        rec["redirected_to_login"] = bool(tap.find("/auth/login")) or "passport.jlcpcb.com" in (ws.js("location.href") or "")
        rec["page_after"] = (ws.js("location.href") or "")[:120]
        ws.shot(out / "jlcdfm_after_upload.png", clip={"x": 0, "y": 0, "width": 1400, "height": 700}, scale=0.6)
        rec["api"] = [{"url": r["url"][:140], "status": r["status"], "body": (r["body"] or "")[:300]} for r in tap.log
                      if "url" in r]
    finally:
        b.close()
    res["dfm_upload"] = rec


def step_dfm_demo_report(res, work, profile):
    """The demo viewer exports a real JLCDFM report PDF without an account; feed it to scripts/dfm.py."""
    dl = work / "dfm_demo_download"
    dl.mkdir(parents=True, exist_ok=True)
    b = Browser(profile, size="1600,1000")
    rec = {}
    try:
        ws = b.ws
        ws.call("Browser.setDownloadBehavior", behavior="allow", downloadPath=str(dl), eventsEnabled=True)
        ws.call("Page.navigate", url=DFM_DEMO)
        ws.pump(25)
        accept_cookies(ws)
        xy = ws.js("(()=>{const e=document.querySelector('[class*=pdf-export-icon]'); if(!e) return null; "
                   "const r=e.getBoundingClientRect(); return [r.x+r.width/2, r.y+r.height/2]})()")
        if not xy:
            raise RuntimeError("PDF export icon not found in the demo viewer")
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            ws.call("Input.dispatchMouseEvent", type=t, x=xy[0], y=xy[1], button="left", clickCount=1)
        end = time.time() + 90
        while time.time() < end and not any(p.suffix.lower() == ".pdf" for p in dl.iterdir()):
            ws.pump(2)
        ws.pump(2)
    finally:
        b.close()
    pdfs = [p for p in dl.iterdir() if p.suffix.lower() == ".pdf"]
    if not pdfs:
        raise RuntimeError("no PDF downloaded")
    pdf = pdfs[0]
    rec["pdf"] = {"name": pdf.name, "bytes": pdf.stat().st_size, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}
    import dfm
    try:
        ing = dfm.ingest_pdf(pdf, "jlc-testboard", kind="pcb")
        rec["ingest"] = {"ok": True, "slices": ing["slices"], "width": ing["index"]["width"],
                         "height": ing["index"]["height"], "stem": ing["stem"]}
        import pypdf
        r = pypdf.PdfReader(str(pdf))
        rec["pdf_layout"] = {"pages": len(r.pages), "images_on_page1": len(r.pages[0].images),
                             "text_chars": len(r.pages[0].extract_text() or "")}
    except Exception as exc:
        rec["ingest"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    res["dfm_demo_report"] = rec


def render_check(png, geo, board_w, board_h):
    """Drill hits and pads in JLC's top render. For each plated hole with its own round pad, the centroid of
    the transparent (hole) pixels is compared with the centroid of the whole pad (copper plus hole): if JLC
    put the drill where the copper is, the two coincide within a pixel. The offset against the board's own
    coordinates is reported too, but it also carries the render's framing (about 0.1 mm here)."""
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    W, H = im.size
    px = im.load()
    sx, sy = W / board_w, H / board_h

    def is_hole(p):
        return p[3] < 128

    def is_copper(p):
        return p[3] >= 128 and p[0] > 150 and 110 < p[1] < 185 and 100 < p[2] < 170

    def centroid(pts):
        return (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts)) if pts else None

    holes = []
    for h in geo["holes"]:
        ex, ey = h["x"] * sx, (board_h - h["y"]) * sy
        pad = min((p for p in geo["top_copper"] if p["kind"] == "flash" and abs(p["x"] - h["x"]) < 0.01
                   and abs(p["y"] - h["y"]) < 0.01), key=lambda p: p["w"], default=None)
        alone = pad is not None and not any(o is not h and math.hypot(o["x"] - h["x"], o["y"] - h["y"]) < pad["w"]
                                            for o in geo["holes"])
        R = int((pad["w"] if pad else h["d"]) / 2 * sx + 3)
        hole_px, cu_px = [], []
        for x in range(max(0, int(ex) - R), min(W, int(ex) + R + 1)):
            for y in range(max(0, int(ey) - R), min(H, int(ey) + R + 1)):
                if math.hypot(x + 0.5 - ex, y + 0.5 - ey) > R:
                    continue
                p = px[x, y]
                if is_hole(p):
                    hole_px.append((x + 0.5, y + 0.5))
                elif is_copper(p):
                    cu_px.append((x + 0.5, y + 0.5))
        row = {"x": round(h["x"], 3), "y": round(h["y"], 3), "d": round(h["d"], 3), "plated": h["plated"],
               "found": bool(hole_px)}
        hc = centroid(hole_px)
        if hc:
            row["vs_board_mm"] = round(math.hypot(hc[0] - ex, hc[1] - ey) / sx, 3)
            row["render_hole_mm"] = round(2 * math.sqrt(len(hole_px) / math.pi) / sx, 3)
        if hc and alone and cu_px and h["plated"]:
            pc = centroid(hole_px + cu_px)
            row["vs_pad_mm"] = round(math.hypot(hc[0] - pc[0], hc[1] - pc[1]) / sx, 3)
            row["render_pad_mm"] = round(2 * math.sqrt((len(hole_px) + len(cu_px)) / math.pi) / sx, 3)
            row["drawn_pad_mm"] = round(pad["w"], 3)
        holes.append(row)
    pads = []
    for p in geo["top_paste"]:
        x, y = int(p["x"] * sx), int((board_h - p["y"]) * sy)
        pads.append(is_copper(px[x, y]))
    found = [h for h in holes if h["found"]]
    vp = [h["vs_pad_mm"] for h in holes if "vs_pad_mm" in h]
    return {"render_px": [W, H], "px_per_mm": round(sx, 3), "holes_found": f"{len(found)}/{len(holes)}",
            "pads_checked": len(vp), "max_hole_vs_pad_mm": max(vp) if vp else None,
            "max_hole_vs_board_mm": max((h["vs_board_mm"] for h in found), default=None),
            "smd_pads_on_copper": f"{sum(pads)}/{len(pads)}", "holes": holes}


def step_quote(res, out, work, fmt, zip_path, profile, assembly=False):
    rec = {"format": fmt}
    b = Browser(profile, size="1600,1300")
    try:
        ws = b.ws
        tap = Tap(ws, [f"{CART_API}*", "*jlcpcb.com/api/*"], block=["passport.jlcpcb.com"])
        ws.call("Page.navigate", url=QUOTE)
        tap.pump(15)
        accept_cookies(ws)
        rec["upload_limit_text"] = ws.js("(document.body.innerText.match(/Only accept[^\\n]*/)||[''])[0]")
        set_file(ws, zip_path)
        t0 = time.time()
        while time.time() - t0 < 180 and not tap.find("/order/analysisGerber", '"head":"ok"'):
            tap.pump(4)
        ok = tap.find("/order/analysisGerber", '"head":"ok"')
        up = tap.find("/file/uploadGerber")
        rec["upload_status"] = up[0]["status"] if up else None
        if not ok:
            rec["error"] = "no analysisGerber result within 180 s"
            return rec
        rec["analysis_seconds"] = round(time.time() - t0)
        tap.pump(4)
        d = json.loads(ok[-1]["body"])["data"]
        rj = json.loads(d["resultJson"])
        fr = json.loads(rj["fileResult"])
        base = json.loads(fr["dfm_base_info"])
        fr["dfm_base_info"], rj["fileResult"], d["resultJson"] = base, fr, rj
        (out / f"quote_{fmt}_analysis.json").write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
        holes = base["drill_sum"]["holes"]
        rec.update({
            "detected_text": ws.js("(document.body.innerText.match(/Detected[^\\n]*/)||[''])[0]"),
            "size_mm": [float(d["pcsLength"]), float(d["pcsWidth"])], "layers": int(d["stencilLayer"]),
            "minLineWidth_mm": d["minLineWidth"], "minLineDist_mm": d["minLineDist"],
            "min_line_width_mm_exact": round(base["min_line_width"] * 25.4, 4),
            "min_line_spacing_mm_exact": round(base["min_line_spacing"] * 25.4, 4),
            "min_hole_mm": round(holes["min_dia"] * 25.4, 4), "min_ring_mm": round(holes["min_ring"] * 25.4, 4),
            "holes_total": holes["total"], "holes_npth": holes["total_npth"],
            "files": fr["file_list"], "smd_pads": base["smt"]["smd_pads"], "hole_pads": base["smt"]["hole_pads"],
            "dfmResultCode": rj.get("dfmResultCode"), "edatoolName": d.get("edatoolName"),
            "gerberResult": d.get("gerberResult"), "gerberFileError": d.get("gerberFileError"),
        })
        ws.js("window.scrollTo(0,0)")
        ws.pump(1)
        ws.shot(out / f"quote_{fmt}.png", clip={"x": 80, "y": 230, "width": 1010, "height": 310}, scale=0.8)
        png = http_get(f"{CART_API}/file/downImg?color=Green&uuid={d['technologyDiscernRecordNum']}"
                       f"&small=2&type=top&fromDemo=", raw=True)
        (out / f"quote_{fmt}_render_top.png").write_bytes(png)
        geo = tb.load(work / "board", fmt)
        rec["render_check"] = render_check(png, geo, tb.BOARD_W, tb.BOARD_H)
        if assembly:
            rec["assembly"] = assembly_next(ws, tap)
        else:
            rec["gerber_viewer"] = gerber_viewer(ws, tap)
    finally:
        b.close()
    return rec


def gerber_viewer(ws, tap):
    """Press the quote page's Gerber Viewer button and report where it goes (same tab or a new one)."""
    n0 = len(tap.log)
    before = {i["targetId"] for i in ws.call("Target.getTargets")["result"]["targetInfos"]}
    clicked = ws.js("(()=>{const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT); let n; "
                    "while(n=w.nextNode()){ if(n.nodeValue.trim()==='Gerber Viewer'){ n.parentElement.click(); return true } } "
                    "return false})()")
    tap.pump(8)
    new = [i["url"][:120] for i in ws.call("Target.getTargets")["result"]["targetInfos"]
           if i["targetId"] not in before and i["type"] == "page"]
    blocked = [r["blocked"] for r in tap.log[n0:] if "blocked" in r]
    goes = new + blocked
    return {"clicked": clicked, "goes_to": goes, "login_wall": any("passport.jlcpcb.com" in u for u in goes)}


FIND_ASSEMBLY = ("(()=>{const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT); let n; "
                 "while(n=w.nextNode()){ if(n.nodeValue.trim()==='PCB Assembly' && "
                 "!n.parentElement.closest('a,.submenu-panel,header,nav,footer')) return n.parentElement } return null})()")


def assembly_next(ws, tap):
    """Switch PCB Assembly on and press NEXT once; record where it goes. No cart, no order."""
    rec = {}
    rec["switch"] = ws.js(f"(()=>{{const e={FIND_ASSEMBLY}; if(!e) return 'not found'; e.click(); return 'on'}})()")
    tap.pump(4)
    txt = ws.js("document.body.innerText") or ""
    i = txt.find("PCB Assembly")
    rec["section_text"] = " | ".join(t.strip() for t in txt[i:i + 700].splitlines() if t.strip())[:600]
    n0 = len(tap.log)
    rec["next"] = ws.js("(()=>{const b=[...document.querySelectorAll('button')].find(e=>e.innerText.trim()==='NEXT');"
                        " if(!b) return 'no NEXT'; b.click(); return 'clicked'})()")
    tap.pump(10)
    after = tap.log[n0:]
    ci = [r for r in after if "/customer/customerInfo" in r.get("url", "")]
    rec["customerInfo"] = (ci[0]["body"] or "")[:200] if ci else None
    rec["login_wall"] = any("blocked" in r and "passport" in r["blocked"] for r in after)
    rec["calls"] = [r.get("url", r.get("blocked", ""))[:120] for r in after]
    return rec


def step_assembly_files(res, out, manifest):
    """BOM and CPL for the test board, written by the advisor's own exporters (export_bom.py, export_cpl.py)."""
    import store
    import export_bom
    import export_cpl
    project = "jlc-testboard"
    pdir = store.pdir(project)
    if (pdir / "bom-log.jsonl").exists():
        (pdir / "bom-log.jsonl").unlink()
    for p in manifest["parts"]:
        store.append(project, "bom-log.jsonl", {"line": p["ref"], "changes": {
            "refs": [p["ref"]], "value": p["value"], "package": p["footprint"], "lcsc": p["lcsc"]}})
    bom = export_bom.export(project, "jlc")
    # export_cpl reads a PcbDoc; the synthetic board has none, so hand it the same record shape
    pw, ph, off = tb.PAD_0603
    doc = {"components": [{"ref": p["ref"], "x_mm": p["x"], "y_mm": p["y"], "rotation": p["rotation"], "layer": "TOP"}
                          for p in manifest["parts"]],
           "pads": [{"ref": p["ref"], "x_mm": p["x"] + s * off, "y_mm": p["y"], "sx_mm": pw, "sy_mm": ph}
                    for p in manifest["parts"] for s in (-1, 1)]}
    stand_in = pdir / "TB1.PcbDoc.stand-in"
    stand_in.write_text("synthetic", encoding="utf-8")
    orig = export_cpl.read_pcbdoc, export_cpl.board_origin_mm
    export_cpl.read_pcbdoc, export_cpl.board_origin_mm = (lambda _p: doc), (lambda _p: (0.0, 0.0))
    try:
        cpl = export_cpl.export_cpl(project, pcb_path=stand_in)
    finally:
        export_cpl.read_pcbdoc, export_cpl.board_origin_mm = orig
    for f in (pdir / "exports").glob("*.csv"):
        shutil.copy(f, out / f.name)
    res["assembly_files"] = {"bom": bom, "cpl": cpl,
                             "bom_csv": (out / f"{project}_BOM_jlc.csv").read_text(encoding="utf-8"),
                             "cpl_csv": (out / f"{project}_cpl.csv").read_text(encoding="utf-8")}


# =========================================================================== comparison and report
def compare(manifest, rules_c):
    rows = []
    fa, fb = manifest["formats"].get("jlc-altium26"), manifest["formats"].get("outjob")
    for c in manifest["coupons"]:
        ma = (fa or fb)["measured"][c["id"]]
        mb = fb["measured"][c["id"]] if fb else None
        checks = []
        for key, vkey in DFM_MAP.get(c["kind"], []):
            r = (rules_c or {}).get(key)
            if not r:
                continue
            checks.append({"check": r["title"], "range_mil": r["range_mil"], "value_mm": ma.get(vkey),
                           "level_a": dfm_level(ma.get(vkey), r["range_mil"]),
                           "level_b": dfm_level(mb.get(vkey), r["range_mil"]) if mb else None})
        dfm_a = worst(ch["level_a"] for ch in checks)
        dfm_b = worst(ch["level_b"] for ch in checks)
        claim, ref = reference_verdict(c, ma)
        pv, pchecks = preset_verdict(c, ma)
        votes = {"jlcdfm": as_pass("dfm", dfm_a), "reference": as_pass("ref", ref), "preset": as_pass("preset", pv)}
        firm = {k: v for k, v in votes.items() if v is not None}
        fails = {k for k, v in firm.items() if v == "fail"}
        if len(firm) < 2:
            agree = "n/a"
        elif fails and len(fails) < len(firm):
            agree = "NO"
        elif not fails and any(v == "warn" for v in firm.values()):
            agree = "partly"
        else:
            agree = "yes"
        rows.append({"id": c["id"], "kind": c["kind"], "what": c["what"], "measured_a": ma, "measured_b": mb,
                     "jlcdfm_checks": checks, "jlcdfm_a": dfm_a, "jlcdfm_b": dfm_b,
                     "reference": {"claim": claim, "verdict": ref},
                     "preset": {"verdict": pv, "checks": pchecks}, "votes": votes, "agree": agree})
    return rows


def _fmt_vals(m):
    return ", ".join(f"{k.replace('_mm', '')} {v:g}" for k, v in m.items() if isinstance(v, (int, float)))


def write_report(out, res):
    L = []
    day = res["date"]
    L += [f"# JLC live check, {day}", "",
          "Generated by `python scripts/jlc_live.py` (not part of pytest). Synthetic 2-layer test board from "
          "`scripts/jlc_testboard.py` only; no real design was read or uploaded. No login, cart or order.", ""]
    # summary of access
    du = res.get("dfm_upload") or {}
    L += ["## What works without an account", "",
          "| Workflow | Anonymous? | Evidence |", "|---|---|---|"]
    if du:
        up = du.get("upload") or {}
        L.append(f"| JLCDFM upload and analysis (jlcdfm.com) | no | `getAll` says login={ (du.get('login_state') or {}).get('login') }; "
                 f"`pcbDfm/uploadGerber` HTTP {up.get('status')}; app then sends the browser to the passport login "
                 f"(redirected={du.get('redirected_to_login')}) |")
    if res.get("dfm_rules"):
        L.append(f"| JLCDFM built-in rule set (checks and thresholds) | yes | `pcbDfm/getDfmConfigFile` -> "
                 f"`{res['dfm_rules']['file']}`, {res['dfm_rules']['count']} distinct checks with thresholds, `jlcdfm_rules.json` |")
    dd = res.get("dfm_demo_report") or {}
    if dd:
        L.append(f"| JLCDFM report PDF (demo board only) | yes | demo viewer PDF export, {dd.get('pdf', {}).get('bytes')} bytes |")
    for q in res.get("quote", []):
        if q.get("size_mm"):
            L.append(f"| Quote page Gerber upload and parse, format `{q['format']}` | yes | `file/uploadGerber` + "
                     f"`order/analysisGerber`: {q.get('detected_text')} |")
    qa = next((q for q in res.get("quote", []) if q.get("assembly")), None)
    if qa:
        a = qa["assembly"]
        L.append(f"| Assembly: BOM/CPL upload and matching | no | PCB Assembly switch works; NEXT -> `customer/customerInfo` "
                 f"answers `{(a.get('customerInfo') or '')[:90]}`, then the passport login (login wall={a.get('login_wall')}) |")
    gv = next((q["gerber_viewer"] for q in res.get("quote", []) if q.get("gerber_viewer")), None)
    if gv:
        L.append(f"| Quote page Gerber Viewer | {'no' if gv['login_wall'] else 'see evidence'} | button leads to `{(gv['goes_to'] or ['nothing'])[0][:70]}` |")
    if res.get("parts"):
        L.append("| Part lookups (search and part detail) | yes | see Parts |")
    L += ["", "### What the owner must do for the account-only steps", "",
          "1. JLCDFM: sign in at https://jlcdfm.com (Sign In -> passport.jlcpcb.com, a JLCPCB account). Upload "
          "`TB1_jlc-altium26.zip` and `TB1_outjob.zip` from this folder, press DFM check, export the PDF (toolbar PDF icon), "
          "then run `python scripts/dfm.py ingest <project> <pdf>` and fill the JLCDFM column below with observed levels.",
          "2. Assembly: same account; on https://jlcpcb.com/quote upload the zip, switch PCB Assembly on, NEXT, upload "
          "`jlc-testboard_BOM_jlc.csv` and `jlc-testboard_cpl.csv`, read the matching page; stop before Save to Cart.",
          "3. A logged-in browser profile can be reused: close Edge and run `python scripts/jlc_live.py --profile "
          "\"%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\"`. The script then reports login=true; the logged-in "
          "upload/analysis capture itself is not automated yet.", ""]
    # board
    m = res["manifest"]
    L += ["## Test board", "",
          f"50 x 50 mm, 2 layers, {len(m['coupons'])} coupons, outline on `.GM1` (0.15 mm), three 0603 parts. "
          "Files: `manifest.json` (coupons, boxes, values measured back from the written files), the two zips.", "",
          "| Format | Gerber | Drill | Origin | Source |", "|---|---|---|---|---|"]
    for f, info in m["formats"].items():
        g, d = info["gerber"], info["drill"]
        L.append(f"| `{f}` | {g['units']} {g['int']}:{g['dec']}, {g['zeros']} | {d['units']} {d['int']}:{d['dec']}, {d['zeros']} | "
                 f"Gerber {info['gerber_origin']}, drill {info['drill_origin']} | {info['source'][:90]} |")
    # quote
    L += ["", "## JLCPCB quote page (anonymous upload)", "",
          "| Format | Detected | Min line / space (shown; exact) | Min hole / ring | Holes (NPTH) | SMD pads | Holes in JLC render | Drill vs pad centre (max) | SMD pads on copper |",
          "|---|---|---|---|---|---|---|---|---|"]
    for q in res.get("quote", []):
        if not q.get("size_mm"):
            L.append(f"| `{q['format']}` | ERROR: {q.get('error')} | | | | | | | |")
            continue
        rc = q.get("render_check") or {}
        L.append(f"| `{q['format']}` | {q['layers']} layers, {q['size_mm'][0]:g} x {q['size_mm'][1]:g} mm | "
                 f"{q['minLineWidth_mm']} / {q['minLineDist_mm']} ({q['min_line_width_mm_exact']} / {q['min_line_spacing_mm_exact']}) | "
                 f"{q['min_hole_mm']} / {q['min_ring_mm']} | {q['holes_total']} ({q['holes_npth']}) | {q['smd_pads'].get('top')} top | "
                 f"{rc.get('holes_found')} | {rc.get('max_hole_vs_pad_mm')} mm over {rc.get('pads_checked')} pads | {rc.get('smd_pads_on_copper')} |")
    if res.get("quote"):
        q0 = res["quote"][0]
        L += ["", f"Quote page upload limit text: \"{q0.get('upload_limit_text')}\". Renders: `quote_<format>_render_top.png` "
              f"(JLC's own image, {q0.get('render_check', {}).get('px_per_mm')} px/mm, so 1 px = "
              f"{1 / (q0.get('render_check', {}).get('px_per_mm') or 1):.3f} mm); parse: `quote_<format>_analysis.json`. "
              "The board has 15 holes, 1 of them NPTH. 'Drill vs pad centre' compares the centroid of each hole with "
              "the centroid of its own round pad in JLC's render; holes found off their pads would show as large values "
              "or as missing holes.", ""]
    # dfm
    L += ["## JLCDFM", ""]
    if du:
        L += [f"- Upload attempt: login state {du.get('login_state')}, upload answer `{json.dumps(du.get('upload'))[:200]}`, "
              f"page afterwards `{du.get('page_after')}`. Screenshot `jlcdfm_after_upload.png`."]
    if res.get("dfm_rules"):
        L += ["- Rule set: the web app serves its built-in rules (the template behind Rule settings > Built-in system rules). "
              "Ranges are mil: below r0 Danger, below r1 Warning, below r2 Good, else not listed. The live demo's statistics "
              "reproduce with this rule (pad spacing 8/41/51, pad to board edge 16/32/52)."]
    if dd:
        ing = dd.get("ingest") or {}
        L += [f"- Report PDF (JLCDFM demo board, exported by the live web app): {json.dumps(dd.get('pdf_layout'))}; "
              f"`scripts/dfm.py` ingest: {json.dumps(ing)}."]
    # comparison
    L += ["", "## Coupons: JLCDFM rule vs reference vs tool preset", "",
          "JLCDFM column = the level JLCDFM's live built-in rules give the coupon's drawn value (format a; format b in "
          "brackets when different). It is a prediction from JLC's own thresholds, not an observed upload result "
          "(upload needs an account). Agree: NO = one source fails what another passes.", "",
          "| Coupon | Drawn (mm) | JLCDFM rule -> level | Reference claim -> verdict | Tool preset | Agree? |",
          "|---|---|---|---|---|---|"]
    for r in res.get("compare", []):
        ch = "; ".join(f"{x['check']} {x['range_mil']} -> {x['level_a']}" + (f" [{x['level_b']}]" if x['level_b'] != x['level_a'] else "")
                       for x in r["jlcdfm_checks"]) or "no JLCDFM check"
        pv = r["preset"]["verdict"] or "no rule"
        if r["preset"]["checks"] and len(r["preset"]["checks"]) > 1:
            pv += " (" + ", ".join(f"{k} {v}" for k, v in r["preset"]["checks"]) + ")"
        L.append(f"| {r['id']} | {_fmt_vals(r['measured_a'])} | {ch} | {r['reference']['claim']} -> {r['reference']['verdict']} | "
                 f"{pv} | {r['agree']} |")
    nos = [r for r in res.get("compare", []) if r["agree"] == "NO"]
    if nos:
        L += ["", "Disagreements (pass/warn/fail per source):", ""]
        for r in nos:
            L.append(f"- {r['id']}: JLCDFM {r['votes']['jlcdfm']}, reference {r['votes']['reference']}, "
                     f"preset {r['votes']['preset']}")
    # parts
    if res.get("parts"):
        L += ["", "## Parts: scripts/jlc.py vs the site's part-detail endpoint", "",
              "| Code | jlc.py (MPN, maker, package, class, stock) | Site | Agree |", "|---|---|---|---|"]
        for p in res["parts"]:
            t, s = p.get("tool") or {}, p.get("site") or {}
            L.append(f"| {p['code']} | {t.get('mpn')}, {t.get('manufacturer')}, {t.get('package')}, {t.get('library_type')}, {t.get('stock')} | "
                     f"{s.get('name')}, {s.get('package')}, {s.get('library_type')}, {s.get('stock')} | "
                     f"{'yes' if p.get('agree') else 'NO ' + str(p.get('diffs') or p.get('tool_error') or p.get('site_error'))}"
                     f"{'; expected ' + p['expected'] + (' ok' if p.get('expected_ok') else ' MISMATCH') if p.get('expected') else ''} |")
    if res.get("assembly_files"):
        af = res["assembly_files"]
        L += ["", "## BOM and CPL (advisor exporters)", "", "```", af["bom_csv"].strip(), "```", "", "```", af["cpl_csv"].strip(), "```",
              "", "CPL coordinates are relative to the board corner (export_cpl.py). Format `jlc-altium26` puts the Gerbers on "
              "Altium's absolute origin, so the CPL and those Gerbers do not share an origin; untested at JLC (assembly needs an account)."]
    if res.get("errors"):
        L += ["", "## Errors", ""] + [f"- {e}" for e in res["errors"]]
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# =========================================================================== main
def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Live JLC check with the synthetic test board (anonymous)")
    ap.add_argument("--out", help="report folder (default docs/bench-runs/jlc-live-<date>)")
    ap.add_argument("--skip", default="", help="comma list of dfm,quote,assembly,parts")
    ap.add_argument("--mixed", action="store_true", help="also upload the jlc-altium26-mixed variant to the quote page")
    ap.add_argument("--profile", help="Edge user-data dir to reuse (Edge must be closed)")
    ap.add_argument("--rebuild", action="store_true",
                    help="no uploads: re-read results.json in --out, redo the part lookups and rewrite report.md")
    a = ap.parse_args(argv)
    skip = set(filter(None, a.skip.split(",")))
    day = dt.date.today().isoformat()
    out = pathlib.Path(a.out) if a.out else REPO / "docs" / "bench-runs" / f"jlc-live-{day}"
    out.mkdir(parents=True, exist_ok=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix="jlc-live-"))
    os.environ["PCB_ADVISOR_HOME"] = str(work / "ws")      # exporters, dfm.py and the jlc.py cache stay out of the repo
    import workspace
    workspace.load(reload=True)
    sessions = iter(range(1, 100))

    def profile():
        """A fresh profile per browser session, unless the user lends one (sessions then run one after another)."""
        return a.profile or str(work / f"edge-{next(sessions)}")
    res = {"date": day, "errors": []}

    def run(name, fn, *args, **kw):
        print(f"[{time.strftime('%H:%M:%S')}] {name} ...", flush=True)
        try:
            return fn(*args, **kw)
        except Exception as exc:
            res["errors"].append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"   failed: {exc}", flush=True)

    if a.rebuild:
        res = json.loads((out / "results.json").read_text(encoding="utf-8"))
        res["manifest"] = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        res["errors"] = [e for e in res.get("errors", []) if not e.startswith("parts")]
        if "parts" not in skip:
            run("parts", step_parts, res)
        rules_file = out / "jlcdfm_rules.json"
        rules_c = json.loads(rules_file.read_text(encoding="utf-8"))["rules"] if rules_file.exists() else None
        res["compare"] = compare(res["manifest"], rules_c)
        (out / "results.json").write_text(json.dumps({k: v for k, v in res.items() if k != "manifest"}, indent=1,
                                                     ensure_ascii=False, default=str), encoding="utf-8")
        write_report(out, res)
        shutil.rmtree(work, ignore_errors=True)
        print(f"report rebuilt: {out / 'report.md'}")
        return 0

    formats = list(tb.DEFAULT_FORMATS) + (["jlc-altium26-mixed"] if a.mixed else [])
    board_dir, manifest = step_board(work, formats)
    res["manifest"] = manifest
    shutil.copy(board_dir / "manifest.json", out / "manifest.json")
    for f in formats:
        shutil.copy(board_dir / f"TB1_{f}.zip", out / f"TB1_{f}.zip")
    zips = {f: board_dir / f"TB1_{f}.zip" for f in formats}

    rules_c = None
    if "parts" not in skip:
        run("parts", step_parts, res)
    if "dfm" not in skip:
        rules_c = run("jlcdfm rules", step_dfm_rules, res, out)
        run("jlcdfm upload attempt", step_dfm_upload, res, out, zips["jlc-altium26"], profile())
        run("jlcdfm demo report -> dfm.py", step_dfm_demo_report, res, work, profile())
    if "quote" not in skip:
        res["quote"] = []
        for f in formats:
            q = run(f"quote {f}", step_quote, res, out, board_dir.parent, f, zips[f], profile(),
                    assembly=(f == "jlc-altium26" and "assembly" not in skip))
            if q:
                res["quote"].append(q)
    if "assembly" not in skip:
        run("assembly files", step_assembly_files, res, out, manifest)
    res["compare"] = compare(manifest, rules_c)
    (out / "results.json").write_text(json.dumps({k: v for k, v in res.items() if k != "manifest"}, indent=1,
                                                 ensure_ascii=False, default=str), encoding="utf-8")
    write_report(out, res)
    shutil.rmtree(work, ignore_errors=True)
    print(f"report: {out / 'report.md'}" + (f"  ({len(res['errors'])} step errors)" if res["errors"] else ""))
    return 0 if not res["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
