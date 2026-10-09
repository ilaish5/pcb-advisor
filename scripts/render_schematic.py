"""
The picture, rendered FROM the model. Never the source of truth.

Two levels, switched automatically:
  sketch stage   the proposed block diagram, laid out in dependency layers
  cascade stage  the signal path, sharpening as blocks accumulate

Hebrew: matplotlib has no bidi engine, so RTL text comes out reversed.  We
pre-order it with python-bidi and mirror flow arrows, because in an RTL diagram
the flow reads right to left.
"""
import pathlib
import re
import sys

import matplotlib
matplotlib.use("Agg")          # must precede schemdraw: the server renders off-thread
import matplotlib.pyplot as plt

import schemdraw
import schemdraw.elements as elm

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import model      # noqa: E402
import workspace  # noqa: E402

try:
    from bidi import get_display
except ImportError:                                          # pragma: no cover
    def get_display(s):
        return s

HEB = re.compile(r"[֐-׿]")
# python-bidi reorders but does not mirror paired glyphs, so "(DC)" comes out ")DC(".
MIRROR = str.maketrans("()[]{}<>", ")(][}{><")
W, H, GAPX, GAPY = 7.0, 3.4, 3.6, 2.2


def rtl(text):
    return bool(HEB.search(text or ""))


def shape(text, width=20):
    """Wrap, then hand RTL lines to the bidi algorithm so they draw correctly."""
    lines = []
    for para in (text or "").split("\n"):
        cur = ""
        for word in para.split():
            if len(cur) + len(word) + 1 > width and cur:
                lines.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        lines.append(cur)
    return "\n".join(get_display(l).translate(MIRROR) if rtl(l) else l for l in lines)


def _box(d, x, y, label, ident, color="black"):
    d.add(elm.Rect(corner1=(x - W / 2, y - H / 2), corner2=(x + W / 2, y + H / 2)).color(color))
    d.add(elm.Label().at((x, y)).label(shape(label), fontsize=10, color=color))
    d.add(elm.Label().at((x, y - H / 2 - 0.8)).label(ident, fontsize=8, color="#0033cc"))


def _arrow(d, p, q, skip=False, lane=0.0):
    """
    Orthogonal link from source to target.  Positions are already mirrored for
    RTL, so the arrow head lands the right way round without special-casing.
    A link that jumps more than one layer is routed in a lane underneath, or it
    would be drawn straight through the boxes in between.
    """
    (x1, y1), (x2, y2) = p, q
    right = x2 > x1
    sx = x1 + W / 2 if right else x1 - W / 2
    ex = x2 - W / 2 if right else x2 + W / 2

    if skip:
        d.add(elm.Line().at((x1, y1 - H / 2)).to((x1, lane)))
        d.add(elm.Line().at((x1, lane)).to((x2, lane)))
        d.add(elm.Arrow().at((x2, lane)).to((x2, y2 - H / 2)))
    elif abs(y1 - y2) < 0.1:
        d.add(elm.Arrow().at((sx, y1)).to((ex, y2)))
    else:
        mx = (sx + ex) / 2
        d.add(elm.Line().at((sx, y1)).to((mx, y1)))
        d.add(elm.Line().at((mx, y1)).to((mx, y2)))
        d.add(elm.Arrow().at((mx, y2)).to((ex, y2)))


def layers(blocks, links):
    """Longest-path layering, so arrows stay short and point one way."""
    ids = [b["id"] for b in blocks]
    preds = {i: [] for i in ids}
    for a, b in links:
        if a in preds and b in preds and a != b:
            preds[b].append(a)
    layer = {i: 0 for i in ids}
    for _ in range(len(ids) + 1):                # cap the walk; tolerates cycles
        changed = False
        for i in ids:
            want = max([layer[p] + 1 for p in preds[i]] or [0])
            if want > layer[i]:
                layer[i], changed = want, True
        if not changed:
            break
    return layer


def render(project=None):
    m = model.build(project=project)
    pdir = model.project_dir(m["project"])
    (pdir / "artifacts").mkdir(parents=True, exist_ok=True)
    svg = pdir / "artifacts" / "blocks.svg"

    try:
        with schemdraw.Drawing(file=str(svg), show=False) as d:
            d.config(unit=2.0, fontsize=11)
            _board(d, m)
    finally:
        # schemdraw's matplotlib backend opens a pyplot figure per drawing and
        # never closes it. redraw() runs after every applied action, so a long
        # session leaked one figure per decision until matplotlib complained.
        plt.close("all")

    png = svg.with_suffix(".png")
    try:
        import cairosvg
        # this preserves the aspect ratio, so it was never what made the old
        # export a 1600x142 strip - the single-row layout was. Bounding the
        # width here just keeps the file a sane size.
        cairosvg.svg2png(url=str(svg), write_to=str(png), output_width=1600)
    except Exception as exc:                                 # pragma: no cover
        print(f"(png skipped: {exc})")
    return svg, png


def _title(d, x, y, main, sub=None):
    d.add(elm.Label().at((x, y)).label(shape(main, 90), fontsize=13))
    if sub:
        d.add(elm.Label().at((x, y - 1.2)).label(shape(sub, 110), fontsize=9, color="#8a8a8a"))


