"""4-minute narrated cut of the E2E demo. Reuses make_demo's drawing; narration with the local Windows voice (System.Speech).
Usage: python make_short.py [--out e2e-demo-4min.mp4]
"""
import argparse, json, pathlib, subprocess, wave, array
import make_demo as m
from make_demo import W, H, Image, ImageDraw, ease, img, camera, cam_point, to_canvas, draw_cursor, ripple, overlay_chrome, callout, title_card, Shot

OUT = pathlib.Path(__file__).resolve().parent
SR = 22050
STAGE_SECS = 25.0

SAY = {
    "intro": "P C B advisor, final end-to-end test. A simulated student builds a four-layer S T M 32 U S B C sensor hub, from a one-line idea "
             "to a J L C manufacturing check, using only the web app. Five A I reviewers judge every stage.",
    1: "Stage one: idea and requirements, on Claude Code. The student describes the board in the chat, and the agent drafts the requirements "
       "and the block diagram. Yellow cards mark real moments of student confusion. The lecturer sent this stage back once, then passed it.",
    2: "Stage two: parts and J L C stock. The agent picks components with L C S C codes and checks availability. The engineer caught real errors: "
       "every B O M line said quantity one, the app claimed fifty-one parts, and it created an Altium project after the student pressed stop.",
    3: "Stage three: the component library, now on Antigravity. Overnight, an Altium error dialog froze the build. It was fixed, reviewed and "
       "pushed during the run. The Altium checker still found 3 D bodies on the wrong side of both connectors, and full solder paste on the "
       "M C U's exposed pad.",
    4: "Stage four: the schematic, drawn in Altium. The compiled netlist matched the design exactly: fifty-five nets, two hundred and twenty-six "
       "pins. But the app warned about a diode short and a pin conflict that did not exist.",
    5: "Stage five: placement, back on Claude Code. The board grows to sixty by forty-five millimetres. The tool cannot place decoupling "
       "capacitors next to their pins, and its corner keep-outs were drawn as top-layer copper.",
    6: "Stage six: routing and the design rule check, on Antigravity. The board routes on the third run, but power tracks came out at "
       "minimum width, signals pass under the crystals, and a green tick sat over four hundred and twenty-four rule violations.",
    7: "Stage seven: manufacturing outputs, on Claude Code. Gerbers, drill, B O M and pick-and-place files are generated in forty seconds, "
       "while the rule violations are still open, behind only a warning banner.",
    8: "Stage eight: the manufacturer. The producer uploads the Gerbers to J L C, without signing in or ordering. J L C reads four layers, "
       "sixty by forty-five millimetres, eight dollars for five boards. The detailed D F M viewer needs a login, so the run stopped there.",
    "outro": "The verdict: from idea to schematic, the system is solid. From library to order, it still makes professional errors, and "
             "sometimes claims a success it did not verify. One hundred and thirty-eight student confusions, and every finding, are in the report.",
}
GATE = {1: "PASS · round 2 · conditions C1-C5", 2: "PASS · round 2 · conditions K1-K5", 3: "PASS · round 2 · library defects = tool limit",
        4: "PASS · round 2 · conditions M1-M4", 5: "PASS · orchestrator ruling (decap distance = tool limit)",
        6: "PASS · round 2 · conditions P1-P5", 7: "PASS · conditions carried to the JLC order", 8: "JLC parsed OK · DFM verdict behind login"}
ROLE_ORDER = {"lecturer": 0, "engineer": 1, "alti": 2, "producer": 3, "designer": 4}


EDGE_PY = pathlib.Path(r"C:\Users\ilaish\AppData\Local\Temp\claude\efecd7ce72b47997\1ae74da2-79ab-4d85-b8a6-e04553b29aa5\scratchpad\ttsenv\Scripts\python.exe")
EDGE_VOICE = "en-US-AndrewNeural"
SPELLED = {"P C B": "PCB", "J L C": "JLC", "S T M 32": "STM32", "U S B C": "USB-C", "L C S C": "LCSC", "B O M": "BOM",
           "3 D": "3D", "M C U": "MCU", "D F M": "DFM", "A I": "AI"}


