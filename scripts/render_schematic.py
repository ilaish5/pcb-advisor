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

    with schemdraw.Drawing(file=str(svg), show=False) as d:
        d.config(unit=2.0, fontsize=11)
        (_sketch if m["stage"] == "sketch" else _chain)(d, m)

    png = svg.with_suffix(".png")
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg), write_to=str(png), output_width=1600)
    except Exception as exc:                                 # pragma: no cover
        print(f"(png skipped: {exc})")
    return svg, png


def _title(d, x, y, main, sub=None):
    d.add(elm.Label().at((x, y)).label(shape(main, 90), fontsize=13))
    if sub:
        d.add(elm.Label().at((x, y - 1.2)).label(shape(sub, 110), fontsize=9, color="#8a8a8a"))


def _sketch(d, m):
    blocks = m["sketch"].get("blocks", [])
    links = [tuple(l) for l in m["sketch"].get("links", []) if len(l) == 2]

    if not blocks:
        d.add(elm.Rect(corner1=(-16, -5), corner2=(16, 5)).color("#ffffff"))
        _title(d, 0, 0.6, "Describe what you want to build.",
               "A block diagram will appear here for you to confirm or correct.")
        return

    flip = any(rtl(b.get("label", "")) for b in blocks)
    lay = layers(blocks, links)
    cols = {}
    for b in blocks:
        cols.setdefault(lay[b["id"]], []).append(b)

    pos, ncols = {}, max(cols) + 1
    for c, items in sorted(cols.items()):
        x = c * (W + GAPX)
        if flip:                                  # right-to-left reading order
            x = (ncols - 1 - c) * (W + GAPX)
        span = (len(items) - 1) * (H + GAPY)
        for i, b in enumerate(items):
            y = span / 2 - i * (H + GAPY)
            pos[b["id"]] = (x, y)
            _box(d, x, y, b.get("label", b["id"]), f'{b["id"]}  ·  {b.get("kind","?")}')

    lane = min(p[1] for p in pos.values()) - H / 2 - 2.0
    for a, b in links:
        if a in pos and b in pos:
            skip = abs(lay[b] - lay[a]) > 1
            _arrow(d, pos[a], pos[b], skip=skip, lane=lane)
            if skip:
                lane -= 1.6

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    state = "confirmed" if m["sketch"].get("confirmed") else "proposed — confirm or correct it"
    _title(d, (min(xs) + max(xs)) / 2, max(ys) + H / 2 + 2.4, f"BLOCK SKETCH — {state}")


def _chain(d, m):
    blocks = m["blocks"]
    flip = any(rtl(b.get("label", "")) for b in blocks)
    order = list(reversed(blocks)) if flip else blocks
    xs = []
    for i, b in enumerate(order):
        x = i * (W + GAPX)
        xs.append(x)
        _box(d, x, 0, b["label"], b["id"])
    for a, b in zip(xs, xs[1:]):
        d.add(elm.Arrow().at((a + W / 2, 0)).to((b - W / 2, 0)))
    p = m["progress"]
    _title(d, (xs[-1] / 2) if xs else 0, H / 2 + 2.5,
           f"SIGNAL PATH — {p['answered']}/{p['total']} decisions · {p['constraints']} constraints",
           "detail sharpens as decisions accumulate")


if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else workspace.default_project()
    svg, png = render(proj)
    print(f"wrote {svg.name}, {png.name}")
