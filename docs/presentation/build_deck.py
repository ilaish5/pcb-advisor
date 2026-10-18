"""Builds pcb-advisor_presentation.pptx (editable, native shapes) and an HTML preview of every slide.
Usage: python build_deck.py <out_dir>      needs python-pptx; preview needs playwright (Edge).
The same slide description feeds both outputs, so the preview shows what PowerPoint will show.
Fonts: Arial everywhere (present on every PC and Mac).
"""
import sys
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
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


class Slide:
    def __init__(self, bg=BG, notes=""):
        self.bg, self.notes, self.items = bg, notes, []

    def rect(self, x, y, w, h, fill=CARD, line=None, lw=1, r=0.0, shape="rect"):
        self.items.append(dict(k="rect", x=x, y=y, w=w, h=h, fill=fill, line=line, lw=lw, r=r, shape=shape)); return self

    def text(self, x, y, w, h, paras, size=14, color=INK, bold=False, align="l", anchor="t", gap=0, ls=1.15):
        """paras: str | list of (str | [runs]); a run is str or (str, {bold,color,size})."""
        if isinstance(paras, str): paras = [paras]
        self.items.append(dict(k="text", x=x, y=y, w=w, h=h, paras=paras, size=size, color=color, bold=bold,
                               align=align, anchor=anchor, gap=gap, ls=ls)); return self

    def img(self, name, x, y, w):
        self.items.append(dict(k="img", name=name, x=x, y=y, w=w)); return self

    def line(self, x1, y1, x2, y2, color=MUTED, lw=1.5, arrow=False, dash=False):
        self.items.append(dict(k="line", x1=x1, y1=y1, x2=x2, y2=y2, color=color, lw=lw, arrow=arrow, dash=dash)); return self


def rgb(h): return RGBColor.from_string(h)


def norm_runs(p):
    if isinstance(p, str): return [(p, {})]
    return [(r, {}) if isinstance(r, str) else r for r in p]


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
                    para.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[it["align"]]
                    if i: para.space_before = Pt(it["gap"])
                    for t, o in norm_runs(p):
                        r = para.add_run(); r.text = t; f = r.font
                        f.name = FONT; f.size = Pt(o.get("size", it["size"])); f.bold = o.get("bold", it["bold"])
                        f.color.rgb = rgb(o.get("color", it["color"]))
            elif k == "img":
                sl.shapes.add_picture(str(IMG / it["name"]), Inches(it["x"]), Inches(it["y"]), width=Inches(it["w"]))
            elif k == "line":
                c = sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(it["x1"]), Inches(it["y1"]), Inches(it["x2"]), Inches(it["y2"]))
                c.line.color.rgb = rgb(it["color"]); c.line.width = Pt(it["lw"])
                ln = c.line._get_or_add_ln()
                if it["dash"]: etree.SubElement(ln, qn("a:prstDash")).set("val", "dash")
                if it["arrow"]:
                    te = etree.SubElement(ln, qn("a:tailEnd")); te.set("type", "triangle"); te.set("w", "med"); te.set("len", "med")
        if s.notes: sl.notes_slide.notes_text_frame.text = s.notes
    prs.save(path)