# A column taller than this wraps into the next one. Any cap will do; what
# matters is that there IS one, in both directions, so the picture stays near
# enough to square to be read at the size a browser or a page gives it.
MAXROWS = 4


def _board(d, m):
    """One renderer for both stages.

    There used to be a second one for the cascade stage that drew the blocks in
    a single row and joined them with arrows taken from their order in the list.
    Those arrows were fiction - it asserted that a test point sits in series
    between a crystal and a debug header - and the row grew one block longer
    with every decision until the image was an unreadable strip. Both faults had
    the same cause: it had no link data and drew edges anyway.

    So: one layered placement, and NO edge unless the student drew it. Parts the
    design questions added are placed below, under a heading that says plainly
    that we do not know how they connect.
    """
    sketching = m["stage"] == "sketch"
    blocks = (m["sketch"].get("blocks", []) if sketching else m["blocks"]) or []
    links = [tuple(l) for l in
             ((m["sketch"].get("links") if sketching else m.get("links")) or [])
             if len(l) == 2]

    if not blocks:
        d.add(elm.Rect(corner1=(-16, -5), corner2=(16, 5)).color("#ffffff"))
        _title(d, 0, 0.6, "Describe what you want to build.",
               "A block diagram will appear here for you to confirm or correct.")
        return

    have = {b["id"] for b in blocks}
    joined = {i for l in links for i in l if i in have}
    wired = [b for b in blocks if b["id"] in joined]
    loose = [b for b in blocks if b["id"] not in joined]

    flip = any(rtl(b.get("label", "")) for b in blocks)
    pos = {}
    lay = layers(wired, links)

    # ---- what the student drew, laid out by dependency
    cols = {}
    for b in wired:
        cols.setdefault(lay[b["id"]], []).append(b)
    # a layer deeper than MAXROWS spills into a column of its own rather than
    # growing the picture downwards without limit
    spread, col = [], 0
    for c in sorted(cols):
        for start in range(0, len(cols[c]), MAXROWS):
            spread.append(cols[c][start:start + MAXROWS])
            col += 1
    ncols = max(col, 1)
    for c, items in enumerate(spread):
        x = ((ncols - 1 - c) if flip else c) * (W + GAPX)
        span = (len(items) - 1) * (H + GAPY)
        for i, b in enumerate(items):
            y = span / 2 - i * (H + GAPY)
            pos[b["id"]] = (x, y)
            _box(d, x, y, b.get("label", b["id"]), _ident(b, sketching))

    # ---- what the decisions added, wrapped, with no edges invented for it
    wired_ys = [y for _, y in pos.values()]
    if loose:
        top = (min(wired_ys) - H - GAPY - 3.0) if pos else 0.0
        width = min(MAXROWS, len(loose))
        left = min((x for x, _ in pos.values()), default=0.0)
        for i, b in enumerate(loose):
            c, r = i % width, i // width
            x = left + ((width - 1 - c) if flip else c) * (W + GAPX)
            y = top - r * (H + GAPY)
            pos[b["id"]] = (x, y)
            _box(d, x, y, b.get("label", b["id"]), _ident(b, sketching), color="#555555")
        if not sketching:
            _title(d, left + (width - 1) * (W + GAPX) / 2, top + H / 2 + 1.6,
                   "added by your decisions — how these connect is not decided yet")

    # Arrows last. schemdraw places a Rect at the drawing's CURRENT position, so
    # anything drawn after an arrow inherits wherever that arrow ended: boxes
    # and their labels drifted apart by two columns.
    lane = (min(wired_ys) - H / 2 - 2.0) if wired_ys else -6.0
    for a, b in links:
        if a in pos and b in pos:
            skip = abs(lay[b] - lay[a]) > 1
            _arrow(d, pos[a], pos[b], skip=skip, lane=lane)
            if skip:
                lane -= 1.6

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    if sketching:
        state = "confirmed" if m["sketch"].get("confirmed") else "proposed — confirm or correct it"
        head, sub = f"BLOCK DIAGRAM — {state}", None
    else:
        p = m["progress"]
        head = (f"YOUR BOARD — {p['answered']}/{p['total']} questions answered · "
                f"{p['constraints']} rules")
        sub = "only the connections you drew are shown"
    _title(d, (min(xs) + max(xs)) / 2, max(ys) + H / 2 + 2.4, head, sub)
    _legend(d, m, (min(xs) + max(xs)) / 2, min(ys) - H / 2 - 2.8)


def _ident(b, sketching):
    return f'{b["id"]}  ·  {b.get("kind", "?")}' if sketching else b["id"]


def _legend(d, m, x, y):
    """What J, U and Q mean. A teaching tool that prints reference designators
    and never expands them is withholding the one convention the student has
    not met yet."""
    text = legend_text(m)
    if not text:
        return
    d.add(elm.Label().at((x, y)).label(shape(text, 100), fontsize=9, color="#666666"))


def legend_text(m):
    """Separate so it can be tested: matplotlib draws SVG text as paths, so
    nothing in the output file can be searched for a phrase."""
    rows = m.get("designators") or []
    return " · ".join(f"{r['prefix']} = {r['means']}" for r in rows)


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    proj = sys.argv[1] if len(sys.argv) > 1 else workspace.default_project()
    svg, png = render(proj)
    print(f"wrote {svg.name}, {png.name}")
