"""Renders mock-ups of the planned workspace (the screens in docs/UI-SPEC.md) as PNG images for the presentation.
Same look as ui/index.html (tokens copied from it). Output: img/mock_<name>.png, 1440x900 at 2x.
Usage: python mock_ui.py        needs playwright (Edge, headless) and internet for the IBM Plex fonts (falls back to Segoe UI).
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
IMG = HERE / "img"

CSS = """
:root{--bg:#eef1f6;--panel:#fff;--panel2:#f5f7fb;--line:#d6dce8;--line2:#e7ebf2;--ink:#141a26;--ink2:#323c50;--dim:#5b667b;
--accent:#2148c9;--accent-soft:#e3e9fb;--ok:#167a46;--ok-soft:#e1f2e8;--warn:#8f5d00;--warn-soft:#fbefd2;--bad:#b8322a;--bad-soft:#fbe4e2;
--nav:#17203a;--nav-ink:#dfe5f3;--nav-dim:#94a0bd;--nav-sel:#2a3657;--net-soft:#f0e7fb;--net:#6b2fb3;
--f-ui:"IBM Plex Sans","Segoe UI",Arial,sans-serif;--f-mono:"IBM Plex Mono",Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:var(--f-ui);color:var(--ink);font-size:13px}
.app{display:grid;grid-template-columns:372px 1fr 216px;gap:12px;padding:12px;height:800px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;box-shadow:0 1px 2px rgba(20,26,38,.06)}
.chat{display:flex;flex-direction:column;overflow:hidden}
.chat-h{padding:12px;border-bottom:1px solid var(--line2);display:flex;gap:8px}
.pill{border:1px solid var(--line);border-radius:8px;padding:7px 10px;background:var(--panel2);font-weight:600;font-size:12.5px;flex:1}
.btn{border:1px solid var(--line);border-radius:7px;padding:5px 10px;background:#fff;font-size:12px;color:var(--ink2);white-space:nowrap;display:inline-block}
.btn.pri{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.msgs{flex:1;padding:12px;display:flex;flex-direction:column;gap:10px;overflow:hidden}
.ctx{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--panel2);font-size:12px;line-height:1.45}
.ctx b{display:block;font-size:13px}.ctx .att{margin-top:6px;display:inline-flex;gap:6px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:6px;padding:3px 8px;font-family:var(--f-mono);font-size:11px}
.me{align-self:flex-end;background:var(--accent-soft);border-radius:12px;padding:9px 12px;max-width:88%;line-height:1.45;font-size:13px}
.ag{line-height:1.5;font-size:13px}.ag .who{font-size:11px;color:var(--dim);font-weight:600;margin-bottom:2px}
.src{display:inline-block;background:var(--accent-soft);color:var(--accent);border-radius:9px;padding:0 7px;font-size:11px;font-weight:600;margin:0 2px;vertical-align:1px;white-space:nowrap}
.next{border:1px solid #b9c7f3;background:#f1f5ff;border-radius:10px;padding:9px 12px;font-size:12.5px;line-height:1.45}
.next b{color:var(--accent)}
.chips{display:flex;gap:6px;padding:0 12px 8px;flex-wrap:wrap}.chip{border:1px solid var(--line);border-radius:12px;padding:3px 10px;font-size:11.5px;color:var(--ink2);background:#fff}
.inp{display:flex;gap:8px;padding:0 12px 12px}.inp div{flex:1;border:1px solid var(--line);border-radius:9px;padding:9px 11px;color:#8b95a8;font-size:13px}
.main{display:flex;flex-direction:column;overflow:hidden}
.tabs{display:flex;gap:12px;padding:0 14px;border-bottom:1px solid var(--line2);height:46px;align-items:flex-end}
.tab{padding:0 0 11px;color:var(--dim);font-size:12px;display:flex;gap:5px;align-items:center;white-space:nowrap;border-bottom:2px solid transparent}
.tab i{font-style:normal;width:18px;height:18px;border-radius:50%;border:1px solid #aab3c6;font-size:10.5px;display:inline-flex;align-items:center;justify-content:center}
.tab.on{color:var(--ink);font-weight:600;border-color:var(--accent)}.tab.on i{background:var(--accent);border-color:var(--accent);color:#fff}
.body{padding:16px 18px;flex:1;overflow:hidden;position:relative}
h2{margin:0 0 4px;font-size:18px}.sub{color:var(--dim);font-size:12.5px;margin-bottom:12px;line-height:1.45}
.nav{background:var(--nav);border-radius:12px;color:var(--nav-ink);padding:14px 10px;display:flex;flex-direction:column;gap:2px}
.nav .logo{font-weight:700;font-size:15px;padding:4px 8px 14px}.nav .cap{font-size:10.5px;letter-spacing:.08em;color:var(--nav-dim);padding:12px 8px 4px}
.nav .it{padding:8px 10px;border-radius:7px;font-size:13px;display:flex;justify-content:space-between}.nav .it.on{background:var(--nav-sel);font-weight:600;color:#fff}
.nav .it em{font-style:normal;color:var(--nav-dim);font-size:11.5px}
.tag{display:inline-block;border-radius:9px;padding:1px 8px;font-size:11px;font-weight:600}
.ok{background:var(--ok-soft);color:var(--ok)}.warn{background:var(--warn-soft);color:var(--warn)}.bad{background:var(--bad-soft);color:var(--bad)}.info{background:var(--accent-soft);color:var(--accent)}
table{border-collapse:collapse;width:100%}th{text-align:left;font-size:11px;color:var(--dim);font-weight:600;padding:7px 8px;border-bottom:1px solid var(--line)}
td{padding:7px 8px;border-bottom:1px solid var(--line2);font-size:12.5px;vertical-align:middle}.mono{font-family:var(--f-mono);font-size:12px}
tr.sel td{background:var(--accent-soft)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.box{border:1px solid var(--line);border-radius:10px;background:#fff}
.lbl{font-size:11px;color:var(--dim);font-weight:600;letter-spacing:.04em;margin-bottom:6px}
"""

TABS = ["Idea", "Parts", "Schematic", "Placement", "Routing", "Layers", "Outputs", "Manufacturer"]


def chat(title, ctx, msgs, nxt, chips):
    m = ""
    for who, t in msgs:
        m += f'<div class="me">{t}</div>' if who == "me" else f'<div class="ag"><div class="who">PCB Advisor</div>{t}</div>'
    return (f'<div class="card chat"><div class="chat-h"><div class="pill">☰  {title}</div><div class="btn">+ New</div></div>'
            f'<div class="msgs">{ctx}{m}<div class="next"><b>Next step</b><br>{nxt}</div></div>'
            f'<div class="chips">{"".join(f"<span class=chip>{c}</span>" for c in chips)}</div>'
            f'<div class="inp"><div>Message the agent… (Enter to send)</div><span class="btn pri" style="padding:9px 16px">Send</span></div></div>')


def nav(active):
    items = [("Workspace", "", "ws"), ("Project library", "28", "lib"), ("Knowledge base", "18", "kb"), ("Skills", "12", "sk"), ("Settings", "", "set")]
    h = '<div class="nav"><div class="logo">▣  PCB Advisor</div><div class="cap">PROJECTS</div>'
    h += '<div class="it on"><span>● LTE Tracker</span></div><div class="it"><span>● demo</span></div><div class="it"><span>+ New project</span></div>'
    h += '<div class="cap">LTE TRACKER</div>'
    for n, c, k in items:
        h += f'<div class="it {"on" if k == active else ""}"><span>{n}</span><em>{c}</em></div>'
    return h + "</div>"


def page(active_tab, chat_html, body, nav_active="ws", sub=None):
    tabs = "".join(f'<div class="tab {"on" if i == active_tab else ""}"><i>{i + 1}</i>{t}</div>' for i, t in enumerate(TABS)) if active_tab is not None else ""
    main = f'<div class="card main"><div class="tabs">{tabs}</div><div class="body">{body}</div></div>'
    return f'<html><head><meta charset="utf-8"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap"><style>{CSS}</style></head><body><div class="app">{chat_html}{main}{nav(nav_active)}</div></body></html>'


# ------------------------------------------------------------------ 1 idea
def block_diagram():
    def node(x, y, w, h, t1, t2, fill, stroke, dash=False, sel=False):
        d = ' stroke-dasharray="6 4"' if dash else ""
        s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="{2.5 if sel else 1.6}"{d}/>'
        s += f'<text x="{x + w / 2}" y="{y + h / 2 - 3}" text-anchor="middle" font-family="IBM Plex Mono,Consolas" font-weight="600" font-size="12" fill="{stroke}">{t1}</text>'
        s += f'<text x="{x + w / 2}" y="{y + h / 2 + 14}" text-anchor="middle" font-family="IBM Plex Sans,Segoe UI" font-size="11" fill="#475069">{t2}</text>'
        if sel:
            for hx, hy in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]:
                s += f'<rect x="{hx - 4}" y="{hy - 4}" width="8" height="8" fill="#fff" stroke="#2148c9" stroke-width="1.5"/>'
        return s

    def edge(pts, label, color, lx, ly, dash=False):
        d = ' stroke-dasharray="6 4"' if dash else ""
        p = " ".join(f"{a},{b}" for a, b in pts)
        s = f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="1.8"{d} marker-end="url(#ar{color[1:]})"/>'
        s += f'<rect x="{lx - 26}" y="{ly - 9}" width="52" height="18" rx="9" fill="#fff" stroke="{color}"/><text x="{lx}" y="{ly + 4}" text-anchor="middle" font-family="IBM Plex Mono,Consolas" font-size="10" fill="{color}">{label}</text>'
        return s

    cols = ["#d27a12", "#2148c9", "#6b2fb3", "#167a46", "#475069"]
    defs = "".join(f'<marker id="ar{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>' for c in cols)
    svg = f'<svg width="770" height="300" viewBox="0 0 770 300"><defs>{defs}</defs>'
    svg += '<rect x="150" y="14" width="600" height="272" rx="12" fill="none" stroke="#2e8a78" stroke-width="1.4" stroke-dasharray="7 5"/><text x="162" y="30" font-family="IBM Plex Mono,Consolas" font-size="10" fill="#2e8a78">custom 4-layer PCB</text>'
    svg += edge([(110, 150), (170, 150)], "1S", "#d27a12", 140, 150)
    svg += edge([(280, 150), (330, 150)], "3V3", "#d27a12", 305, 150)
    svg += edge([(440, 150), (500, 150)], "UART", "#2148c9", 470, 150)
    svg += edge([(225, 122), (225, 70), (555, 70), (555, 118)], "3V8", "#d27a12", 390, 70)
    svg += edge([(610, 150), (672, 150)], "RF", "#6b2fb3", 641, 150)
    svg += edge([(555, 182), (555, 232)], "UART", "#475069", 555, 207, dash=True)
    svg += node(8, 122, 104, 56, "Li-ion 1S", "battery", "#fff7e0", "#d27a12")
    svg += node(170, 122, 110, 56, "Power", "+3V8 / +3V3", "#fff7e0", "#d27a12")
    svg += node(330, 122, 110, 56, "STM32G0", "main MCU", "#eef3ff", "#2148c9")
    svg += node(500, 120, 112, 60, "A7670G", "LTE Cat-1 modem", "#f4ecfd", "#6b2fb3", sel=True)
    svg += node(674, 122, 84, 56, "U.FL", "antenna", "#f4ecfd", "#6b2fb3")
    svg += node(500, 232, 112, 48, "GNSS", "not chosen yet", "#f7f8fb", "#475069", dash=True)
    svg += '</svg>'
    return svg


def idea():
    body = '<h2>Idea</h2><div class="sub">A bike tracker that reports its location every 5 minutes and runs a week on one charge. Edit the diagram together with the agent.</div>'
    body += '<div style="display:flex;gap:8px;margin-bottom:10px"><span class="btn">Open the conversation</span><span class="btn pri">Next: Parts</span></div>'
    body += '<div class="box" style="padding:10px 12px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px"><b style="font-size:13px">Block diagram</b>'
    body += '<span style="display:flex;gap:6px"><span class="btn">+ Block</span><span class="btn">Link</span><span class="btn">Delete</span><span class="tag ok" style="align-self:center">Agent has the latest version</span></span></div>'
    body += block_diagram()
    body += '<div style="position:absolute;left:430px;top:224px;background:#fff;border:1px solid var(--line);border-radius:8px;box-shadow:0 6px 18px rgba(20,26,38,.15);padding:6px 8px;display:flex;gap:6px"><span class="btn">Rename</span><span class="btn">Change part</span><span class="btn pri">Ask about this</span></div></div>'
    body += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px">'
    body += '<div class="box" style="padding:10px 12px;font-size:12.5px;line-height:1.7"><div class="lbl">AGREED · FREE TEXT</div><b>Cellular</b> LTE Cat-1, SIMCom A7670G<br><b>Power</b> 1S Li-ion, +3V8 for the modem<br><b>MCU</b> STM32G0, UART to the modem</div>'
    body += '<div class="box" style="padding:10px 12px;font-size:12.5px;line-height:1.7"><div class="lbl">STILL OPEN</div>Battery size and charging current<br>GNSS module: not chosen yet<br>Enclosure: waterproof or not</div></div>'
    c = chat("Idea refinement", '<div class="ctx"><b>Stage 1 · Idea</b>LTE Tracker · 1 sheet · 19 BOM lines</div>',
             [("me", "Can we add a GNSS module?"),
              ("ag", 'Yes. I added a dashed <b>GNSS</b> block under the modem. It is not chosen yet. Does that match what you meant?'),
              ("me", "Yes. Link it to the modem over UART."),
              ("ag", 'Done. The diagram is updated on both sides, so we are using the same names. <span class="src">idea notes</span>')],
             "Confirm the diagram, then open <b>Parts</b> to pick the modem and the MCU.", ["What is still open?", "Summarize the idea"])
    return page(0, c, body)


# ------------------------------------------------------------------ 2 parts
def parts():
    rows = [("U4", "A7670G-LABE", "LTE Cat-1 modem", 1204, "ok"), ("U1", "STM32G030F6P6", "Main MCU", 3210, "ok"), ("U5", "TXS0104EPWR", "1.8 V ↔ 3.3 V level shifter", 5880, "ok"),
            ("Q3", "2N7002", "Switches the modem power key", 24000, "ok"), ("D30", "ESD56301D05", "ESD protection, battery line", 0, "bad"),
            ("D31", "ESDA6V1W5", "ESD protection, SIM lines", 140, "warn"), ("J6", "U.FL-R-SMT-1", "Antenna connector", 8600, "ok"),
            ("J7", "786800001", "Nano-SIM holder", 2100, "ok"), ("C30", "TAJD337K006RNJ", "Bulk cap for transmit peaks", 310, "ok")]
    body = '<h2>Parts</h2><div class="sub">Each row has a datasheet, live stock from the manufacturer and a short note on what the part does. Click a row to chat about it.</div>'
    body += '<div style="display:flex;gap:8px;margin-bottom:10px"><span class="btn">Check stock</span><span class="btn">Compare prices</span><span class="btn">Export JLC BOM</span>'
    body += '<span class="tag info" style="align-self:center">19 lines</span><span class="tag ok" style="align-self:center">$18.39 / board</span><span class="tag bad" style="align-self:center">1 out of stock</span></div>'
    body += '<div class="box"><table><tr><th>Ref</th><th>Part</th><th>Role in the circuit</th><th>Datasheet</th><th>Stock</th><th></th></tr>'
    for r, p, role, st, k in rows:
        sel = " class=sel" if r == "U4" else ""
        stock = {"ok": f'<span class="dot" style="background:#167a46"></span>{st:,}', "warn": f'<span class="dot" style="background:#c98a00"></span>{st:,} · low',
                 "bad": '<span class="dot" style="background:#b8322a"></span>0 · out'}[k]
        act = '<span class="btn pri" style="padding:3px 9px">Alternatives</span>' if k == "bad" else '<span class="btn" style="padding:3px 9px">⇄ Swap</span>'
        body += f'<tr{sel}><td class="mono" style="color:var(--net);font-weight:600">{r}</td><td class="mono">{p}</td><td>{role}</td><td><span class="src">PDF ↗</span></td><td>{stock}</td><td style="white-space:nowrap">{act} <span class="btn" style="padding:3px 9px">💬 Ask</span></td></tr>'
    body += '</table></div>'
    c = chat("Part chat · U4", '<div class="ctx"><b>U4 · A7670G-LABE</b>LTE Cat-1 modem, 1,204 in stock<br><span class="att">📎 A7670G hardware guide.pdf  attached</span></div>',
             [("me", "Can the modem run straight from the battery?"),
              ("ag", 'Yes. The modem supply input accepts a single Li-ion cell directly, so no extra regulator is needed on that rail. <span class="src">datasheet p.14</span> Keep the bulk capacitor close to the supply pins. <span class="src">datasheet p.15</span>'),
              ("me", "What does D30 protect?"),
              ("ag", 'D30 clamps spikes on the battery line. It is out of stock, so I listed two alternatives in the table.')],
             "Replace <b>D30</b> with an alternative, then move on to the <b>Schematic</b>.", ["Why this part?", "Find an alternative"])
    return page(1, c, body)


# ------------------------------------------------------------------ 3 schematic
def schematic():
    src = (IMG / "ui_schematic.png").as_uri()
    body = '<h2>Schematic</h2><div class="sub">Generated from the project data. Click a part or a connection to ask about it.</div>'
    body += '<div style="display:flex;gap:8px;margin-bottom:8px"><span class="btn info" style="background:var(--accent-soft);color:var(--accent);font-weight:600">03 Modem</span><span class="btn">01 Power</span><span class="btn">02 MCU</span></div>'
    body += f'<div class="box" style="height:470px;overflow:hidden;position:relative"><img src="{src}" style="position:absolute;left:-418px;top:-170px;width:1440px">'
    body += '<div style="position:absolute;left:84px;top:36px;width:120px;height:222px;border:2px solid #2148c9;border-radius:6px;background:rgba(33,72,201,.07)"></div>'
    body += '<div style="position:absolute;left:210px;top:60px;width:300px;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:0 8px 24px rgba(20,26,38,.2);padding:12px 14px">'
    body += '<div style="font-weight:700;font-size:13px">U4 · SIMCom A7670G</div><div style="color:var(--dim);font-size:12px;margin:2px 0 10px">Clicked: pin 9, RESET_N</div>'
    body += '<div style="display:flex;flex-direction:column;gap:6px"><span class="btn pri">What is this pin for?</span><span class="btn">Is this connection correct?</span><span class="btn">Show it in the datasheet</span></div></div></div>'
    c = chat("Schematic · U4 pin 9", '<div class="ctx"><b>Selected: U4 · RESET_N</b>From the schematic preview<br><span class="att">📎 A7670G hardware guide.pdf  attached</span></div>',
             [("me", "What is this pin for?"),
              ("ag", 'RESET_N restarts the modem. The pin is active low and has an internal pull-up, so it can stay open when you do not need a hardware reset. <span class="src">datasheet p.22</span> Here it is wired to a test point.')],
             "Open <b>Placement & Routing</b> to see where U4 sits on the board.", ["What is still open?", "Check this sheet"])
    return page(2, c, body)


# ------------------------------------------------------------------ 4 placement and routing
def board(mode="routing"):
    W, H = 520, 420
    s = f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="8" fill="#fbfcfe" stroke="#17203a" stroke-width="2.5"/>'
    rooms = [(16, 16, 150, 120, "POWER", "#fdf0cf"), (178, 16, 210, 120, "MCU", "#e3e9fb"), (400, 16, 104, 190, "CONNECTORS", "#e7ebf2"),
             (16, 150, 150, 150, "MODEM", "#e6f0ff"), (178, 150, 210, 150, "SIM + ANTENNA", "#f0e7fb"), (16, 314, 372, 92, "SENSORS + TEST POINTS", "#e1f2e8")]
    for x, y, w, h, n, c in rooms:
        s += f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{c}" stroke="#c7cfdf" stroke-dasharray="4 3"/><text x="{x + 8}" y="{y + 16}" font-family="IBM Plex Mono,Consolas" font-size="9.5" fill="#5b667b" font-weight="600">{n}</text>'
    parts = [(34, 52, 46, 30, "L1"), (96, 60, 26, 22, "U2"), (36, 96, 22, 16, "C30"), (200, 42, 86, 60, "U1"), (300, 56, 26, 18, "C31"), (330, 78, 18, 14, "C32"),
             (34, 176, 100, 76, "U4"), (200, 176, 60, 40, "J7"), (280, 190, 40, 26, "D31"), (330, 176, 40, 30, "J6"), (418, 40, 70, 40, "J1"), (418, 100, 70, 40, "J2"),
             (36, 336, 40, 24, "U3"), (100, 340, 30, 22, "TP1"), (150, 340, 30, 22, "TP2")]
    for x, y, w, h, n in parts:
        sel = n == "C31"
        s += f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="#17203a" opacity="{1 if sel or w > 40 else .85}"/><text x="{x + w / 2}" y="{y + h / 2 + 3.5}" text-anchor="middle" font-family="IBM Plex Mono,Consolas" font-size="9" fill="#fff">{n}</text>'
    nets = [("#d27a12", 3.2, "M80,67 L96,67 M122,71 L200,71"), ("#d27a12", 3.2, "M122,71 L122,140 L84,140 L84,176"), ("#c0392b", 2, "M286,72 L300,72"), ("#c0392b", 2, "M326,66 L360,66 L360,176"),
            ("#6b2fb3", 2.4, "M134,214 L200,214"), ("#6b2fb3", 2.4, "M260,196 L280,196 M320,196 L330,196"), ("#2148c9", 1.6, "M243,102 L243,176"), ("#2148c9", 1.6, "M200,80 L150,80 L150,176")]
    for c, w, d in (nets if mode == "routing" else []):
        s += f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round" opacity=".9"/>'
    s += '<rect x="294" y="50" width="38" height="30" rx="5" fill="none" stroke="#2148c9" stroke-width="2.2"/>'
    s += '<g transform="translate(250,100)"><rect width="140" height="40" rx="8" fill="#17203a"/><text x="70" y="17" text-anchor="middle" font-family="IBM Plex Sans" font-size="11" font-weight="700" fill="#fff">C31 · 1 µF</text><text x="70" y="31" text-anchor="middle" font-family="IBM Plex Sans" font-size="10" fill="#cbd5e1">decoupling for U1 · 3 mm</text></g>'
    return s + "</svg>"


def placement():
    body = '<h2>Placement</h2><div class="sub">The plan, before Altium: which room each part goes to, in what order, and which way each connector faces.</div>'
    body += '<div style="display:flex;gap:6px;margin-bottom:10px"><span class="btn" style="background:var(--accent-soft);color:var(--accent);font-weight:600">Rooms</span><span class="btn">Top</span><span class="btn">Bottom</span><span class="btn">Connector directions</span><span class="btn">Keep-outs</span></div>'
    body += '<div style="display:grid;grid-template-columns:524px 1fr;gap:12px"><div class="box" style="padding:0;overflow:hidden">' + board("rooms") + '</div>'
    body += '<div style="display:flex;flex-direction:column;gap:10px"><div class="box" style="padding:10px 12px"><div class="lbl">PLACEMENT ORDER</div>'
    for i, (n, d) in enumerate([("Connectors on the edges", "J1 and J2 face the outside of the case"), ("MCU in the middle", "short tracks to every room"), ("Decoupling next to each supply pin", "within 3 mm"), ("Modem near the antenna edge", "RF track as short as possible"), ("Sensors and test points last", "away from the noisy rooms")]):
        body += f'<div style="display:flex;gap:8px;padding:5px 0;border-top:{"0" if i == 0 else "1px solid var(--line2)"}"><span class="tag info" style="align-self:flex-start">{i + 1}</span><div style="font-size:12px;line-height:1.35"><b>{n}</b><br><span style="color:var(--dim)">{d}</span></div></div>'
    body += '</div><div class="box" style="padding:10px 12px;font-size:12px;line-height:1.5"><div class="lbl">SELECTED</div><b>C31 · 1 µF</b><br><span style="color:var(--dim)">Decoupling for U1. Place within 3 mm of the supply pin.</span><br><span class="src" style="margin:6px 0 0">datasheet p.31</span></div></div></div>'
    c = chat("Placement · C31", '<div class="ctx"><b>Selected: C31 · 1 µF</b>On the plan, near U1 (MCU)</div>',
             [("me", "Why is this capacitor so close to the MCU?"),
              ("ag", 'It supplies the fast current spikes of the MCU. The longer the track, the less it helps, so the datasheet asks for it right next to the supply pin. <span class="src">datasheet p.31</span>'),
              ("me", "Why is the modem at the board edge?"),
              ("ag", 'The antenna connector sits on that edge. The shorter the RF track, the less signal is lost.')],
             "Happy with the rooms? Open <b>Routing</b> to plan the critical nets.", ["Why this room?", "What is a keep-out?"])
    return page(3, c, body)


def routing():
    body = '<h2>Routing</h2><div class="sub">How the critical nets run. Click a net to ask why. The student routes it in Altium.</div>'
    body += '<div style="display:flex;gap:6px;margin-bottom:10px"><span class="btn" style="background:var(--accent-soft);color:var(--accent);font-weight:600">Critical nets</span><span class="btn">All nets</span><span class="btn">Top</span><span class="btn">Bottom</span></div>'
    body += '<div style="display:grid;grid-template-columns:524px 1fr;gap:12px"><div class="box" style="padding:0;overflow:hidden">' + board("routing") + '</div>'
    body += '<div style="display:flex;flex-direction:column;gap:10px"><div class="box" style="padding:10px 12px"><div class="lbl">ROUTING PLAN</div>'
    for i, (n, d, c) in enumerate([("+3V8 supply", "wide track, short, to the modem first", "#d27a12"), ("RF antenna", "50 Ω, no vias, ground around", "#6b2fb3"), ("USB D+ / D−", "differential pair, matched length", "#2148c9"), ("UART to modem", "keep short, away from RF", "#c0392b")]):
        body += f'<div style="display:flex;gap:8px;padding:5px 0;border-top:{"0" if i == 0 else "1px solid var(--line2)"}"><span style="width:10px;height:10px;border-radius:2px;background:{c};margin-top:4px;flex:none"></span><div style="font-size:12px;line-height:1.35"><b>{n}</b><br><span style="color:var(--dim)">{d}</span></div></div>'
    body += '</div><div class="box" style="padding:10px 12px;font-size:12px;line-height:1.5"><div class="lbl">SELECTED NET</div><b>RF antenna</b><br><span style="color:var(--dim)">Keep it on one layer, with ground on both sides and a solid plane below.</span><br><span class="src" style="margin:6px 0 0">modem hardware guide p.22</span></div></div></div>'
    c = chat("Routing · RF antenna", '<div class="ctx"><b>Selected: RF antenna</b>J7 to the modem, 50 Ω</div>',
             [("me", "Why does the RF track avoid vias?"),
              ("ag", 'Each via adds inductance and breaks the 50 Ω line. The plan keeps that track on one layer. <span class="src">modem hardware guide p.22</span>'),
              ("me", "Which net do I route first?"),
              ("ag", 'The RF track, then the +3V8 supply to the modem, then USB. The easy nets go last.')],
             "Happy with the nets? Open <b>Layers</b> to check the stack-up.", ["Show the route order", "Why a differential pair?"])
    return page(4, c, body)


def layers():
    body = '<h2>Layers</h2><div class="sub">The stack-up the plan relies on, taken from the manufacturer\'s 4-layer board.</div>'
    rows = [("L1 · Top", "#d27a12", 14, "35 µm"), ("Prepreg", "#e7d9a8", 22, "0.21 mm"), ("L2 · GND plane", "#6b2fb3", 14, "17 µm"),
            ("Core", "#c9d3e6", 46, "1.065 mm"), ("L3 · +3V8 and signals", "#2148c9", 14, "17 µm"), ("Prepreg", "#e7d9a8", 22, "0.21 mm"), ("L4 · Bottom", "#d27a12", 14, "35 µm")]
    svg = '<svg width="470" height="230">'
    y = 6
    for n, c, h, th in rows:
        svg += f'<rect x="6" y="{y}" width="190" height="{h}" fill="{c}" rx="2"/>'
        svg += f'<text x="206" y="{y + h / 2 + 4}" font-family="IBM Plex Sans" font-size="12" font-weight="{600 if h < 20 else 400}" fill="#141a26">{n}</text><text x="440" y="{y + h / 2 + 4}" text-anchor="end" font-family="IBM Plex Mono" font-size="11" fill="#5b667b">{th}</text>'
        y += h + 4
    svg += '</svg>'
    body += '<div style="display:grid;grid-template-columns:490px 1fr;gap:12px"><div class="box" style="padding:12px">' + svg + '</div>'
    body += '<div style="display:flex;flex-direction:column;gap:10px"><div class="box" style="padding:10px 12px;font-size:12.5px;line-height:1.6"><div class="lbl">WHY 4 LAYERS</div>The RF track and USB need a solid ground right under them. Two layers cannot give that.</div>'
    body += '<div class="box" style="padding:10px 12px;font-size:12.5px;line-height:1.6"><div class="lbl">WHAT IT SETS</div>Track width for 50 Ω on L1<br>Spacing and via sizes from the manufacturer<br>Which layer each critical net uses</div>'
    body += '<div class="box" style="padding:10px 12px;font-size:12.5px;line-height:1.6"><div class="lbl">TO DO IN ALTIUM</div>Set the stack-up once<br>Import the design-rule file<br>Check the rules in the PcbDoc <span class="src">rules table</span></div></div></div>'
    c = chat("Layers", '<div class="ctx"><b>Stack-up</b>4 layers · 1.6 mm</div>',
             [("me", "Can I use 2 layers to save money?"),
              ("ag", 'Not for this board. The 50 Ω RF track needs a ground plane under it, and a 2-layer board has none. The price difference is small at this quantity.')],
             "Set the stack-up in Altium, then open <b>Outputs</b>.", ["What does the stack-up set?", "Where do I set it in Altium?"])
    return page(5, c, body)


def library():
    body = '<h2>Project library</h2><div class="sub">One library for the whole project: every symbol linked to its footprint and 3D model. One Altium script builds it from the checked part files.</div>'
    body += '<div style="display:flex;gap:8px;margin-bottom:10px;align-items:center"><span class="btn pri">Build the library in Altium</span><span class="btn">Open the folder</span><span style="color:var(--dim);font-size:12px">lte_tracker.IntLib · 28 parts · 25 ready</span></div>'
    body += '<div class="box"><table><tr><th>Part</th><th>Symbol</th><th>Footprint</th><th>3D model</th><th>Status</th><th></th></tr>'
    rows = [("A7670G-LABE", 1, 1, 1, "ok", "Ready"), ("STM32G030F6P6", 1, 1, 1, "ok", "Ready"), ("TXS0104E", 1, 1, 1, "ok", "Ready"), ("TPS62162", 1, 1, 0, "warn", "No 3D model"), ("USB-C receptacle", 1, 1, 1, "ok", "Ready"), ("SIM card holder", 1, 0, 0, "bad", "Footprint missing"), ("100nF 0402", 1, 1, 1, "ok", "Ready"), ("D30 · TVS diode", 1, 1, 0, "warn", "Out of stock")]
    for n, a, b, c3, k, st in rows:
        ck = lambda v: '<span style="color:var(--ok)">✓</span>' if v else '<span style="color:var(--bad)">✗</span>'
        act = '<span class="btn" style="padding:3px 9px">Find the model</span>' if k != "ok" else '<span class="btn" style="padding:3px 9px">💬 Ask</span>'
        body += f'<tr><td><b>{n}</b></td><td>{ck(a)}</td><td>{ck(b)}</td><td>{ck(c3)}</td><td><span class="tag {k}">{st}</span></td><td>{act}</td></tr>'
    body += '</table></div>'
    body += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:10px">'
    for i, (h, d) in enumerate([("Check the part files", "Symbol, footprint and 3D model per part"), ("Run the script once", "Altium builds one library"), ("Install it in Altium", "Use the same parts in every sheet")]):
        body += f'<div class="box" style="padding:10px 12px;font-size:12.5px"><span class="tag info">{i + 1}</span> <b>{h}</b><br><span style="color:var(--dim)">{d}</span></div>'
    body += '</div>'
    c = chat("Project library", '<div class="ctx"><b>SIM card holder</b>Footprint missing</div>',
             [("me", "Where do I get the footprint?"),
              ("ag", 'The manufacturer\'s page has one. Open the link in the row, download the file and drop it into the project files. I check it against the datasheet before it goes into the library. <span class="src">part page</span>')],
             "Fix the red rows, then press <b>Build the library in Altium</b>.", ["What is in the library?", "Why one library?"])
    return page(None, c, body, nav_active="lib")


def files():
    body = '<h2>Files</h2><div class="sub">Every file in the project, from the Altium folder or uploaded by you. Open any of them here.</div>'
    body += '<div style="display:flex;gap:8px;margin-bottom:10px;align-items:center"><span class="btn pri">⬆ Upload files</span><span class="btn">Open the Altium folder</span><span class="btn">Refresh</span></div>'
    body += '<div class="box"><table><tr><th>File</th><th>Where from</th><th>Used in answers</th><th>Updated</th><th></th></tr>'
    groups = [("PROJECT", [("lte_tracker.PrjPcb", "Altium project", 4, "today 18:22"), ("01_Power.SchDoc", "Altium project", 9, "today 18:22"), ("LTE-TRACKER.PcbDoc", "Altium project", 6, "today 18:22")]),
              ("DATASHEETS", [("A7670G hardware guide.pdf", "downloaded", 14, "Oct 9"), ("STM32G030 datasheet.pdf", "downloaded", 11, "Oct 9"), ("TXS0104E datasheet.pdf", "downloaded", 3, "Oct 9")]),
              ("REFERENCE", [("AD26 essentials manual.pdf", "reference", 7, "Oct 2"), ("JLCPCB capabilities.html", "reference", 5, "Oct 2")]),
              ("YOUR FILES", [("modem notes.txt", "uploaded by you", 2, "Oct 10"), ("antenna layout.png", "uploaded by you", 1, "Oct 11")])]
    for g, fs in groups:
        body += f'<tr><td colspan=5 style="background:var(--panel2);font-size:10.5px;letter-spacing:.06em;color:var(--dim);font-weight:700;padding:5px 8px">{g}</td></tr>'
        for n, w, u, d in fs:
            body += f'<tr><td class="mono">📄 {n}</td><td>{w}</td><td>{u}</td><td style="color:var(--dim)">{d}</td><td><span class="btn" style="padding:3px 9px">Open</span></td></tr>'
    body += '</table></div>'
    c = chat("Files", '<div class="ctx"><b>18 files</b>3 from Altium · 8 reference · 2 yours</div>',
             [("me", "Add my own antenna notes."),
              ("ag", 'Drop the file in the list. From then on I can quote it, and it shows up in the answers as a tag.'),
              ("me", "Which file did you use most?"),
              ("ag", 'The modem hardware guide: 14 answers so far.')],
             "Upload your own references, then continue where you stopped.", ["Upload a file", "What can you quote?"])
    return page(None, c, body, nav_active="kb")


def skills():
    body = '<h2>Skills</h2><div class="sub">What the agent knows how to do. Each skill is a short, checkable procedure, and the agent picks the right one for your question.</div>'
    items = [("idea-and-requirements", "Idea", "Turns a rough idea into the questions worth asking early"), ("parts-and-stock", "Parts", "Checks stock, price and alternatives per part"), ("part-models", "Parts", "Finds symbol, footprint and 3D model"),
             ("project-library", "Library", "Plans the one project library"), ("schematic-preview", "Schematic", "Example sheets to redraw in Altium"), ("schematic-review", "Schematic", "Findings that cite a datasheet page"),
             ("placement-and-routing-plan", "Placement · Routing", "Rooms, order and critical nets"), ("rules-and-calcs", "Layers", "Design rules and trace calculations"), ("board-review", "Routing", "Checks the routed board and the DRC messages"),
             ("manufacturer-and-dfm", "Manufacturer", "Output files and the manufacturer's checks"), ("altium-help", "Any tab", "How to do it in Altium, with a source"), ("project-keeping", "Any tab", "Decisions log and file order")]
    body += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">'
    for n, tab, d in items:
        on = n == "schematic-review"
        body += f'<div class="box" style="padding:9px 11px;{"border-color:var(--accent);background:var(--accent-soft)" if on else ""}"><div class="mono" style="font-weight:600;font-size:11.5px">{n}</div><div style="margin:3px 0 4px"><span class="tag info">{tab}</span></div><div style="font-size:11.5px;line-height:1.35;color:var(--dim)">{d}</div></div>'
    body += '</div>'
    body += '<div class="box" style="margin-top:10px;padding:10px 14px;font-size:12.5px;line-height:1.6;display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px"><div><div class="lbl">SELECTED · SCHEMATIC-REVIEW</div>Reviews your sheet and returns a findings table.</div><div><div class="lbl">EVERY FINDING HAS</div>A verdict, a fix, and a datasheet page</div><div><div class="lbl">USED 6 TIMES IN THIS PROJECT</div>Last: Oct 11, power sheet</div></div>'
    c = chat("Skills", '<div class="ctx"><b>Schematic review</b>power sheet</div>',
             [("me", "Check my power sheet."),
              ("ag", 'I used the <b>schematic-review</b> skill. Two findings: the bulk capacitor on U2 is above the maximum value <span class="src">datasheet p.9</span>, and the enable pin has no pull-up <span class="src">datasheet p.11</span>.')],
             "Fix the two findings in Altium, then ask me to check the sheet again.", ["Which skill did you use?", "List all skills"])
    return page(None, c, body, nav_active="sk")


# ------------------------------------------------------------------ 5 outputs
def outputs():
    body = '<h2>Outputs</h2><div class="sub">Every file exported from the Altium project, in one place. Open any file here.</div>'
    body += '<div style="display:flex;gap:8px;margin-bottom:10px;align-items:center"><span class="btn pri">Refresh from Altium</span><span style="color:var(--dim);font-size:12px">Last export 18:22 · project <b>lte_tracker.PrjPcb</b></span></div>'
    groups = [("SCHEMATIC", [("Schematic", "Schematic-4-sheets.pdf", "5.4 MB", "ok")]), ("BOARD", [("Board", "LTE-TRACKER.PcbDoc", "3.1 MB", "ok")]),
              ("MANUFACTURING", [("Gerber and drill", "LTE-TRACKER-Gerber.zip", "310 KB", "ok")]),
              ("ASSEMBLY", [("Parts table · manufacturer format", "BOM-JLC.csv", "4 KB", "ok"), ("Parts table · full", "BOM-full.csv", "7 KB", "ok"), ("Pick and place", "CPL-JLC.csv", "9 KB", "warn")])]
    body += '<div class="box"><table><tr><th>File</th><th>Name</th><th>Size</th><th>Status</th><th></th></tr>'
    for g, fs in groups:
        body += f'<tr><td colspan=5 style="background:var(--panel2);font-size:10.5px;letter-spacing:.06em;color:var(--dim);font-weight:700;padding:5px 8px">{g}</td></tr>'
        for n, f, sz, k in fs:
            st = '<span class="tag ok">up to date</span>' if k == "ok" else '<span class="tag warn">older than the board</span>'
            body += f'<tr><td><b>{n}</b></td><td class="mono">{f}</td><td>{sz}</td><td>{st}</td><td><span class="btn" style="padding:3px 9px">Open</span> <span class="btn" style="padding:3px 9px">Folder</span></td></tr>'
    body += '</table></div>'
    body += '<div class="box" style="margin-top:10px;padding:8px 10px"><div class="lbl">BOM-JLC.csv · preview</div><table><tr><th>Comment</th><th>Designator</th><th>Footprint</th><th>LCSC part</th></tr>'
    for r in [("100nF", "C34-C42", "0402", "C1525"), ("33pF", "C32", "0402", "C1565"), ("22R", "R41, R42, R43", "0402", "C25092")]:
        body += "<tr>" + "".join(f'<td class="mono">{x}</td>' for x in r) + "</tr>"
    body += "</table></div>"
    c = chat("Altium steps", '<div class="ctx"><b>Implement in Altium</b>Plan agreed · 4 of 4 tabs confirmed</div>',
             [("ag", 'Open Altium and the project below, then run the output job once. The files land in the folder this workspace reads, so they show up here without any upload.'),
              ("me", "The pick and place file is marked older than the board."),
              ("ag", 'You moved a part after the last export. Run the output job again, then press <b>Refresh from Altium</b>.')],
             "Run the output job in Altium, then press <b>Refresh</b>.", ["How do I run the output job?", "What is a CPL file?"])
    return page(6, c, body)


# ------------------------------------------------------------------ 6 manufacturer
def manufacturer():
    body = '<h2>Manufacturer check</h2><div class="sub">Run the manufacturer\'s checker, upload what it shows, and go through the flags with the agent.</div>'
    body += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">'
    body += '<div class="box" style="padding:12px 14px;font-size:12.5px;line-height:1.7"><div class="lbl">1 · RUN THE CHECK</div>① Open the manufacturer\'s checker<br>② Upload <span class="mono">LTE-TRACKER-Gerber.zip</span><br>③ Run the PCB check, then the assembly check<br>④ Export the report or take a screenshot</div>'
    body += '<div class="box" style="padding:12px 14px"><div class="lbl">2 · UPLOAD THE RESULTS</div><div style="border:1.5px dashed #aab3c6;border-radius:8px;padding:10px;text-align:center;color:var(--dim);font-size:12px;margin-bottom:8px">Drop the report or screenshots here</div>'
    body += '<span class="att" style="background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:3px 8px;font-family:var(--f-mono);font-size:11px;margin-right:6px">📎 PCB-DFM-report.pdf</span><span style="background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:3px 8px;font-family:var(--f-mono);font-size:11px">📎 SMT-DFM.png</span></div></div>'
    body += '<div class="box"><div style="padding:10px 12px 0"><div class="lbl">3 · FLAGS</div></div><table><tr><th>Flag</th><th>Count</th><th>Verdict</th><th></th></tr>'
    for f, n, v, k in [("Board outline in every layer", 48, "Real fault · fix", "bad"), ("Silkscreen too thin", 12, "Real fault · fix", "bad"), ("Pad spacing", 17, "False alarm", "ok"),
                       ("Solder-mask bridge", 50, "False alarm", "ok"), ("Annular ring, unplated holes", 6, "False alarm", "ok")]:
        body += f'<tr><td>{f}</td><td class="mono">{n}</td><td><span class="tag {k}">{v}</span></td><td><span class="btn" style="padding:3px 9px">💬 Ask</span></td></tr>'
    body += '</table></div>'
    c = chat("Manufacturer check", '<div class="ctx"><b>Reports uploaded</b>PCB check · assembly check<br><span class="att">📎 PCB-DFM-report.pdf</span></div>',
             [("me", "Pad spacing is flagged 17 times. Is that a problem?"),
              ("ag", 'No. The checker reads the Gerber files and does not know which pad belongs to which net, so it flags pads that are meant to be close. <span class="src">manufacturer note</span> The outline flag is different: it is a real fault.'),
              ("me", "How do I fix the outline?"),
              ("ag", 'In the output job, plot the outline layer only into its own file. I listed the steps under the flag.')],
             "Fix the two real faults in Altium, export again and upload the new report.", ["Explain the next flag", "How do I re-export?"])
    return page(7, c, body)


# ------------------------------------------------------------------ 7 settings
def settings():
    body = '<h2>Settings</h2><div class="sub">Link the workspace to your Altium project, so the scripts always find the right files.</div>'

    def field(l, v, extra=""):
        return f'<div style="display:grid;grid-template-columns:170px 1fr auto;gap:10px;align-items:center;margin-bottom:10px"><div style="color:var(--dim);font-size:12px;font-weight:600">{l}</div><div class="box mono" style="padding:8px 10px;background:var(--panel2)">{v}</div><div>{extra}</div></div>'
    body += '<div class="box" style="padding:14px 16px;margin-bottom:12px"><div class="lbl">ALTIUM PROJECT</div>'
    body += field("Project name", "lte_tracker") + field("Project file", "C:\\Projects\\lte_tracker\\lte_tracker.PrjPcb", '<span class="btn">Browse…</span>') + field("Board file", "LTE-TRACKER.PcbDoc  (found in the project)")
    body += field("Output folder", "C:\\Projects\\lte_tracker\\Outputs", '<span class="btn">Browse…</span>') + field("Altium Designer", "26.8 · C:\\Program Files\\Altium\\AD26", '<span class="tag ok">detected</span>')
    body += '<div style="display:flex;gap:10px;align-items:center"><span class="btn pri">Test the link</span><span class="tag ok">Found 4 schematic sheets and 1 board</span></div></div>'
    body += '<div class="box" style="padding:14px 16px"><div class="lbl">AGENT AND MANUFACTURER</div>' + field("AI engine", "Claude Code", '<span class="tag ok">connected</span>') + field("Manufacturer", "JLCPCB") + '</div>'
    c = chat("Setup", '<div class="ctx"><b>First time here</b>Link your Altium project</div>',
             [("ag", 'Point me to the project file and I find the rest: sheets, board and the output folder. The workspace only reads from it. It never changes your Altium files.')],
             "Press <b>Test the link</b>. If it shows your sheets, you are done.", ["What does it read?", "Where are the exports?"])
    return page(None, c, body, nav_active="set")


# ------------------------------------------------------------------ 8 knowledge base
def knowledge():
    body = '<h2>Knowledge base</h2><div class="sub">Everything the agent can quote. Open a file here, or upload your own.</div>'
    body += '<div style="display:grid;grid-template-columns:300px 1fr;gap:12px"><div class="box" style="padding:10px 12px"><span class="btn pri" style="width:100%;text-align:center;margin-bottom:10px">⬆ Upload files</span>'
    for g, fs in [("DATASHEETS", ["A7670G hardware guide.pdf", "STM32G030 datasheet.pdf", "TXS0104E datasheet.pdf"]), ("REFERENCE", ["AD26 essentials manual.pdf", "JLCPCB capabilities.html"]), ("YOUR FILES", ["modem notes.txt", "antenna layout.png"])]:
        body += f'<div class="lbl" style="margin-top:8px">{g}</div>'
        for f in fs:
            on = f.startswith("A7670G")
            body += f'<div style="padding:6px 8px;border-radius:6px;font-size:12px;{"background:var(--accent-soft);font-weight:600" if on else ""}">📄 {f}</div>'
    body += '</div><div class="box" style="padding:0;overflow:hidden"><div style="padding:8px 12px;border-bottom:1px solid var(--line2);display:flex;justify-content:space-between"><b style="font-size:12.5px">A7670G hardware guide.pdf</b><span class="tag info">page 14</span></div>'
    body += '<div style="padding:18px 22px;background:#fff;height:360px;font-size:12px;line-height:1.7;color:#333"><b style="font-size:14px">3.2 Power supply</b><br><br>'
    for w in (92, 86, 95, 70):
        body += f'<div style="height:9px;background:#e7ebf2;border-radius:3px;margin-bottom:9px;width:{w}%"></div>'
    body += '<div style="background:#fff3b0;padding:6px 8px;border-radius:4px;margin:10px 0;font-size:12px">VBAT supply input range … a single-cell Li-ion battery can supply the module directly.</div>'
    for w in (90, 80, 94, 60, 88, 76):
        body += f'<div style="height:9px;background:#e7ebf2;border-radius:3px;margin-bottom:9px;width:{w}%"></div>'
    body += '</div></div></div>'
    c = chat("Knowledge base", '<div class="ctx"><b>Opened from an answer</b>A7670G hardware guide.pdf · page 14</div>',
             [("ag", 'This is the page behind the tag in my answer. The highlighted sentence is the one I relied on.'),
              ("me", "Add my own antenna notes."),
              ("ag", 'Drop the file in the list. From then on I can quote it, and it shows up in the answers as a tag.')],
             "Upload your own references, then continue where you stopped.", ["Upload a file", "What can you quote?"])
    return page(None, c, body, nav_active="kb")


SCREENS = {"idea": idea, "parts": parts, "schematic": schematic, "placement": placement, "routing": routing, "layers": layers, "outputs": outputs, "library": library, "files": files, "skills": skills,
           "manufacturer": manufacturer, "settings": settings, "knowledge": knowledge}

if __name__ == "__main__":
    tmp = HERE / "_mock_tmp"; tmp.mkdir(exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1440, "height": 800}, device_scale_factor=2)
        for k, fn in SCREENS.items():
            f = tmp / f"{k}.html"; f.write_text(fn(), encoding="utf-8")
            pg.goto(f.as_uri()); pg.wait_for_timeout(700)
            pg.screenshot(path=str(IMG / f"mock_{k}.png"))
            print("wrote", k)
        b.close()
    from PIL import Image
    Image.open(IMG / "mock_parts.png").crop((24, 24, 768, 1580)).save(IMG / "mock_chat.png")
    Image.open(IMG / "mock_knowledge.png").crop((1454, 265, 2362, 760)).save(IMG / "mock_page.png")
    for f in tmp.glob("*.html"): f.unlink()
    tmp.rmdir()
