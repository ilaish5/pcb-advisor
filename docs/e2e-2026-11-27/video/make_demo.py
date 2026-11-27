"""Animated demo video of the E2E run (Remotion-style, rendered with Pillow + ffmpeg).

Inputs (RUN folder): screens/*.jpg, roles/student-actions.jsonl, roles/student-confusions.md,
roles/<role>-S<n>.md "## Video highlights", alti/*.png, RUN-STATE.md.
Usage: python make_demo.py [--stages 1,2] [--out demo.mp4] [--fps 25]
"""
import argparse, json, math, pathlib, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

RUN = pathlib.Path(__file__).resolve().parent.parent
FFMPEG = r"C:\Users\ilaish\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.1-full_build\bin\ffmpeg.exe"
W, H = 1280, 720
F = "C:/Windows/Fonts/"
def font(name, size):
    return ImageFont.truetype(F + name, size)
FT = {"h1": font("segoeuib.ttf", 54), "h2": font("segoeuib.ttf", 30), "b": font("segoeui.ttf", 22),
      "bb": font("segoeuib.ttf", 22), "s": font("segoeui.ttf", 18), "sb": font("segoeuib.ttf", 18),
      "mono": font("consola.ttf", 22), "xs": font("segoeui.ttf", 15)}
BG = (14, 17, 24)
ROLE = {"lecturer": ((220, 70, 70), "Lecturer"), "designer": ((160, 100, 230), "Designer (UI/UX)"),
        "engineer": ((60, 140, 230), "Engineer (system)"), "alti": ((240, 150, 40), "Alti (Altium outputs)"),
        "producer": ((40, 180, 110), "Producer (JLC)"), "student": ((250, 200, 40), "Student: confused")}
STAGES = {0: ("Setup", "Settings"), 1: ("Idea + requirements", "Claude Code"), 2: ("BOM + stock", "Claude Code"),
          3: ("Library", "Antigravity"), 4: ("Schematic", "Antigravity"), 5: ("Placement", "Claude Code"),
          6: ("Routing + DRC", "Antigravity"), 7: ("Outputs", "Claude Code"), 8: ("JLC DFM", "Producer role")}

