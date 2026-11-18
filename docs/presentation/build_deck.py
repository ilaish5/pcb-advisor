"""Builds pcb-advisor_presentation.pptx (editable, native shapes, Hebrew right-to-left) and an HTML/PNG preview of every slide.
Usage: python build_deck.py <out_dir> [--no-preview]    needs python-pptx and Pillow; the preview needs headless Edge.
Every image in img/ is a real capture: capture_ui.py (the running app, read-only), Altium's own window through the altium MCP
screenshot tool, cut to size by crop_shots.py. There are no mock-ups. The slides carry no speaker notes.
Fonts: Arial everywhere (present on every PC and Mac, has Hebrew).
"""
import re
import subprocess
import sys
from pathlib import Path
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from lxml import etree

HERE = Path(__file__).resolve().parent
IMG = HERE / "img"
FONT = "Arial"
NAVY, INK, MUTED, BLUE = "0F172A", "1E293B", "64748B", "2563EB"
BG, CARD, LINE = "F8FAFC", "FFFFFF", "E2E8F0"
RED, REDBG, GREEN, GREENBG, AMBER, AMBERBG, BLUEBG = "DC2626", "FEE2E2", "059669", "D1FAE5", "B45309", "FEF3C7", "DBEAFE"
W, H = 13.333, 7.5
L, R = 0.6, 12.733            # content edges
HEB = re.compile(r"[\u0590-\u05FF]")


class Slide:
    def __init__(self, bg=BG):
        self.bg, self.items = bg, []

    def rect(self, x, y, w, h, fill=CARD, line=None, lw=1, r=0.0, shape="rect"):
        self.items.append(dict(k="rect", x=x, y=y, w=w, h=h, fill=fill, line=line, lw=lw, r=r, shape=shape)); return self

    def text(self, x, y, w, h, paras, size=14, color=INK, bold=False, align=None, anchor="t", gap=0, ls=1.15):
        """paras: str | list of (str | [runs]); a run is str or (str, {bold,color,size}). align: l | r | c | None (r for Hebrew, l otherwise)."""
        if isinstance(paras, str): paras = [paras]
        self.items.append(dict(k="text", x=x, y=y, w=w, h=h, paras=paras, size=size, color=color, bold=bold,
                               align=align, anchor=anchor, gap=gap, ls=ls)); return self

    def img(self, name, x, y, w=None, h=None):
        iw, ih = Image.open(IMG / name).size
        if w is None: w = h * iw / ih
        h = w * ih / iw
        self.items.append(dict(k="img", name=name, x=x, y=y, w=w, h=h)); return self

    def line(self, x1, y1, x2, y2, color=MUTED, lw=1.5, arrow=False, dash=False):
        self.items.append(dict(k="line", x1=x1, y1=y1, x2=x2, y2=y2, color=color, lw=lw, arrow=arrow, dash=dash)); return self


def rgb(h): return RGBColor.from_string(h)


def norm_runs(p):
    if isinstance(p, str): return [(p, {})]
    return [(r, {}) if isinstance(r, str) else r for r in p]


def para_info(it, p):
    """(is_hebrew, align) of one paragraph."""
    heb = any(HEB.search(t) for t, _ in norm_runs(p))
    al = it["align"] or ("r" if heb else "l")
    return heb, al