def tts_edge(items):
    """Neural voice through edge-tts (separate venv), converted to 22.05 kHz mono wav."""
    d = OUT / "tts"
    d.mkdir(exist_ok=True)
    jobs = {}
    for k, v in items.items():
        for a, b in SPELLED.items():
            v = v.replace(a, b)
        jobs[str(d / f"edge_{k}.mp3")] = v
    (d / "edge_jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    script = ("import asyncio,json,sys,edge_tts\n"
              "jobs=json.load(open(sys.argv[1],encoding='utf-8'))\n"
              "async def main():\n"
              "    for path,text in jobs.items():\n"
              f"        await edge_tts.Communicate(text,'{EDGE_VOICE}',rate='+4%').save(path)\n"
              "asyncio.run(main())\n")
    (d / "edge_run.py").write_text(script, encoding="utf-8")
    subprocess.run([str(EDGE_PY), "-I", str(d / "edge_run.py"), str(d / "edge_jobs.json")], check=True)
    out = {}
    for k in items:
        mp3, wav = d / f"edge_{k}.mp3", d / f"edge_{k}.wav"
        subprocess.run([m.FFMPEG, "-y", "-loglevel", "error", "-i", str(mp3), "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", str(wav)], check=True)
        out[k] = wav
    return out


def tts(items):
    """items {key: text} -> {key: wav path}. Neural edge-tts voice; local Windows voice as the fallback."""
    try:
        return tts_edge(items)
    except Exception as exc:
        print(f"edge-tts failed ({exc}); using the local voice", flush=True)
    d = OUT / "tts"
    d.mkdir(exist_ok=True)
    jobs = {str(k): str(d / f"say_{k}.wav") for k in items}
    (d / "jobs.json").write_text(json.dumps({jobs[str(k)]: v for k, v in items.items()}), encoding="utf-8")
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        f"$j = Get-Content -Raw -Encoding UTF8 '{d / 'jobs.json'}' | ConvertFrom-Json;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SelectVoice('Microsoft Zira Desktop'); $s.Rate = 1;"
        f"$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({SR}, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono);"
        "foreach ($p in $j.PSObject.Properties) { $s.SetOutputToWaveFile($p.Name, $fmt); $s.Speak($p.Value) }; $s.SetOutputToNull()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return {k: pathlib.Path(jobs[str(k)]) for k in items}