def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def wrap(text, fnt, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if fnt.getlength(nxt) <= width:
            cur = nxt
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def clip(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"

# ---------------- data ----------------
NAME_RE = re.compile(r"^S(\d+)-(\d+)")

def load_screens(stages):
    out = []
    for p in (RUN / "screens").iterdir():
        m = NAME_RE.match(p.name)
        if m and p.suffix.lower() in (".jpg", ".png") and int(m.group(1)) in stages:
            out.append((int(m.group(1)), int(m.group(2)), p))
    out.sort(key=lambda x: (x[0], x[1], x[2].name))
    return out

def key_of(name):
    m = NAME_RE.match(pathlib.Path(name or "").name)
    return f"S{int(m.group(1))}-{int(m.group(2)):02d}" if m else None

def load_actions():
    acts = {}
    for line in (RUN / "roles/student-actions.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        k = key_of(d.get("after"))
        if k:
            acts.setdefault(k, []).append(d)
    return acts

def load_confusions():
    out = {}
    for line in (RUN / "roles/student-confusions.md").read_text(encoding="utf-8").splitlines():
        if not re.match(r"^C\d+\s*\|", line):
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 6:
            continue
        shot = parts[-1].split(",")[0].strip().strip("`")
        k = key_of(shot)
        if k:
            out.setdefault(k, []).append((parts[0], parts[2]))
    return out

def load_highlights():
    """{screen_key: [(role, text)]}, {stage: [(role, image_path|None, text)]} for alti images / unknown shots."""
    on_shot, extra = {}, {}
    for p in sorted((RUN / "roles").glob("*-S*.md")):
        m = re.match(r"([a-z]+)-S(\d+)", p.stem)
        if not m or m.group(1) not in ROLE:
            continue
        role, stage = m.group(1), int(m.group(2))
        txt = p.read_text(encoding="utf-8", errors="replace")
        sec = re.search(r"## Video highlights\s*\n(.*?)(\n## |\Z)", txt, re.S)
        if not sec:
            continue
        for line in sec.group(1).splitlines():
            line = line.strip().lstrip("-* ").strip()
            if "|" not in line:
                continue
            ref, text = [x.strip().strip("`") for x in line.split("|", 1)]
            k = key_of(ref)
            if k:
                on_shot.setdefault(k, []).append((role, text))
                continue
            img = None
            for cand in (RUN / ref, RUN / "alti" / pathlib.Path(ref).name, RUN / "screens" / pathlib.Path(ref).name):
                if cand.is_file() and cand.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    img = cand
                    break
            extra.setdefault(stage, []).append((role, img, text))
    return on_shot, extra

def load_gates():
    gates = {}
    for line in (RUN / "RUN-STATE.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(\d) [^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", line)
        if m:
            gates[int(m.group(1))] = {"lecturer": m.group(3).strip(), "designer": m.group(4).strip(),
                                      "engineer": m.group(5).strip(), "alti": m.group(6).strip(), "gate": m.group(7).strip()}
    return gates

# ---------------- drawing ----------------
_cache = {}
def img(path):
    if path not in _cache:
        if len(_cache) > 6:
            _cache.pop(next(iter(_cache)))
        im = Image.open(path).convert("RGB")
        s = min(W / im.width, H / im.height)
        canvas = Image.new("RGB", (W, H), BG)
        fitted = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
        ox, oy = (W - fitted.width) // 2, (H - fitted.height) // 2
        canvas.paste(fitted, (ox, oy))
        _cache[path] = (canvas, s, ox, oy, im.width, im.height)
    return _cache[path]

def to_canvas(path, act):
    """Map an action's x/y (in the Chrome frame) to canvas pixels."""
    canvas, s, ox, oy, iw, ih = img(path)
    fw, fh = act.get("frame_w") or iw, act.get("frame_h") or ih
    return ox + act["x"] * iw / fw * s, oy + act["y"] * ih / fh * s

def camera(base, cx, cy, z):
    if z <= 1.001:
        return base.copy()
    cw, ch = W / z, H / z
    x0 = min(max(cx - cw / 2, 0), W - cw)
    y0 = min(max(cy - ch / 2, 0), H - ch)
    return base.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))

def cam_point(px, py, cx, cy, z):
    cw, ch = W / z, H / z
    x0 = min(max(cx - cw / 2, 0), W - cw)
    y0 = min(max(cy - ch / 2, 0), H - ch)
    return (px - x0) * z, (py - y0) * z

CURSOR = [(0, 0), (0, 26), (7, 20), (12, 31), (17, 29), (12, 18), (21, 18)]
def draw_cursor(d, x, y, scale=1.0):
    pts = [(x + px * scale, y + py * scale) for px, py in CURSOR]
    d.polygon([(a + 2, b + 2) for a, b in pts], fill=(0, 0, 0, 90))
    d.polygon(pts, fill=(255, 255, 255, 255), outline=(20, 20, 20, 255))

def rounded(d, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)

def overlay_chrome(frame, stage, label, progress, extra_badge=None):
    o = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(o)
    name, engine = STAGES.get(stage, ("", ""))
    chip = f"Stage {stage} · {name}"
    w = FT["sb"].getlength(chip) + 28
    rounded(d, (16, 14, 16 + w, 46), 14, (10, 12, 18, 215))
    d.text((30, 18), chip, font=FT["sb"], fill=(255, 255, 255, 255))
    eng = f"engine: {engine}"
    w2 = FT["xs"].getlength(eng) + 22
    rounded(d, (24 + w, 16, 24 + w + w2, 44), 12, (40, 46, 60, 215))
    d.text((35 + w, 21), eng, font=FT["xs"], fill=(190, 200, 220, 255))
    if extra_badge:
        w3 = FT["sb"].getlength(extra_badge) + 28
        rounded(d, (W - 16 - w3, 14, W - 16, 46), 14, (250, 200, 40, 230))
        d.text((W - 2 - w3, 18), extra_badge, font=FT["sb"], fill=(20, 20, 20, 255))
    if label:
        lines = wrap(clip(label, 170), FT["b"], W - 80)[:2]
        bh = 18 + 30 * len(lines)
        rounded(d, (24, H - 26 - bh, W - 24, H - 22), 12, (10, 12, 18, 200))
        for i, ln in enumerate(lines):
            d.text((40, H - 22 - bh + 8 + 30 * i), ln, font=FT["b"], fill=(240, 240, 245, 255))
    d.rectangle((0, H - 6, W, H), fill=(40, 44, 56, 255))
    d.rectangle((0, H - 6, int(W * progress), H), fill=(90, 160, 255, 255))
    return Image.alpha_composite(frame.convert("RGBA"), o)

def callout(frame, role, text, t, tag=None):
    """Slide-in review card on the right."""
    color, title = ROLE[role]
    o = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(o)
    cw = 470
    lines = wrap(clip(text, 260), FT["b"], cw - 40)[:6]
    ch = 70 + 30 * len(lines)
    x = W - 24 - cw + int((1 - ease(t / 0.3)) * (cw + 40))
    y = 70
    rounded(d, (x + 4, y + 4, x + cw + 4, y + ch + 4), 16, (0, 0, 0, 110))
    rounded(d, (x, y, x + cw, y + ch), 16, (250, 250, 252, 245), outline=color + (255,), width=3)
    d.rectangle((x, y + 12, x + 8, y + ch - 12), fill=color + (255,))
    d.text((x + 24, y + 14), (tag + " · " if tag else "") + title, font=FT["sb"], fill=color + (255,))
    shown = int(len(" ".join(lines)) * min(1.0, max(0.0, (t - 0.2) / 0.9)))
    k = 0
    for i, ln in enumerate(lines):
        part = ln[: max(0, shown - k)]
        k += len(ln) + 1
        d.text((x + 24, y + 48 + 30 * i), part, font=FT["b"], fill=(25, 28, 36, 255))
    return Image.alpha_composite(frame, o)

def ripple(d, x, y, t):
    if 0 <= t <= 0.5:
        r = 8 + 40 * ease(t / 0.5)
        a = int(200 * (1 - t / 0.5))
        d.ellipse((x - r, y - r, x + r, y + r), outline=(90, 160, 255, a), width=4)
        d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(90, 160, 255, a))