# ---------------------------------------------------------------- pptx
def emit_pptx(slides, path):
    prs = Presentation(); prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    for s in slides:
        sl = prs.slides.add_slide(prs.slide_layouts[6])
        sl.background.fill.solid(); sl.background.fill.fore_color.rgb = rgb(s.bg)
        for it in s.items:
            k = it["k"]
            if k == "rect":
                kind = {"rect": MSO_SHAPE.RECTANGLE, "round": MSO_SHAPE.ROUNDED_RECTANGLE, "oval": MSO_SHAPE.OVAL}[it["shape"]]
                sh = sl.shapes.add_shape(kind, Inches(it["x"]), Inches(it["y"]), Inches(it["w"]), Inches(it["h"]))
                if it["shape"] == "round": sh.adjustments[0] = min(0.5, it["r"] / min(it["w"], it["h"]))
                sh.shadow.inherit = False
                if it["fill"]: sh.fill.solid(); sh.fill.fore_color.rgb = rgb(it["fill"])
                else: sh.fill.background()
                if it["line"]: sh.line.color.rgb = rgb(it["line"]); sh.line.width = Pt(it["lw"])
                else: sh.line.fill.background()
            elif k == "text":
                tb = sl.shapes.add_textbox(Inches(it["x"]), Inches(it["y"]), Inches(it["w"]), Inches(it["h"]))
                tf = tb.text_frame; tf.word_wrap = True
                tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
                tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[it["anchor"]]
                for i, p in enumerate(it["paras"]):
                    para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                    heb, al = para_info(it, p)
                    para.alignment = {"l": PP_ALIGN.LEFT, "r": PP_ALIGN.RIGHT, "c": PP_ALIGN.CENTER}[al]
                    if heb: para._p.get_or_add_pPr().set("rtl", "1")
                    para.line_spacing = it["ls"]
                    if i: para.space_before = Pt(it["gap"])
                    for t, o in norm_runs(p):
                        r = para.add_run(); r.text = t; f = r.font
                        f.name = FONT; f.size = Pt(o.get("size", it["size"])); f.bold = o.get("bold", it["bold"])
                        f.color.rgb = rgb(o.get("color", it["color"]))
                        rpr = r._r.get_or_add_rPr()
                        if HEB.search(t): rpr.set("lang", "he-IL")
                        cs = etree.SubElement(rpr, qn("a:cs")); cs.set("typeface", FONT)
            elif k == "img":
                sl.shapes.add_picture(str(IMG / it["name"]), Inches(it["x"]), Inches(it["y"]), width=Inches(it["w"]))
            elif k == "line":
                c = sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(it["x1"]), Inches(it["y1"]), Inches(it["x2"]), Inches(it["y2"]))
                c.line.color.rgb = rgb(it["color"]); c.line.width = Pt(it["lw"])
                ln = c.line._get_or_add_ln()
                if it["dash"]: etree.SubElement(ln, qn("a:prstDash")).set("val", "dash")
                if it["arrow"]:
                    te = etree.SubElement(ln, qn("a:tailEnd")); te.set("type", "triangle"); te.set("w", "med"); te.set("len", "med")
    prs.save(path)