def wav_len(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def key_shot(stage, path, prev, act, card, dur):
    kind = (act or {}).get("kind")
    has_xy = bool(act and isinstance(act.get("x"), (int, float)) and act.get("x", 0) > 0 and prev and kind in ("click", "type", "select"))
    pre = 1.1 if has_xy else 0.0
    label = (act or {}).get("label") or ""
    if has_xy:
        px, py = to_canvas(prev, act)

    def fn(t, prog):
        if has_xy and t < pre:
            z = 1 + 0.3 * ease(t / 0.7)
            zt = ease(t / 0.7)
            cx, cy = W / 2 + (px - W / 2) * zt, H / 2 + (py - H / 2) * zt
            fr = camera(img(prev)[0], cx, cy, z).convert("RGBA")
            o = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dr = ImageDraw.Draw(o)
            sx, sy = cam_point(px, py, cx, cy, z)
            st = ease(t / 0.7)
            draw_cursor(dr, W * 0.6 + (sx - W * 0.6) * st, H * 0.85 + (sy - H * 0.85) * st, 1.15)
            if t > 0.75:
                ripple(dr, sx, sy, t - 0.75)
            return overlay_chrome(Image.alpha_composite(fr, o), stage, label, prog)
        t2 = t - pre
        z = 1.0 + 0.05 * (t2 / max(1, dur - pre))
        fr = camera(img(path)[0], W / 2, H / 2, z)
        if t2 < 0.3 and prev:
            fr = Image.blend(img(prev)[0] if not has_xy else camera(img(prev)[0], px, py, 1.3), fr, ease(t2 / 0.3))
        fr = overlay_chrome(fr.convert("RGBA"), stage, label if not card else "", prog)
        if card and t2 > 0.4:
            role, text, tag = card
            fr = callout(fr, role, text, t2 - 0.4, tag=tag)
        return fr
    return Shot(dur, fn, stage)


def alti_shot(stage, role, path, text, dur):
    def fn(t, prog):
        fr = camera(img(path)[0], W / 2, H / 2, 1 + 0.06 * t / dur).convert("RGBA")
        fr = overlay_chrome(fr, stage, f"Altium evidence: {path.name}", prog)
        return callout(fr, role, text, t)
    return Shot(dur, fn, stage)


def plan_stage(st, screens, acts, confs, hl, extra):
    """Pick 3-5 key moments: reviewer highlights, one student confusion, one Altium image."""
    order = [p for s, n, p in screens if s == st]
    keyname = {p: f"S{st}-{int(m.NAME_RE.match(p.name).group(2)):02d}" for p in order}
    picks = {}
    cands = []
    for p in order:
        for role, text in hl.get(keyname[p], []):
            cands.append((ROLE_ORDER.get(role, 9), order.index(p), p, (role, text, None)))
    cands.sort(key=lambda x: (x[0], x[1]))
    for _, _, p, card in cands:
        if p not in picks and len(picks) < 3:
            picks[p] = card
    for p in order:  # one confusion, the gold
        if keyname[p] in confs and p not in picks:
            cid, text = confs[keyname[p]][0]
            picks[p] = ("student", text, cid)
            break
    i = 0
    while len(picks) < 3 and order:
        p = order[min(len(order) - 1, (i * len(order)) // 3 + len(order) // 6)]
        picks.setdefault(p, None)
        i += 1
        if i > 6:
            break
    chosen = sorted(picks, key=order.index)
    shots = []
    for p in chosen:
        idx = order.index(p)
        prev = order[idx - 1] if idx > 0 else None
        act = (acts.get(keyname[p]) or [None])[-1]
        shots.append(("screen", p, prev, act, picks[p]))
    for role, path, text in extra.get(st, []):
        if path is not None:
            shots.append(("alti", path, role, text))
            break
    return shots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT / "e2e-demo-4min.mp4"))
    ap.add_argument("--fps", type=int, default=25)
    a = ap.parse_args()
    screens = m.load_screens(set(range(1, 9)))
    acts, confs, (hl, extra) = m.load_actions(), m.load_confusions(), m.load_highlights()
    wavs = tts(SAY)
    shots, audio = [], []  # audio: (start_sec, wav)
    t = 0.0

    def add(sh):
        nonlocal t
        shots.append(sh)
        t += sh.dur

    intro_len = max(14.0, wav_len(wavs["intro"]) + 1.5)
    audio.append((0.6, wavs["intro"]))
    add(title_card("pcb-advisor · final end-to-end run", "Idea to manufacturable 4-layer PCB, one student, five reviewers",
                   ["STM32F411 USB-C sensor hub · 4 layers · 60 x 45 mm · 55 parts",
                    "Engines switch between Claude Code and Antigravity",
                    "Lecturer · Designer · Engineer · Alti (Altium) · Producer (JLC)",
                    "Yellow cards = real student confusions"], dur=intro_len))
    for st in range(1, 9):
        name, engine = m.STAGES[st]
        speech = wav_len(wavs[st])
        total = max(STAGE_SECS, speech + 5.5)
        audio.append((t + 0.4, wavs[st]))
        add(title_card(f"Stage {st} · {name}", f"engine: {engine}", dur=2.6, stage=st))
        plan = plan_stage(st, screens, acts, confs, hl, extra)
        each = (total - 2.6 - 2.8) / max(1, len(plan))
        for item in plan:
            if item[0] == "screen":
                _, p, prev, act, card = item
                add(key_shot(st, p, prev, act, card, each))
            else:
                _, path, role, text = item
                add(alti_shot(st, role, path, text, each))
        add(title_card(f"Gate · Stage {st}", GATE[st], dur=2.8, stage=st,
                       color=(40, 180, 110) if GATE[st].startswith("PASS") else (240, 150, 40)))
    outro_len = max(15.0, wav_len(wavs["outro"]) + 2.0)
    audio.append((t + 0.5, wavs["outro"]))
    add(title_card("What the run found", "solid front half · back half still makes professional errors",
                   ["138 student confusions · every finding with evidence",
                    "1 blocking bug fixed live (library rebuild lock)",
                    "Full report: docs/e2e-2026-11-27/REPORT.md"], dur=outro_len))
    total = t
    print(f"{len(shots)} shots, {total/60:.2f} min", flush=True)

    # audio track
    buf = array.array("h", bytes(int(total * SR) * 2 + SR * 2))
    for start, wp in audio:
        with wave.open(str(wp)) as w:
            assert w.getframerate() == SR and w.getsampwidth() == 2 and w.getnchannels() == 1
            data = array.array("h", w.readframes(w.getnframes()))
        o = int(start * SR)
        buf[o:o + len(data)] = data
    wav_out = OUT / "tts" / "narration.wav"
    with wave.open(str(wav_out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(buf.tobytes())

    ff = subprocess.Popen([m.FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(a.fps), "-i", "-", "-i", str(wav_out), "-c:v", "libx264", "-preset", "medium", "-crf", "21",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", a.out],
                          stdin=subprocess.PIPE)
    done = 0.0
    for sh in shots:
        nf = max(1, int(round(sh.dur * a.fps)))
        for f in range(nf):
            tt = f / a.fps
            ff.stdin.write(sh.fn(tt, (done + tt) / total).convert("RGB").tobytes())
        done += sh.dur
    ff.stdin.close()
    ff.wait()
    print("done", a.out, ff.returncode)


if __name__ == "__main__":
    main()