def typing_box(d, text, t, x=None, y=None):
    text = clip(text, 150)
    n = int(len(text) * min(1.0, t / max(0.6, min(2.4, len(text) / 45))))
    shown = text[:n] + ("▌" if int(t * 3) % 2 == 0 else " ")
    lines = wrap(shown, FT["mono"], W - 260)[-3:]
    bh = 24 + 32 * len(lines)
    bx, by = 120, H - 140 - bh
    rounded(d, (bx, by, W - 120, by + bh), 14, (255, 255, 255, 245), outline=(90, 160, 255, 255), width=3)
    for i, ln in enumerate(lines):
        d.text((bx + 18, by + 12 + 32 * i), ln, font=FT["mono"], fill=(20, 24, 32, 255))

# ---------------- timeline ----------------
class Shot:
    def __init__(self, dur, fn, stage):
        self.dur, self.fn, self.stage = dur, fn, stage

def title_card(title, sub, lines=(), dur=2.6, stage=None, color=(90, 160, 255)):
    def fn(t, prog):
        im = Image.new("RGBA", (W, H), BG + (255,))
        d = ImageDraw.Draw(im)
        for i in range(0, W, 40):
            d.line((i, 0, i - 300, H), fill=(22, 26, 36, 255), width=1)
        a = ease(t / 0.5)
        y = 220 + int((1 - a) * 30)
        d.rectangle((120, y - 16, 128, y + 70), fill=color + (255,))
        d.text((150, y - 14), title, font=FT["h1"], fill=(255, 255, 255, int(255 * a)))
        n = int(len(sub) * min(1, max(0, (t - 0.4) / 0.9)))
        d.text((152, y + 66), sub[:n], font=FT["h2"], fill=(170, 190, 220, 255))
        for i, ln in enumerate(lines):
            if t > 0.9 + 0.25 * i:
                d.text((152, y + 130 + 34 * i), ln, font=FT["b"], fill=(210, 215, 225, 255))
        d.rectangle((0, H - 6, int(W * prog), H), fill=(90, 160, 255, 255))
        return im
    return Shot(dur, fn, stage)