# ---------------------------------------------------------------- html preview (same description, rendered by Edge)
def esc(t): return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def emit_html(slides, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    px = lambda v: f"{v * 96:.1f}px"
    files = []
    for n, s in enumerate(slides, 1):
        d = []
        for it in s.items:
            k = it["k"]
            if k == "rect":
                rad = "50%" if it["shape"] == "oval" else (px(it["r"]) if it["shape"] == "round" else "0")
                bd = f"border:{it['lw'] * 96 / 72:.2f}px solid #{it['line']};" if it["line"] else ""
                bgc = f"background:#{it['fill']};" if it["fill"] else ""
                d.append(f"<div style='position:absolute;left:{px(it['x'])};top:{px(it['y'])};width:{px(it['w'])};height:{px(it['h'])};"
                         f"box-sizing:border-box;{bgc}{bd}border-radius:{rad}'></div>")
            elif k == "text":
                ps = []
                for i, p in enumerate(it["paras"]):
                    heb, al = para_info(it, p)
                    runs = "".join(f"<span style='font-weight:{'700' if o.get('bold', it['bold']) else '400'};color:#{o.get('color', it['color'])};"
                                   f"font-size:{o.get('size', it['size']) * 96 / 72:.2f}px'>{esc(t)}</span>" for t, o in norm_runs(p))
                    mt = f"margin-top:{it['gap'] * 96 / 72:.1f}px;" if i else ""
                    ta = {"l": "left", "r": "right", "c": "center"}[al]
                    ps.append(f"<div dir='{'rtl' if heb else 'ltr'}' style='{mt}min-height:1em;text-align:{ta}'>{runs}</div>")
                jc = {"t": "flex-start", "m": "center", "b": "flex-end"}[it["anchor"]]
                d.append(f"<div style='position:absolute;left:{px(it['x'])};top:{px(it['y'])};width:{px(it['w'])};height:{px(it['h'])};"
                         f"display:flex;flex-direction:column;justify-content:{jc};line-height:{it['ls']};"
                         f"font-family:{FONT},sans-serif;font-size:{it['size'] * 96 / 72:.2f}px'>{''.join(ps)}</div>")
            elif k == "img":
                d.append(f"<img src='{(IMG / it['name']).as_uri()}' style='position:absolute;left:{px(it['x'])};top:{px(it['y'])};width:{px(it['w'])}'>")
            elif k == "line":
                mk = "marker-end='url(#a)'" if it["arrow"] else ""
                da = "stroke-dasharray='6 4'" if it["dash"] else ""
                d.append(f"<svg style='position:absolute;left:0;top:0;width:{px(W)};height:{px(H)};overflow:visible'>"
                         f"<defs><marker id='a' markerWidth='8' markerHeight='8' refX='7' refY='4' orient='auto'>"
                         f"<path d='M0,0 L8,4 L0,8 z' fill='#{it['color']}'/></marker></defs>"
                         f"<line x1='{it['x1'] * 96}' y1='{it['y1'] * 96}' x2='{it['x2'] * 96}' y2='{it['y2'] * 96}' stroke='#{it['color']}' "
                         f"stroke-width='{it['lw'] * 96 / 72}' {mk} {da}/></svg>")
        f = out_dir / f"slide{n:02d}.html"
        f.write_text(f"<html><head><meta charset='utf-8'></head><body style='margin:0;overflow:hidden'><div style='position:relative;width:{px(W)};height:{px(H)};"
                     f"background:#{s.bg};overflow:hidden'>{''.join(d)}</div></body></html>", encoding="utf-8")
        files.append(f)
    return files


def render_png(files):
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    for f in files:
        subprocess.run([edge, "--headless", "--disable-gpu", "--hide-scrollbars", f"--screenshot={f.with_suffix('.png')}",
                        f"--window-size={round(W * 96)},{round(H * 96)}", f.as_uri()],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)


# ---------------------------------------------------------------- helpers shared by slides
TOTAL = 10


def frame(s, kicker, title, n):
    s.text(L, 0.4, R - L, 0.3, kicker, size=12, color=BLUE, bold=True)
    s.text(L, 0.72, R - L, 0.7, title, size=30, color=NAVY, bold=True, ls=1.05)
    s.text(L, 7.08, 6, 0.25, "PCB Advisor  ·  27525", size=9, color=MUTED, align="l")
    s.text(R - 1.0, 7.08, 1.0, 0.25, f"{n} / {TOTAL}", size=9, color=MUTED, align="r")


def bullets(s, x, y, w, items, size=20, color=INK, gap=12, mark=BLUE):
    s.text(x, y, w, 0.5 * len(items) * size / 14, [[("•  ", {"color": mark, "bold": True}), t] for t in items], size=size, color=color, gap=gap)


def shot(s, name, x, y, w, caption, cap_h=0.3, cap_size=11):
    """A real screenshot in a card with a caption that says what it shows."""
    iw, ih = Image.open(IMG / name).size
    h = w * ih / iw
    s.rect(x - 0.06, y - 0.06, w + 0.12, h + 0.12, fill=CARD, line=LINE, r=0.08, shape="round")
    s.img(name, x, y, w)
    s.text(x - 0.06, y + h + 0.12, w + 0.12, cap_h, caption, size=cap_size, color=MUTED, align="c")
    return h


def stat(s, x, y, w, num, label, color=NAVY, size=54, lsize=14):
    s.text(x, y, w, size / 72 * 1.25, num, size=size, color=color, bold=True, align="c", anchor="m", ls=1.0)
    s.text(x, y + size / 72 * 1.25 + 0.05, w, 0.6, label, size=lsize, color=MUTED, align="c")


def chip(s, x, y, w, label, fg, bg, size=12, h=0.34):
    s.rect(x, y, w, h, fill=bg, r=h / 2, shape="round")
    s.text(x, y, w, h, label, size=size, color=fg, bold=True, align="c", anchor="m")


def badge(s, x, y, n, fill=BLUE):
    s.rect(x, y, 0.42, 0.42, fill=fill, shape="oval")
    s.text(x, y, 0.42, 0.42, str(n), size=14, color="FFFFFF", bold=True, align="c", anchor="m")


def build():
    S = []

    # 1 title
    s = Slide(bg=NAVY); S.append(s)
    s.text(7.2, 0.9, 5.5, 0.3, "AI לתכנון חומרה", size=13, color="93C5FD", bold=True)
    s.text(7.2, 1.7, 5.5, 1.0, "PCB Advisor", size=54, color="FFFFFF", bold=True, ls=1.0, align="r")
    s.text(7.2, 3.0, 5.5, 1.6, "יועץ AI שמלווה סטודנט מהרעיון ועד קובצי הייצור, בתוך Altium Designer", size=24, color="CBD5E1", ls=1.2)
    s.rect(11.83, 5.0, 0.9, 0.06, fill=BLUE)
    s.text(7.2, 5.3, 5.5, 1.0, ["Ilia Shalem", "קורס 27525  ·  מרצה: Avihai Aharon"], size=15, color="94A3B8", gap=4, align="r")
    s.rect(0.6, 1.5, 6.3 + 0.16, 3.34 + 0.16, fill="1E293B", r=0.14, shape="round")
    s.img("altium_live_pcb.png", 0.68, 1.58, 6.3)
    s.text(0.6, 5.1, 6.46, 0.5, "צילום אמיתי: Altium Designer, הלוח Live-STM32.PcbDoc", size=11, color="94A3B8", align="c")

    # 2 the problem
    s = Slide(); S.append(s)
    frame(s, "הבעיה", "הבעיה של הסטודנט", 2)
    cards = [("טעויות קטנות", "footprint שגוי, רכיב שאזל, קבל על פין לא נכון", REDBG, RED),
             ("צ'אט כללי לא מספיק", "מציין פין וערך שגויים באותו ביטחון כמו נכונים", AMBERBG, AMBER),
             ("המטרה", "ה-AI עוזר, והקוד הוא שמחליט", GREENBG, GREEN)]
    cw, gp = 3.85, 0.29
    for i, (h, b, bg, fg) in enumerate(cards):
        x = R - cw - i * (cw + gp)
        s.rect(x, 1.9, cw, 3.1, fill=CARD, line=LINE, r=0.14, shape="round")
        s.rect(x, 1.9, cw, 0.14, fill=fg)
        s.text(x + 0.3, 2.4, cw - 0.6, 0.6, h, size=26, color=NAVY, bold=True)
        s.text(x + 0.3, 3.3, cw - 0.6, 1.4, b, size=18, color=MUTED, ls=1.25)
    s.rect(L, 5.5, R - L, 1.0, fill=BLUEBG, r=0.12, shape="round")
    s.text(L + 0.4, 5.5, R - L - 0.8, 1.0, "שתי עדיפויות: קודם דיוק טכני בלי טעויות, אחר כך קלות שימוש מההתקנה ועד קובצי הייצור",
           size=20, color=NAVY, bold=True, anchor="m")

    # 3 stages + approval
    s = Slide(); S.append(s)
    frame(s, "מה המערכת עושה", "שמונה שלבים, וכל פעולה באישור הסטודנט", 3)
    stages = [("רעיון", "דרישות ודיאגרמה"), ("BOM", "מלאי ומחיר ב-JLC"), ("ספרייה", "סמל, footprint, 3D"), ("סכמה", "ציור ב-Altium"),
              ("השמה", "Place parts"), ("ניתוב", "Route board"), ("DRC / DFM", "בדיקה מלאה"), ("תוצרים", "Gerber, BOM, CPL")]
    ax0, aw = 5.4, R - 5.4                      # the chain sits on the right, the evidence image on the left
    cw, gp = (aw - 3 * 0.17) / 4, 0.17
    for i, (nm, sub) in enumerate(stages):
        row, col = divmod(i, 4)
        x = R - cw - col * (cw + gp); y = 1.65 + row * 1.7
        s.rect(x, y, cw, 1.45, fill=CARD, line=LINE, r=0.12, shape="round")
        badge(s, x + cw - 0.55, y + 0.17, i + 1, fill=BLUE if i < 7 else GREEN)
        s.text(x + 0.12, y + 0.7, cw - 0.24, 0.35, nm, size=17, color=NAVY, bold=True, align="c")
        s.text(x + 0.12, y + 1.05, cw - 0.24, 0.3, sub, size=11, color=MUTED, align="c")
    bullets(s, ax0, 5.2, aw, ["לחיצה על כפתור השלב היא ההסכמה", "כל פעולה ב-Altium מגבה את הקובץ קודם", "ההזמנה נשארת של הסטודנט"], size=19, gap=9)
    shot(s, "ui_blink_route.png", L + 0.06, 1.71, 4.5, "Blinker-555: מה שהשרת כתב אחרי שהסטודנט לחץ Route", cap_h=0.45)

    # 4 the real UI
    s = Slide(); S.append(s)
    frame(s, "המערכת בפועל", "ממשק אמיתי, לוח STM32 אמיתי", 4)
    tiles = [("ui_live_idea.png", "רעיון: דיאגרמת בלוקים"), ("ui_live_bom.png", "BOM: 26 רכיבים ומלאי חי"),
             ("ui_live_library.png", "ספרייה: סמל, footprint ו-3D"), ("ui_live_schematic.png", "סכמה מ-Altium: גיליון 03 MCU")]
    iw = 5.45
    for i, (nm, cap) in enumerate(tiles):
        row, col = divmod(i, 2)
        shot(s, nm, R - iw - col * (iw + 0.25) - 0.06, 1.6 + row * 2.8, iw, cap, cap_h=0.28, cap_size=11)

    # 5 architecture
    s = Slide(); S.append(s)
    frame(s, "ארכיטקטורה", "ממשק, שרת, מנוע סוכן וגשר ל-Altium", 5)

    def box(x, y, w, h, head, sub, fill=CARD, fg=NAVY, line=LINE):
        s.rect(x, y, w, h, fill=fill, line=line, lw=1.5, r=0.14, shape="round")
        s.text(x + 0.15, y + 0.28, w - 0.3, 0.5, head, size=20, color=fg, bold=True, align="c")
        s.text(x + 0.15, y + 0.82, w - 0.3, 0.5, sub, size=12, color=MUTED if fill in (CARD, BLUEBG) else "CBD5E1", align="c")
    box(9.93, 1.8, 2.8, 1.45, "דפדפן", "ממשק המשתמש", fill=CARD)
    box(5.5, 1.8, 3.4, 1.45, "שרת מקומי", "serve.py: הכותב היחיד", fill=BLUEBG, line=BLUE)
    box(0.6, 1.8, 3.9, 1.45, "מנועי סוכן", "Claude Code  |  Antigravity", fill=CARD)
    box(5.5, 4.1, 3.4, 1.45, "גשר Altium", "bridge.py: סקריפטים", fill=CARD)
    box(0.6, 4.1, 3.9, 1.45, "Altium Designer", "שרטוט, השמה, ניתוב, DRC, תוצרים", fill=NAVY, fg="FFFFFF", line=NAVY)
    box(9.93, 4.1, 2.8, 1.45, "JLC", "מלאי, מחיר, דאטהשיט", fill=CARD)
    s.line(9.93, 2.52, 8.9, 2.52, arrow=True, lw=2.25)            # UI -> server (right to left)
    s.line(5.5, 2.52, 4.5, 2.52, arrow=True, lw=2.25)             # server -> engines
    s.line(7.2, 3.25, 7.2, 4.1, arrow=True, lw=2.25)              # server -> bridge
    s.line(5.5, 4.82, 4.5, 4.82, arrow=True, lw=2.25)             # bridge -> Altium
    s.line(8.6, 3.25, 10.4, 4.1, arrow=True, lw=2.25)             # server -> JLC
    bullets(s, L, 5.9, R - L, ["הסוכן מציע פעולות, והשרת מבצע וכותב את התוצאה", "שני מנועים דרך שער אחד", "הכול מקומי, שום דבר לא נשלח החוצה"], size=17, gap=5)

    # 6 quality
    s = Slide(); S.append(s)
    frame(s, "איכות והקפדה", "עדיף לא לעשות מאשר לטעות", 6)
    shot(s, "ui_live_outputs_blocked.png", L + 0.06, 1.7, 6.5,
         "Live-STM32, Outputs: קובצי הייצור נחסמים עד שכל פין לא מאומת נסגר", cap_h=0.5)
    stat(s, 7.7, 1.55, 2.5, "2241", "בדיקות נאספות", size=54)
    stat(s, 10.2, 1.55, 2.5, "12/12", "תקלות אמיתיות נתפסו בקוד", size=54)
    bullets(s, L, 4.9, R - L,
            ["ספק מסומן 'לא נבדק', אף פעם לא 'עבר', ואין ממצא שווא",
             "DRC מלא: כל כלל בדוח עם ספירה, נקי רק כשהסכום שווה ל-Total",
             "הנתב מסרב מראש במקום להציג לוח שנראה מנותב"], size=20, gap=12)

    # 7 router + placement
    s = Slide(); S.append(s)
    frame(s, "שלב 3: נתב והשמה", "לוח מיקרו-בקר של 60 רכיבים, בלי Altium", 7)
    tiles = [("60", "רכיבים, שתי שכבות"), ("45/45", "נתיבים נותבו, 0 הפרות"), ("4.96", "מ\"מ גביש, תקרה 5"), ("8/8", "קבלי ניתוק בתוך 3 מ\"מ")]
    tw, gp = 2.85, 0.243
    for i, (n, lab) in enumerate(tiles):
        x = R - tw - i * (tw + gp)
        s.rect(x, 1.65, tw, 2.0, fill=CARD, line=LINE, r=0.14, shape="round")
        stat(s, x, 1.85, tw, n, lab, color=BLUE, size=48, lsize=15)
    bullets(s, L, 4.5, R - L,
            ["רוחב לפי זרם, וזוג USB מצומד כשהמרווחים מאפשרים",
             "בדיקת יציקת GND: איים ופדים לא מחוברים",
             "סירוב מפורש לפני ניתוב: שכבות פנימיות, BGA, עכבה"], size=21, gap=14)
    s.text(L, 6.5, R - L, 0.3, "לוח STM32 סינתטי, 50 על 40 מ\"מ, 9 בדיקות אוטומטיות", size=11, color=MUTED, align="r")

    # 8 benchmark
    s = Slide(); S.append(s)
    frame(s, "בנצ'מרק", "12 תקלות אמיתיות, שני מנועים", 8)
    heads = ["מנוע", "הקוד תפס", "המנוע תפס", "מוקדם מהמציאות", "QA מתוך 25", "התנהגות מתוך 13"]
    rows = [("Claude Code", "12/12", "10/12", "7", "0.88", "0.61"), ("Antigravity", "12/12", "10/12", "7", "0.94", "0.92")]
    colw = [2.5, 1.9, 1.9, 2.2, 1.8, 1.83]
    xs, x = [], R
    for cwid in colw:
        x -= cwid; xs.append(x)
    s.rect(L, 1.7, R - L, 0.7, fill=NAVY, r=0.1, shape="round")
    for x, cwid, h in zip(xs, colw, heads):
        s.text(x + 0.1, 1.7, cwid - 0.2, 0.7, h, size=14, color="FFFFFF", bold=True, align="c", anchor="m")
    for ri, row in enumerate(rows):
        y = 2.55 + ri * 1.3
        s.rect(L, y, R - L, 1.15, fill=CARD, line=LINE, r=0.1, shape="round")
        for ci, (x, cwid, v) in enumerate(zip(xs, colw, row)):
            col = RED if v == "0.61" else (NAVY if ci else BLUE)
            s.text(x + 0.1, y, cwid - 0.2, 1.15, v, size=22 if ci == 0 else 36, color=col, bold=True, align="c", anchor="m", ls=1.0)
    bullets(s, L, 5.3, R - L,
            ["הקוד תופס 12/12 בשני המנועים, והמנוע לבדו 10/12",
             "ב-Claude Code נכשלו 5 מתוך 13 תשובות בהתנהגות, רובן באורך",
             "הרצה מ-18.11.2026, אחרי שלב 3"], size=19, gap=9)

    # 9 live STM32 run
    s = Slide(); S.append(s)
    frame(s, "הרצה חיה ב-Altium", "לוח STM32F103 אמיתי: מה עבד ומה לא", 9)
    shot(s, "altium_live_pcb.png", L + 0.06, 1.65, 7.2, "Altium Designer: הלוח Live-STM32, הניתוב חלקי", cap_h=0.3)
    blocks = [("עבד", GREEN, GREENBG, ["BOM, ספרייה, סכמה של 3 גיליונות", "חוקים והשמה, על 26 רכיבים"]),
              ("חלקי", AMBER, AMBERBG, ["ניתוב חלקי: 16/18", "DRC הושלם אך לא נקי: silk ו-mask, תוקן במחולל", "בדיקת יציקה: 0 איים"]),
              ("אחרי התיקונים", BLUE, BLUEBG, ["גביש ב-4.6 מ\"מ", "קבלי ניתוק על 4 מתוך 5 פיני אספקה"])]
    bx, bw = 0.6 + 7.2 + 0.4, R - (0.6 + 7.2 + 0.4)
    for i, (h, fg, bg, body) in enumerate(blocks):
        y = 1.65 + i * 1.53
        s.rect(bx, y, bw, 1.45, fill=CARD, line=LINE, r=0.12, shape="round")
        chip(s, bx + bw - 1.9 - 0.2, y + 0.16, 1.9, h, fg, bg)
        s.text(bx + 0.2, y + 0.58, bw - 0.4, 0.85, body, size=14, color=INK, ls=1.1, gap=3)
    s.rect(L, 6.32, R - L, 0.55, fill=BLUEBG, r=0.1, shape="round")
    s.text(L + 0.4, 6.32, R - L - 0.8, 0.55, "ניתוב מלא של הלוח הזה: בעבודה", size=18, color=NAVY, bold=True, anchor="m")

    # 10 limits + demo
    s = Slide(); S.append(s)
    frame(s, "גבולות והדגמה", "מגבלות ידועות, ותוכנית ההדגמה", 10)
    cw = (R - L - 0.4) / 2
    cards = [("מגבלות ידועות", RED, ["שתי שכבות, עד כ-60 רכיבים", "בלי BGA, שכבות פנימיות ועכבה", "ניתוב מלא של STM32 חי: בעבודה"]),
             ("הדגמה חיה", GREEN, ["פרויקט חדש: רעיון ו-BOM בצ'אט", "Draw, Place, Route ב-Altium", "DRC, יציקה, Generate outputs"])]
    for ci, (h, fg, items) in enumerate(cards):
        x = R - cw - ci * (cw + 0.4)
        s.rect(x, 1.7, cw, 4.6, fill=CARD, line=LINE, r=0.14, shape="round")
        s.rect(x, 1.7, cw, 0.14, fill=fg)
        s.text(x + 0.4, 2.15, cw - 0.8, 0.6, h, size=26, color=NAVY, bold=True)
        if ci == 1:
            for i, t in enumerate(items):
                badge(s, x + cw - 0.4 - 0.42, 3.25 + i * 0.95, i + 1, fill=GREEN)
                s.text(x + 0.4, 3.25 + i * 0.95, cw - 1.45, 0.8, t, size=19, color=INK, anchor="t")
            s.text(x + 0.4, 5.9, cw - 0.8, 0.3, "לוח Blinker-555, כ-15 דקות", size=12, color=MUTED)
        else:
            bullets(s, x + 0.4, 3.25, cw - 0.8, items, size=20, gap=20, mark=RED)
    return S


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    slides = build()
    assert len(slides) == TOTAL
    emit_pptx(slides, out / "pcb-advisor_presentation.pptx")
    if "--no-preview" not in sys.argv:
        prev = out / "preview"
        render_png(emit_html(slides, prev))
        print("previews in", prev)
    print("wrote", out / "pcb-advisor_presentation.pptx", len(slides), "slides")