# ---------------------------------------------------------------- html preview
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
                    runs = "".join(f"<span style='font-weight:{'700' if o.get('bold', it['bold']) else '400'};color:#{o.get('color', it['color'])};"
                                   f"font-size:{o.get('size', it['size']) * 96 / 72:.2f}px'>{esc(t)}</span>" for t, o in norm_runs(p))
                    mt = f"margin-top:{it['gap'] * 96 / 72:.1f}px;" if i else ""
                    ps.append(f"<div style='{mt}min-height:1em'>{runs}</div>")
                jc = {"t": "flex-start", "m": "center", "b": "flex-end"}[it["anchor"]]
                ta = {"l": "left", "c": "center", "r": "right"}[it["align"]]
                d.append(f"<div style='position:absolute;left:{px(it['x'])};top:{px(it['y'])};width:{px(it['w'])};height:{px(it['h'])};"
                         f"display:flex;flex-direction:column;justify-content:{jc};text-align:{ta};line-height:{it['ls']};"
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
        f.write_text(f"<html><body style='margin:0;overflow:hidden'><div style='position:relative;width:{px(W)};height:{px(H)};"
                     f"background:#{s.bg};overflow:hidden'>{''.join(d)}</div></body></html>", encoding="utf-8")
        files.append(f)
    return files


def render_png(files, out_dir):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": round(W * 96), "height": round(H * 96)}, device_scale_factor=1.5)
        for f in files:
            pg.goto(f.as_uri()); pg.screenshot(path=str(out_dir / (f.stem + ".png")))
        b.close()


# ---------------------------------------------------------------- helpers shared by slides
def frame(s, kicker, title, n, total):
    s.text(0.6, 0.38, 9, 0.3, kicker.upper(), size=11, color=BLUE, bold=True)
    s.text(0.6, 0.7, 12.1, 0.9, title, size=27, color=NAVY, bold=True, ls=1.1)
    s.text(0.6, 7.05, 8, 0.25, "PCB Advisor  ·  Course 27525", size=9, color=MUTED)
    s.text(11.7, 7.05, 1.03, 0.25, f"{n} / {total}", size=9, color=MUTED, align="r")


def chip(s, x, y, w, label, fg, bg, size=9):
    s.rect(x, y, w, 0.26, fill=bg, r=0.13, shape="round")
    s.text(x, y, w, 0.26, label, size=size, color=fg, bold=True, align="c", anchor="m")


def badge(s, x, y, n, fill=BLUE):
    s.rect(x, y, 0.36, 0.36, fill=fill, shape="oval")
    s.text(x, y, 0.36, 0.36, str(n), size=13, color="FFFFFF", bold=True, align="c", anchor="m")


def shot_slide(s, n, total, kicker, title, image, callouts, status, notes):
    frame(s, kicker, title, n, total)
    iw = 7.7; ih = iw * 900 / 1440
    s.rect(0.6, 1.75, iw + 0.12, ih + 0.12, fill=CARD, line=LINE, r=0.1, shape="round")
    s.img(image, 0.66, 1.81, iw)
    y = 1.8
    for i, (head, body) in enumerate(callouts, 1):
        badge(s, 8.75, y, i)
        s.text(9.25, y - 0.02, 3.5, 0.4, head, size=15, color=NAVY, bold=True, ls=1.05)
        s.text(9.25, y + 0.5, 3.5, 0.9, body, size=12, color=MUTED)
        y += 1.55
    s.notes = notes


TOTAL = 16


def mock_slide(S, n, kicker, title, image, labels, notes, w=9.6):
    s = Slide(notes=notes); S.append(s)
    frame(s, kicker, title, n, TOTAL)
    ih = w * 800 / 1440
    s.rect(0.6, 1.42, w + 0.12, ih + 0.12, fill=CARD, line=LINE, r=0.1, shape="round")
    s.img(image, 0.66, 1.48, w)
    y = 1.5
    for i, lab in enumerate(labels, 1):
        badge(s, 10.65, y, i)
        s.text(11.12, y - 0.06, 1.6, 0.9, lab, size=12, color=NAVY, bold=True, ls=1.1)
        y += 1.2 if len(labels) <= 4 else 1.0
    return s


def build():
    S = []
    # 1 title
    s = Slide(bg=NAVY, notes="פתיחה: בנינו עוזר AI שמלווה סטודנט בקורס תכנון לוחות. התכנון קורה ביחד מחוץ ל-Altium, והסטודנט נכנס ל-Altium כדי ליישם."); S.append(s)
    s.text(0.8, 0.8, 7, 0.3, "AI FOR HARDWARE ENGINEERING", size=12, color="93C5FD", bold=True)
    s.text(0.8, 2.0, 5.9, 1.2, "PCB Advisor", size=54, color="FFFFFF", bold=True, ls=1.0)
    s.text(0.8, 3.3, 5.6, 1.6, "An AI mentor that plans the board with the student, before Altium", size=22, color="CBD5E1", ls=1.2)
    s.rect(0.8, 5.35, 0.9, 0.06, fill=BLUE)
    s.text(0.8, 5.65, 6, 0.9, ["Ilia Shalem", "Course 27525  ·  Lecturer: Avihai Aharon"], size=14, color="94A3B8", gap=4)
    s.rect(6.55, 1.5, 6.1, 3.5 + 0.16, fill="1E293B", r=0.14, shape="round")
    s.img("mock_placement.png", 6.63, 1.58, 5.94)

    # 3 idea
    s = Slide(notes="הרעיון: מתכננים ביחד מחוץ ל-Altium, הסטודנט מיישם ב-Altium, ובודקים מול היצרן שוב ביחד. הסוכן מציע והסטודנט מחליט."); S.append(s)
    frame(s, "The idea", "Plan together. Implement in Altium. Check together.", 2, TOTAL)
    cols = [("1", "PLAN", "Student + agent", ["Idea", "Parts", "Schematic", "Placement & routing"], GREEN),
            ("2", "IMPLEMENT", "Student in Altium", ["Schematic", "Placement", "Routing"], None),
            ("3", "CHECK", "Student + agent", ["Export files", "Manufacturer check"], BLUE)]
    cw = 3.7
    for i, (num, kick, head, items, accent) in enumerate(cols):
        x = 0.6 + i * (cw + 0.52); mid = accent is None
        s.rect(x, 1.85, cw, 3.7, fill=NAVY if mid else CARD, line=None if mid else LINE, r=0.12, shape="round")
        s.text(x + 0.35, 2.1, cw - 0.7, 0.3, f"{num}  {kick}", size=12, color="93C5FD" if mid else accent, bold=True)
        s.text(x + 0.35, 2.45, cw - 0.7, 0.5, head, size=22, color="FFFFFF" if mid else NAVY, bold=True)
        s.text(x + 0.35, 3.3, cw - 0.7, 2.1, [[("•  ", {"color": "93C5FD" if mid else accent, "bold": True}), t] for t in items],
               size=16, color="E2E8F0" if mid else INK, gap=10)
        if i < 2: s.line(x + cw + 0.06, 3.7, x + cw + 0.46, 3.7, color=MUTED, lw=2.25, arrow=True)
    s.rect(0.6, 5.95, 12.13, 0.8, fill=BLUEBG, r=0.1, shape="round")
    s.text(0.95, 5.95, 11.4, 0.8, "The agent proposes.  The student decides.", size=18, color=NAVY, bold=True, anchor="m")

    mock_slide(S, 3, "Tab 1", "Idea: one diagram, shared by both", "mock_idea.png",
               ["Editable block diagram", "Same words for agent and student", "Decisions in free text"],
               "לשונית הרעיון. דיאגרמת הבלוקים ניתנת לעריכה על ידי שניהם ולכן יש שפה משותפת, וההחלטות נכתבות בטקסט חופשי. הדמיית ממשק.")
    mock_slide(S, 4, "Tab 2", "Parts: a table you can work in", "mock_parts.png",
               ["Datasheet link", "Live stock", "Swap a part", "Chat per part, datasheet attached"],
               "טבלת רכיבים אינטראקטיבית: קישור לדאטהשיט, מלאי חי, החלפה, צ'אט על רכיב (הדאטהשיט נכנס לשאלה) והסבר קצר על תפקיד הרכיב. הדמיית ממשק.")
    mock_slide(S, 5, "Tab 3", "Schematic: ask about any part", "mock_schematic.png",
               ["Generated by Python", "Click a part or a pin", "Ask in one click"],
               "הסכמה נוצרת בפייתון. לוחצים על רכיב או פין ושואלים. הסטודנט מצייר מחדש ב-Altium. הדמיית ממשק.")
    mock_slide(S, 6, "Tab 4  ·  Main output", "Placement: rooms, order, connector sides", "mock_placement.png",
               ["Rooms on the board", "Placement order", "Click a part, ask why"],
               "לשונית הפלייסמנט: אזורים על הלוח, סדר הצבה וכיווני מחברים. לוחצים על רכיב ושואלים למה. הדמיית ממשק.")
    mock_slide(S, 7, "Tab 5  ·  Main output", "Routing: the critical nets, planned", "mock_routing.png",
               ["Critical nets in colour", "Route order", "Click a net, ask why"],
               "לשונית הראוטינג: תוכנית לנתיבים הקריטיים (הזנה, RF, USB, UART) וסדר הניתוב. הדמיית ממשק.")
    mock_slide(S, 8, "Tab 6", "Layers: the stack-up behind the plan", "mock_layers.png",
               ["4-layer stack-up", "Why 4 layers", "What to set in Altium"],
               "לשונית השכבות: מבנה השכבות של היצרן, למה 4 שכבות, ומה להגדיר ב-Altium. הדמיית ממשק.")
    mock_slide(S, 9, "Tab 7", "Outputs: every file in one place", "mock_outputs.png",
               ["Schematic to Gerber", "Both parts tables", "Open in place"],
               "מרחב תוצרי Altium: כל קבצי הייצוא מהסכמה ועד הגרבר, כולל שני סוגי טבלת הרכיבים. אפשר לפתוח קבצים בממשק. הדמיית ממשק.")
    mock_slide(S, 10, "Tab 8", "Manufacturer check: results, discussed", "mock_manufacturer.png",
               ["Guided run", "Upload the results", "Real fault or false alarm"],
               "בדיקות סופיות מול היצרן: הסוכן מנחה איך מריצים, הסטודנט מעלה את התוצאות, ומדברים על כל סימון. הדמיית ממשק.")

    # 11-13 always available
    mock_slide(S, 11, "Always available", "Project library: one library for every part", "mock_library.png",
               ["Symbol, footprint, 3D", "Missing parts flagged", "One script builds it"],
               "ספריית הפרויקט: ספרייה אחת שבה לכל רכיב סימול, פוטפרינט ומודל תלת מימד מקושרים. סקריפט אחד ב-Altium בונה אותה. הדמיית ממשק.")
    mock_slide(S, 12, "Always available", "Files: open, upload, and see what is used", "mock_files.png",
               ["Project and reference files", "Upload your own", "Used in answers"],
               "לשונית הקבצים: קבצי הפרויקט מ-Altium, דאטהשיטים, רפרנסים וקבצים שהסטודנט מעלה. אפשר לפתוח בממשק ורואים כמה פעמים כל קובץ שימש בתשובות. הדמיית ממשק.")
    mock_slide(S, 13, "Always available", "Skills: twelve procedures the agent follows", "mock_skills.png",
               ["One skill per job", "Findings cite a page", "Shows which skill ran"],
               "הסקילים: שתים עשרה פרוצדורות קצרות. הסוכן בוחר את המתאימה לשאלה ואומר באיזו השתמש. כל ממצא כולל פסק דין, תיקון ועמוד בדאטהשיט. הדמיית ממשק.")
    mock_slide(S, 14, "Always available", "Settings: link to the Altium project", "mock_settings.png",
               ["Project name and path", "Altium location", "Test the link"],
               "הגדרות: קישור לפרויקט של Altium (שם, נתיב, מיקום התוכנה) כדי שהסקריפט יפנה לפרויקט הנכון. הדמיית ממשק.")

    # 11 guide + sources
    s = Slide(notes="הסוכן מנחה בכל שלב: מה הצעד הבא. והמקור הוא תג קטן בתוך התשובה. לחיצה אחת פותחת את העמוד בדאטהשיט, בלי חלון ובלי עצירה. הדמיית ממשק."); S.append(s)
    frame(s, "How it feels to use", "A next step at every stage. A source in one click.", 15, TOTAL)
    ch = 5.3; cw_ = ch * 744 / 1556
    s.rect(0.6, 1.5, cw_ + 0.12, ch + 0.12, fill=CARD, line=LINE, r=0.1, shape="round")
    s.img("mock_chat.png", 0.66, 1.56, cw_)
    x2 = 0.6 + cw_ + 0.6
    s.text(x2, 1.5, 6, 0.3, "EVERY STAGE", size=11, color=BLUE, bold=True)
    for i, nm in enumerate(["Idea", "Parts", "Schematic", "Placement", "Altium", "Check"]):
        xx = x2 + i * 1.35
        col = GREEN if i < 2 else (BLUE if i == 2 else LINE)
        s.rect(xx, 1.95, 0.34, 0.34, fill=col, shape="oval")
        s.text(xx - 0.3, 2.35, 0.94, 0.3, nm, size=10, color=INK if i <= 2 else MUTED, bold=i == 2, align="c")
        if i < 5: s.line(xx + 0.4, 2.12, xx + 1.29, 2.12, color=LINE, lw=2)
    s.text(x2, 3.2, 6, 0.3, "EVERY CLAIM", size=11, color=BLUE, bold=True)
    pw = 5.4
    s.rect(x2, 3.6, pw, (pw - 0.12) * 495 / 908 + 0.12, fill=CARD, line=LINE, r=0.1, shape="round")
    s.img("mock_page.png", x2 + 0.06, 3.66, pw - 0.12)
    s.rect(x2 + 1.6, 3.15, 1.6, 0.3, fill=BLUEBG, r=0.15, shape="round")
    s.text(x2 + 1.6, 3.15, 1.6, 0.3, "datasheet p.14  ↗", size=10, color=BLUE, bold=True, align="c", anchor="m")

    # 12 why
    s = Slide(notes="למה בנינו ככה: מקור לכל טענה בלי חיכוך, הסטודנט מחליט, רץ מקומית ובלי עלות, ויותר מצ'אט רגיל כי הוא רואה את הפרויקט."); S.append(s)
    frame(s, "Why it is built this way", "Four choices that keep it a mentor, not a shortcut", 16, TOTAL)
    cards = [("Every claim has a source", "A small tag. One click.", "1"), ("The student decides", "The agent proposes.", "2"),
             ("Local, $0 for the university", "Student's own Claude Code or Antigravity.", "3"), ("More than a chat", "Sees the real project and live stock.", "4")]
    cw, ch = 5.9, 2.1
    for i, (h, b, n) in enumerate(cards):
        x = 0.6 + (i % 2) * (cw + 0.33); y = 1.85 + (i // 2) * (ch + 0.3)
        s.rect(x, y, cw, ch, fill=CARD, line=LINE, r=0.12, shape="round")
        badge(s, x + 0.3, y + 0.5, n)
        s.text(x + 0.9, y + 0.4, cw - 1.2, 0.5, h, size=20, color=NAVY, bold=True, anchor="m")
        s.text(x + 0.9, y + 1.1, cw - 1.2, 0.7, b, size=15, color=MUTED)
    return S


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    slides = build()
    emit_pptx(slides, out / "pcb-advisor_presentation.pptx")
    prev = out / "preview"
    files = emit_html(slides, prev)
    render_png(files, prev)
    print("wrote", out / "pcb-advisor_presentation.pptx", len(slides), "slides; previews in", prev)
