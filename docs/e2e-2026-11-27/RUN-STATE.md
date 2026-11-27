# Run state

| Stage | Student | Lecturer | Designer | Engineer | Alti | Gate |
|---|---|---|---|---|---|---|
| 1 Idea | done v4 | PASS r2 w/ conditions C1-C5 | 6/10 (r2), C1-C28 answered | 4 WRONG sys (guard revert, BOOT1, stale desc, SWD label) | n/a | PASS 02:35 |
| 2 BOM | done 30 lines / 52 parts | PASS r2 w/ conditions K1-K5 | 5.5/10, C29-C48 answered | 9 WRONG sys (qty 1, 51-parts claim, Altium project created despite Stop, false "schematic label" msg...) | n/a | PASS 02:19 |
| 3 Library | done (app could not fix lib defects) | PASS r2 w/ conditions L1-L5 | 5.5/10 (r2), C49-C67 | 3 WRONG (green Checked on unverified pins, wrong pitch preview, LED polarity uncited) | 3 WRONG (3D wrong side J1/J2, no courtyard, full paste on U1 EP) | PASS 03:0x |
| 4 Schematic | done (+R15, Idea v10 60x45) | PASS r2 w/ conditions M1-M4 (M1 done) | 5/10 | 2 WRONG (U4 false mismatch, silent failed build) | 1 WRONG (false D1 short); inter-sheet nets CONNECTED (verified) | PASS 05:5x |
| 5 Placement | done 60x45; decaps far (tool limit) | PASS r1 w/ gate N1 (waived as tool limit) | 5.5/10, C93-C109 | 4 WRONG (KO = top copper, agent denied stack change, SD decap missed) | 6 WRONG (stack default values, KO copper, decaps 15-28 mm, HSE 8 mm) | PASS 06:xx (ruling) |
| 6 Routing | done route #3 (+5V/VBUS 0.4, +3V3 still 0.127) | PASS r2 w/ conditions P1-P5 | 5/10 | 3 WRONG (power tracks 0.127 mm, vias blamed on footprints, silk fix disables empty rule) | DRC 424 -> 86 real; 4 real issues; P5: +5V/VBUS ok; signals under Y1/Y2; pours 0.16 mm to holes | PASS 07:xx |
| 7 Outputs | done 07:2x (gerbers.zip 53.8 kB, BOM_jlc, CPL, manifest; README into notes.md) | PASS r1 w/ conditions (CPL centroid; order-time checks to S8) | 5/10; overall 5.4/10 (SUMMARY) | 2 WRONG (outputs pass 424 DRC silently, order note contradicts Gerber on tenting) | 3 WRONG (CPL pad centres, EP full paste in GTP, S6 issues carried into Gerbers); 60x45, 4 Cu, drills ok | PASS 07:35 |
| 8 DFM (producer) | n/a | n/a | n/a | n/a | n/a | done 07:4x: JLC parsed 4 layers 45x60, $8/5 pcs anon; DFM viewer needs sign-in (stopped, verdict unknown); PCBA not tested (NEXT = cart); 2 WRONG (note 'Tent vias' vs 157 open vias; pre-order checks blind to mask webs + pour-to-NPTH) |

Sessions: student local_f4ea21df (Sonnet), lecturer local_0362bedb (Opus), designer local_27e3dabe (Sonnet), engineer local_0cebfc94 (Opus), alti local_0eb23159 (Opus), producer local_dd1de5b7 (Sonnet), fixer local_bdcef8b6 (Sonnet, worktree e2e-fixes-1127)
Code fixes during the run: #1 dbf3635 library rebuild lock (merged+pushed, verified live 03:52: built 31, fresh, in project)
## Resource policy (8GB RAM, pagefile raised to 2-16GB by the owner at 01:30)
- Each idle role session holds about 250MB. Roles not needed in the current or next stage are archived; they are restored
  with unarchive_session + SendMessage. Their conversation is kept (tested on the producer at 01:35: archive, unarchive and resume all work).
- Before archiving a role, its checkpoint goes below (last instruction, last report file), so a restored or replaced session can continue
  from the same point. If a restore ever fails, a new session gets: PROTOCOL.md + its role brief + this checkpoint + its report files.
- Check free RAM and commit before each Altium stage.

## Role checkpoints
- student: stage 7 done, parked (Chrome handed to the producer for stage 8). Next: only if the lecturer says FIX for S7.
- stage 7 reviews sent ~07:3x to lecturer, designer (+designer-SUMMARY.md), engineer, alti; producer started stage 8.
- after all: REPORT.md -> Fable opinion -> demo video -> morning report.
- lecturer, designer, engineer: S1 done (roles/*-S1.md, 2 rounds); idle until stage 2 ends.
- alti: S3 done (roles/alti-S3.md); call at end of stage 4.
- producer: restored 07:0x, idle; call after stage 7 with the Gerber zip path.
- fixer: ARCHIVED 01:45; branch claude/e2e-fixes-1127-fc2587, no bug yet; restore on first blocking bug.

- 07:36 ARCHIVED designer (S7 + designer-SUMMARY.md done) and student (all stages done, parked; nothing left unless S8 needs a UI action).

- 07:45 run COMPLETE (all 8 stages). Next: archive idle roles, REPORT.md (subagent draft + my check), Fable opinion, demo video, morning report.

- 08:0x DONE: REPORT.md (Opus draft, saved by orchestrator; 138/138 confusions, 37 distinct WRONG + 8 UI-state WRONG), FABLE-OPINION.md, video/e2e-demo.mp4 (21 min, silent) and video/e2e-demo-4min.mp4 (3:53, neural narration en-US-AndrewNeural via edge-tts, owner approved). All role sessions archived; fixer idle.

## Schedule
- Hourly self-check at :07 (+ jitter). One-shot resume check at 05:15 (quota resets at 05:00).
- At the end: REPORT.md, then one Fable subagent reviews the logs and outputs -> FABLE-OPINION.md.

Early finding S0: "New project" click froze the page ~45 s (student log), under heavy RAM pressure; check if reproducible.
ffmpeg for demo video: /c/Users/ilaish/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.1-full_build/bin/ffmpeg.exe

## Demo video plan (owner, 02:30)
Animated, Remotion style: cursor moving to each click + ripple, typing text, zoom/pan to action, stage title cards, reviewer callout
cards (Video highlights) and lecturer verdict at each gate. Built at the end with Python (Pillow frames) + ffmpeg 9.1 (installed),
from screens/ + roles/student-actions.jsonl + roles/*-S*.md highlights. No Node on this PC; Remotion itself would need Node + npm +
its headless Chrome, so it is NOT installed overnight without asking; the Python renderer gives the same effects.
Renderer runs only after the run ends (RAM).