def screen_shot(stage, path, prev_path, act, confs, calls):
    kind = (act or {}).get("kind") or (act or {}).get("action")
    has_xy = bool(act and isinstance(act.get("x"), (int, float)) and act.get("x", 0) > 0 and prev_path and kind in ("click", "type", "select", "key", "scroll"))
    label = (act or {}).get("label") or ""
    if kind == "type" and act.get("text"):
        label = f'{label}: "{clip(act["text"], 90)}"'
    move = 0.6 if has_xy else 0.0
    typ = min(1.8, max(0.7, len(act.get("text") or "") / 55)) + 0.3 if has_xy and kind == "type" else 0.0
    click = 0.35 if has_xy else 0.0
    fade = 0.3
    wait = act.get("secs") if act and kind == "wait" else None
    hold = (0.9 if (has_xy or confs or calls) else 0.45) + (0.5 if wait else 0)
    confs, calls = confs[:1], calls[:2]
    seg_conf = 2.8 * len(confs)
    seg_call = 3.0 * len(calls)
    total = move + typ + click + fade + hold + seg_conf + seg_call
    if has_xy:
        px, py = to_canvas(prev_path, act)
        # keep the click point in the after image too (same frame) when the after image differs in size
        qx, qy = px, py
    else:
        px = py = qx = qy = None
    z_in = 1.35 if has_xy else 1.0

    def fn(t, prog):
        if has_xy and t < move + typ + click:
            base = img(prev_path)[0]
            zt = ease(t / move) if move else 1
            z = 1 + (z_in - 1) * zt
            cx, cy = W / 2 + (px - W / 2) * zt, H / 2 + (py - H / 2) * zt
            fr = camera(base, cx, cy, z).convert("RGBA")
            o = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(o)
            sx, sy = cam_point(px, py, cx, cy, z)
            st = ease(t / move) if move else 1
            curx, cury = W * 0.62 + (sx - W * 0.62) * st, H * 0.85 + (sy - H * 0.85) * st
            tc = t - move
            if 0 <= tc and kind == "type" and act.get("text"):
                typing_box(d, act["text"], tc)
            if t >= move + typ:
                ripple(d, sx, sy, t - move - typ)
            draw_cursor(d, curx, cury, 1.15)
            fr = Image.alpha_composite(fr, o)
            return overlay_chrome(fr, stage, label, prog)
        t2 = t - (move + typ + click)
        cur = img(path)[0]
        zt = 1 - ease(t2 / 0.7) if has_xy else 0
        z = 1 + (z_in - 1) * zt
        cx, cy = (W / 2 + (qx - W / 2) * zt, H / 2 + (qy - H / 2) * zt) if has_xy else (W / 2, H / 2)
        if not has_xy:  # slow Ken Burns
            z = 1 + 0.04 * min(1, t2 / total)
        fr = camera(cur, cx, cy, z)
        if t2 < fade and prev_path:
            prev = camera(img(prev_path)[0], cx, cy, z) if has_xy else img(prev_path)[0]
            fr = Image.blend(prev, fr, ease(t2 / fade))
        fr = fr.convert("RGBA")
        if has_xy and t2 < 0.7:
            o = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sx, sy = cam_point(qx, qy, cx, cy, z)
            draw_cursor(ImageDraw.Draw(o), sx, sy, 1.15)
            fr = Image.alpha_composite(fr, o)
        badge = f"agent working · {int(wait)} s" if wait else None
        fr = overlay_chrome(fr, stage, label, prog, badge)
        t3 = t2 - fade - hold
        if t3 >= 0:
            if t3 < seg_conf:
                i = int(t3 // 2.8)
                cid, text = confs[i]
                fr = callout(fr, "student", text, t3 - 2.8 * i, tag=cid)
            else:
                t4 = t3 - seg_conf
                i = min(len(calls) - 1, int(t4 // 3.0))
                role, text = calls[i]
                fr = callout(fr, role, text, t4 - 3.0 * i)
        return fr
    return Shot(total, fn, stage)

def image_callout_shot(stage, role, path, text):
    def fn(t, prog):
        if path:
            base = img(path)[0]
            z = 1 + 0.06 * (t / 4.0)
            fr = camera(base, W / 2, H / 2, z).convert("RGBA")
        else:
            fr = Image.new("RGBA", (W, H), BG + (255,))
        fr = overlay_chrome(fr, stage, f"Review evidence: {path.name}" if path else "", prog)
        return callout(fr, role, text, t)
    return Shot(3.4, fn, stage)

def gate_card(stage, g):
    lines = []
    for r in ("lecturer", "designer", "engineer", "alti"):
        v = g.get(r, "")
        if v and v.lower() not in ("n/a", "reviewing", "reviewing (+summary)"):
            lines.append(f"{ROLE[r][1].split(' (')[0]}: {clip(v, 95)}")
    gate = g.get("gate", "")
    return title_card(f"Gate · Stage {stage}", clip(gate or "-", 60), lines, dur=3.6 + 0.4 * len(lines), stage=stage,
                      color=(40, 180, 110) if "PASS" in gate else (220, 70, 70))

def build(stages):
    screens = load_screens(stages)
    acts, confs, (hl, extra), gates = load_actions(), load_confusions(), load_highlights(), load_gates()
    shots = [title_card("pcb-advisor · final end-to-end run", "Idea to manufacturable 4-layer PCB, one student, five reviewers",
                        ["Board: STM32F411 USB-C sensor hub, 4 layers, 60 x 45 mm, 54 parts",
                         "Student drives the web app in Chrome; engines switch between Claude Code and Antigravity",
                         "Lecturer · Designer (UI/UX) · Engineer (system) · Alti (Altium) · Producer (JLC DFM)",
                         "Night of 27 Nov 2026 · every yellow card is a real student confusion"], dur=6.5)]
    prev = None
    for st in sorted({s for s, _, _ in screens}):
        name, engine = STAGES.get(st, ("", ""))
        shots.append(title_card(f"Stage {st} · {name}", f"engine: {engine}", stage=st))
        for s, n, p in [x for x in screens if x[0] == st]:
            k = f"S{s}-{n:02d}"
            act = (acts.get(k) or [None])[-1]
            shots.append(screen_shot(st, p, prev, act, confs.get(k, []), hl.get(k, [])))
            prev = p
        for role, path, text in extra.get(st, []):
            shots.append(image_callout_shot(st, role, path, text))
        if st in gates and st > 0:
            shots.append(gate_card(st, gates[st]))
    nconf = sum(len(v) for v in confs.values())
    shots.append(title_card("What the run found", "the system will stand or fall on user experience",
                            [f"{len(screens)} screenshots · {sum(len(v) for v in acts.values())} logged student actions",
                             f"{len((RUN / 'roles/student-confusions.md').read_text(encoding='utf-8').split(chr(10)+'C')) - 1} student confusion entries ({nconf} shown on screen)",
                             "Full findings: docs/e2e-2026-11-27/REPORT.md"], dur=6.0))
    return shots

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default="0,1,2,3,4,5,6,7,8")
    ap.add_argument("--out", default=str(RUN / "video" / "e2e-demo.mp4"))
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    shots = build({int(x) for x in a.stages.split(",")})
    total = sum(s.dur for s in shots)
    print(f"{len(shots)} shots, {total/60:.1f} min", flush=True)
    if a.dry:
        return
    ff = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(a.fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                           "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out], stdin=subprocess.PIPE)
    done = 0.0
    for i, s in enumerate(shots):
        nf = max(1, int(round(s.dur * a.fps)))
        for f in range(nf):
            t = f / a.fps
            fr = s.fn(t, (done + t) / total).convert("RGB")
            ff.stdin.write(fr.tobytes())
        done += s.dur
        if i % 20 == 0:
            print(f"{i}/{len(shots)} {done/total:.0%}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done", a.out, ff.returncode)

if __name__ == "__main__":
    main()
