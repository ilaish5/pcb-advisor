# pcb-advisor final E2E run, 27 Nov 2026

**What was built.** A simulated student (Sonnet, web UI only, no hand work in Altium) took a new project `Final-E2E-4L` from a one-line idea to a JLC upload: an STM32F411CEU6 USB-C sensor hub (LSM6DSO IMU on SPI, BME280 on I2C, W25Q128JV flash, 4-bit SDIO microSD, 25 MHz + 32.768 kHz crystals, LDL1117 LDO, USBLC6 + TVS + polyfuse, SWD 2x5). Final state: 4 copper layers, 60 x 45 mm, 31 BOM lines / 55 parts, 3 schematic sheets, route #3 with 39 nets, 762 tracks and 157 vias (0 shorts, 0 clearance, 0 unrouted, Altium DRC 424), Gerber zip of 14 files (53,838 bytes), JLC BOM and CPL. 312 files in `screens/`, 138 student confusion entries.

**Stages and engines.** Claude Code CLI (Opus) for stages 1, 2, 5 and 7; Antigravity CLI (Gemini) for stages 3, 4 and 6; stage 8 was done by the producer role on jlcpcb.com. Every gate passed, five of them only after a lecturer FIX round. One blocking bug was fixed mid-run (fix #1, dbf3635: library rebuild on a locked IntLib).

**Did it reach JLC?** Yes. JLC parsed the zip as "4 layer board of 45x60mm", $8.00 for 5 pcs (anonymous quote). JLC's own DFM verdict is **unknown**: the Gerber Viewer requires sign-in, and the producer stopped there. PCBA (BOM/CPL matching, rotation) was not tested, because NEXT creates a cart item.

**The three most serious system problems:**
1. **Confident statements and success states that are false**, which breaks the owner's first priority. Examples: a green "Checked: nothing to verify" on pins nobody checked; "The BOM now has 51 parts" after no-op cards; a fixed "updated ... on the schematic label and in the library" approval text; "keep-outs have no copper" while they are copper; the agent denying it changes the layer stack; a false D1 short; a false U4 pin conflict; silk advice that cannot work; a green tick over 421 DRC; Outputs silent about 424 DRC; and an order note that says "Tent vias" for open vias.
2. **The board files carry defects the system itself created and did not detect.**
   - The stack is Altium's defaults, not the promised JLC04161H.
   - The corner keep-outs were drawn as Top copper. The fix deleted the requirement, so the inner pours end 0.16 mm from the M3 holes.
   - Vias are left untented next to pads on HASL (86 mask dams under 0.10 mm on route #3, per Alti).
   - Placement and routing ignore the pins: the VCAP1 cap is 15.7 mm away (17.4 mm of trace), and signals run under both crystals.
   - Power tracks are rounded down to 0.127 mm, the QFN exposed pad gets a full paste opening, and the CPL centroid rule is unstated.
3. **Dead ends for a web-only student.** Every fix the tool cannot make (decap moves, footprint edits, via tenting, DRC fixes, ERC) becomes an Altium hand step, with no tracked state and no way to waive. Long waits give no sign of life: a 20-minute silent library build (the blocker) and 5-7 minute routes.

**Verdict.** The pipeline works end to end, and its core content is right:
- every IC pinout checked matches its datasheet;
- the netlist equals Altium's own compile (55 nets, 0 split or merged);
- the routing is complete with 0 shorts;
- the Gerber set is well formed and parsed by JLC on the first upload.

It is **not yet at the owner's bar**. Engineer and Alti filed 45 WRONG tags. After deduplication with the lecturer, producer and designer there are 37 distinct technical WRONG problems plus 8 UI-state WRONG items, and many of them are the tool stating something untrue rather than refusing. The UI/UX score is 5.4/10 (designer).

| Stage | Engine | Gate (lecturer) | Designer score | WRONG tags as filed (engineer + alti) | Headline |
|---|---|---|---|---|---|
| 1 Idea | Claude Code | FIX, then PASS r2 with C1-C5 | 6.5 r1 / 6 r2 | 4 + n/a = 4 | Datasheet claims all true, but the description went stale while the agent said "Updated the draft"; the guard deleted the student's notes |
| 2 BOM | Claude Code | FIX, then PASS r2 with K1-K5 | 5.5 / 5.5 | 9 + n/a = 9 (one is a repeat; 8 distinct) | Clean part identity and stock; Qty 1 everywhere, false "51 parts", crystals/LDO/VDDA wrong until asked, Altium project created after Stop |
| 3 Library | Antigravity | FIX, then PASS r2 with L1-L5 | 6 r1 / 5.5 r2 | 3 + 3 = 6 | All pinouts right; green "Checked" over unchecked pins, wrong preview pitch, no courtyard, J1/J2 3D/origin, EP full paste |
| 4 Schematic | Antigravity | FIX, then PASS r2 with M1-M4 | 5 | 2 + 1 = 3 | Netlist = Altium compile; BLOCKER library rebuild (fixed), false U4 conflict, false D1 short |
| 5 Placement | Claude Code | PASS r1 with N1-N4 (N1 waived by ruling) | 5.5 | 4 + 6 = 10 | Edges and holes right; keep-outs are copper, stack not JLC, decaps/HSE far from pins, agent denies changing layers |
| 6 Routing + DRC | Antigravity | FIX, then PASS r2 with P1-P5 | 5 | 3 + 5 = 8 | 39/39 routed, 0 shorts; power at 0.127 mm, untented vias misattributed, crystals routed over, hole rule silently skipped |
| 7 Outputs | Claude Code | PASS r1 with conditions (Q1-Q5, order page P2) | 5 (overall 5.4) | 2 + 3 = 5 | Complete, consistent files; outputs silent on 424 DRC, "Tent vias" note vs open vias, CPL centroid, EP paste in GTP |
| 8 JLC DFM | producer | n/a | n/a | producer: 2 | JLC parsed 4 layers 45x60, $8/5 pcs; DFM verdict behind sign-in (unknown); PCBA not tested |

Notes on the table:
- The counts are `[WRONG]` tags in each role file, not distinct problems. RUN-STATE gives the same numbers for S1-S5 and S7.
- For S6, RUN-STATE lists Alti's "4 real issues"; the 5 is my tally of Alti's `[WRONG]` tags.
- RUN-STATE logs the S1 gate at 02:35, after the S2 gate at 02:19. The S1 entry was evidently written late.

## Fixes made during the run

1. **Fix #1, commit dbf3635 (product code, the only code fix).** "Library rebuild: release the IntLib from the open Altium project before compiling, re-add it after (also on failure); an Altium error box ends the wait early and is explained."
   - **Trigger (03:47, BLOCKER, stage 4):** adding one 10 nF cap (C23) and pressing Build library ran 15-20 min and ended silently twice. Altium showed the modal "Could not create integrated library ...IntLib", because the installed IntLib was locked. The bridge said only "stopped in the middle". The page showed "Building in Altium" for 20+ min, and then asked the student to restart Altium and use the Projects panel (S4-40, C86).
   - **Response:** the orchestrator closed the modal (UIA Invoke) and restored the archived fixer session (Sonnet, worktree e2e-fixes-1127, branch `claude/e2e-fixes-1127-fc2587`).
   - **Fix and review:** the fix does LIBRELEASE + re-add, plus modal detection within 15 s. The orchestrator reviewed it and merged it into main at 03:51, then pushed and restarted the server. `tests/test_altium_library.py`: 30 passed.
   - **Verified live 03:52:** "Library built: 31 of 31 lines, IntLib installed in Altium", IntLib fresh and in the project, about 90 s (S4-43, C87).
   - **Not covered by the fix** (still open, see FRICTION A and J):
     - Rebuilding one part resets all 31 lines.
     - The running state is client-side only and is lost on reload.
     - A failed restore (WinError 1224, altium-log 03:32) reached the page as nothing.
2. **Test-harness change (not product code), 02:35.** The product's `scripts/tool_guard.py` restored or deleted every changed repo file at the end of an agent turn. Because the run folder sits inside the install, it deleted confusion entry C18 and screenshot S1-08. `docs/e2e-2026-11-27/` was added to `.git/info/exclude`. The guard's behaviour and its wording stay a system finding (W1).
3. **Operational recoveries (no code changed):**
   - The orchestrator closed the Altium modal at 03:47.
   - Alti's first compile-script launch (S4) left an Altium "Select Item To Run" box and a message box open, which blocked the bridge. Alti closed them via `bridge.release_executor()` and WM_CLOSE.

Every other finding was recorded only, per protocol: non-blocking findings are not fixed overnight. The orchestrator's rulings in DECISIONS.md:
- **02:58:** library defects the app cannot fix are not a run blocker.
- **05:51:** no manual stack work in Altium.
- **06:15:** N1 is waived as a tool limit.
- **06:57:** in the stack dispute, Alti is right.

## Findings by severity

Rules used here:
- **One entry per distinct system problem**, listing every stage and role that saw it.
- **Severity is the highest tag any role filed.** Where roles disagree, the dissent is named, and the ruling is given only where DECISIONS.md has one; otherwise "no ruling recorded".
- **[LIMIT, silent]** marks a tool limit the app does not disclose. **[LIMIT, stated]** marks one the app admitted when asked.
- **Roles:** Eng = engineer, Lect = lecturer, Des = designer. Stage and role are written as S6 Alti.

**Retracted or corrected findings (dropped or narrowed below):**
- **Engineer S5/S6 (corrected in engineer-S7).** The engineer had said "the PcbDoc stack IS JLC04161H-7628 (AdvisorBridge.pas:2673-2676)". That came from a code comment; the `StackLayerProps` calls are commented out (lines 2721-2724). The S6 claim that the agent's "doesn't use JLC's 4-layer stack-up" was inaccurate is withdrawn, since the agent was right. The S5 finding that the agent denied adding the inner layers stands.
- **Lecturer S3 r1 (withdrawn in S3 r2).** "J1 locating holes plated with a zero ring" came from the KiCad source. Altium holds them as NPTH.
- **Lecturer S4 r1 (withdrawn as WRONG in S4 r2).** "Checked claimed for inter-sheet connectivity". Alti's native compile showed 55 nets, 0 split, 0 merged. "NC as a magic net" stays FRICTION.
- **Engineer S1 r2:** C24 (SDIO D0 PB4 to PB7) is not a technical error; both pins carry SDIO_D0.
- **Designer S1 r2:** Confirm idea does save the draft (tooltip), so C14 is a clarity issue, not data loss.
- **Engineer S3 r2:** the chat later gave the correct J1 pitch (0.50 mm). The preview caption (0.65 mm) stays wrong.
- **Engineer S2 r2:** the r1 BOM engineering errors (LSE/HSE crystals, VDDA 1 uF, LDO dissipation, IMU requirement) are fixed in the data. The generic causes are unchanged.

### BLOCKER

**B1. Library rebuild after adding one part hangs 15-20 min and fails silently (installed IntLib locked).** Fixed mid-run.
- **Seen by:** S4 Lect (BLOCKER), Eng (WRONG), Des ("BLOCKER-class friction"). Confusions C77-C79, C84-C86.
- **Evidence:** S4-21, S4-22, S4-23, S4-38, S4-39, S4-40; `alti/altium-error-dialog-0346.png`; altium-log 03:28:54 / 03:32:01 ("Altium stopped in the middle of the script ... [TMessageForm] Error"; "The earlier library could not be put back ([WinError 1224] ...)").
- **Cause:** the rebuild is all-or-nothing on a locked installed IntLib, and modals and hangs were not detected.
- **Fixed by dbf3635.** Residual issues are listed under FRICTION A and J.

### WRONG: technical output or claims (37 distinct problems)

**Idea and requirements**

**W1. The tool guard reverts files the agent did not write, deletes them, and blames the agent.**
- **Seen by:** S1 Eng (WRONG), Lect (FRICTION), Des (C19 wording). Confusion C19.
- **Evidence:** S1-09-research-answer-end.jpg. The chat at 01:19:25 says "the agent edited system files: .../student-confusions.md, .../S1-08-research-wait.jpg; they were restored"; both files were the student's.
- **Cause:** `scripts/tool_guard.py`. `snapshot()` runs at turn start; `restore()` / `git rm --cached` + `unlink` run at turn end (~155-171). `refusal()` (~239) always says "the agent edited". The guard cannot tell who wrote a file, so it is a data-loss path.
- **Note:** the trigger was the harness writing into the repo; the mechanism is generic.

**W2. Requirements, description, goal and diagram drift from the decided content, while the agent says it updated them.**
- **Seen by:**
  - S1 Eng (2 WRONG: description stale after turns 2-3; SWD block "Debug (optional)"), Lect (WRONG: "Updated the draft with all your fixes" while the description contradicted).
  - S2 Eng (WRONG: IMU swap not in the requirements; "Logging 200 Hz"), Lect (FRICTION: change parked in an unsaved `idea-draft.json`; goal still "ME6211" after the LDO swap).
  - S4 Lect (FRICTION: board size 60x45 "Set" while the text says 45x35; "the fourth stale-text case").
  - Des (theme B).
- **Confusions:** C12, C13, C28, C43, C46, C96.
- **Evidence:** S1-03-second-answer.jpg, S1-04-third-answer.jpg, S1-07-confirmed-next-bom.jpg, S2-52-r2-u5-approved-idea-saved-v7.jpg, S4-69-board-size-set-60x45.jpg; turns-log 01:06:12 / 01:07:05 (no `idea.describe`).
- **Cause:** `idea.propose` and `idea.diagram.edit` do not regenerate or lint the goal, description or diagram against the agreed items and BOM parts. The layer selector reads the saved board (`ui/js/views/idea.js:221-240`).

**W3. Contradictory requirements accepted without warning.**
- **Seen by:** S1 Lect.
- **Evidence:** `idea.json` has "USB-C only ... no battery" together with "LSE runs the RTC for the timestamps". The agent wrote the sentence itself (chat 01:07:44).
- **Cause:** no needs-vs-provisions cross-check before Confirm.
- Fixed by the student after lecturer Q1 (VBAT to 3V3, time set by the host).

**W4. An unsourced claim survived the MCU change.**
- **Seen by:** S1 Lect.
- **Evidence:** "USB DFU via BOOT0 as backup" was supported only by the AN2606 **L4** tables (chat 01:04:46). It was not re-checked after the swap to F411 (01:06:12), and there is no cite in `cites.json`.
- **Cause:** derived items are not re-validated or marked "unverified" when the item they derive from changes.
- Later marked "unverified (AN2606 not read)", which the lecturer accepted.

**W5. Confirmation state does not reflect the content.**
- **Seen by:** S1 Lect (WRONG: 6 confirmed items still say "(assumed)"; FRICTION: confirmation not invalidated by later edits), Eng (COSMETIC / FRICTION), S2 Lect (FRICTION), Des (C27 "borderline WRONG").
- **Confusions:** C14, C27, C28.
- **Evidence:**
  - `idea-versions.json` v2: all 16 items `confirmed, by: agent`, 6 with "(assumed)".
  - `confirmed_at 01:08:13` while v4 (19 changes) was saved at 01:26:48, and v5-v8 up to 02:13.
  - S1-17-saved-v4-still-confirmed.jpg: no Confirm button. The agent still says "press Save, then Confirm idea".
- **Cause:** Save/Confirm promote drafts without looking at "assumed". `idea.js:141-142` shows "confirmed" whenever `I.confirmed` is set.

**W6. The DFU pin plan omits BOOT1/PB2.**
- **Seen by:** S1 Eng.
- **Evidence:** S1-15-pin-table.jpg (chat 01:25:16). PB2 (pin 20) is neither assigned nor tied low, although F411 Table 8 requires BOOT1=0 for system-memory boot.
- Became lecturer condition C1; fixed at BOM (R13 10k).
- **Cause:** the pin plan is not cross-checked against the MCU boot and bootloader pins.

**BOM**

**W7. First BOM: Qty 1 on every multi-part role; warned, but "Approve all" applied it.**
- **Seen by:** S2 Eng, Des (FRICTION). Confusions C30, C31.
- **Evidence:** S2-08-bom-approved-28-lines.jpg: 28 lines / 28 parts against about 70 expected.
- **Cause:** `bom.propose` accepts a role naming N parts with one ref. It should refuse or expand, not warn.

**W8. False "The BOM now has 51 parts"; no-op cards were counted as applied.**
- **Seen by:** S2 Eng, Lect, Des (FRICTION). Confusions C33, C35, C36.
- **Evidence:**
  - Chat 01:39:22. S2-13-agent-answer-warnings-again.jpg, S2-15-qty-still-1-after-reload.jpg.
  - `proposals.jsonl` p20261127013921739 has `changes == before`, "approved by auto".
  - Fixed only after the student complained, by re-sent cards with `refs`: two rounds, about 8 min.
- **Cause:** the count field is silently dropped; the chat reports the intended result, not the applied one.

**W9. A fixed approval text claims schematic and library updates that did not happen.**
- **Seen by:** S2 r2 Eng ("Approved. U5 is updated in the BOM, on the schematic label and in the library", chat 02:12:16, no library existed); S5 Eng (repeat for R5 at 05:24:58, Main.SchDoc still had PA10 NC).
- **Cause:** `scripts/serve.py:463` uses that string for every non-new proposal, whatever happened.

**W10. An approved card created a duplicate designator.**
- **Seen by:** S2 r2 Lect (WRONG), Eng (FRICTION). Confusion C47.
- **Evidence:** S2-55-stock-check-r4-duplicate.jpg. R4 sat on both the 360 ohm and the 680 ohm line; the header read 53 parts for about 10 min until the stock check caught it.
- **Cause:** applying a BOM card does not enforce unique refs.

**W11. Unrequested actions from a review chip: a library build, then an Altium project; Stop did not stop the plan; the side effect was hidden.**
- **Seen by:** S2 Eng (r1 and r2), Lect (r1 and r2), Des (FRICTION). Confusions C38, C41, C48.
- **Evidence:**
  - S2-29-whats-wrong-agent-builds-library.jpg, S2-30-library-build-failed-no-altium.jpg, S2-57-settings-altium-project-created.jpg.
  - altium-log 01:50:11 `new-project`, then 01:50:19 `skeleton`. The chat said only "(Not applied: library.build: stopped by the student before it ran)".
- **Cause:**
  - The chip wording "28 open ... how do I fix it" invites action.
  - The agent may call `library.build` and project creation without a gate.
  - Stop cancels only the pending step.

**W12. The datasheet binding is not refreshed on an MPN change.**
- **Seen by:** S2 Lect (WRONG), Eng and Lect r2 (FRICTION). Confusion C45.
- **Evidence:**
  - `bom.json` U5 `mpn: ME6211C33M5G-N` with `datasheet: AMS1117-3.3.pdf`, and the 01:39 budget used the AMS1117's 11 mA Iq.
  - Later "U5 <- LDL1117S33R.pdf: unchecked (does not mention ME6211A33PG-N)", because verify ran before the swap (S2-51-r2-datasheets-scans.jpg).
- **Cause:** a line update changes `mpn`/`lcsc` but does not re-bind or re-verify the datasheet.

**W13. Parts selected without datasheet-mandated checks.** All were fixed in round 2, only after reviewers asked.
- **Seen by:** S2 Eng (3 WRONG), Lect (WRONG on crystals). Confusion C42 (the fix).
- **Crystals:** LSE Y2 (FC-135, CL 12.5 pF) gm_crit 2.16 uA/V against F411 Table 38 limits of 0.56 / 1.50. HSE Y1 1.11 mA/V against 1 mA/V. No crystal datasheets were fetched.
- **VDDA:** the datasheet "1 uF // 10 nF" (Figure 43) was missing; VDDA had only a 100 nF.
- **LDO:** ME6211 SOT-23 at 0.29 W against Pd 300 mW, while the chat said only "It's 500 mA".
- **Cause:** the BOM flow has no gm_crit, dissipation or MCU-supply-scheme checks.
- **Note:** the round-2 numbers were all checked TRUE by the engineer (S2-35-r2-5-cards-crystals-ldo.jpg).

**Library**

**W14. A green "Checked: Pins: nothing to verify for this part" on parts whose pins were never checked.**
- **Seen by:** S3 Eng, Lect (WRONG), Des ("WRONG-looking", top UI finding); S7 Eng (U1 still unverified: the pin checker cannot parse the STM32 table, and its text "names 6 of its 49" is wrong).
- **Confusions:** C50, C53, C54, C60.
- **Evidence:** S3-10-j1-pins-tab.jpg, S3-21-y1-pins-tab.jpg, S3-25-d3-pins-tab.jpg, S3-38-u1-pins-tab.jpg. `bom.json` `library_entry.verify = unchecked` on U1-U5, F1, J1-J3, Y1, Y2.
- **Cause:** `ui/js/views/pages.js:70-78` `libPinsState` falls through to `['ok', ...]` when `pins_status` is empty, and it was empty on all 30 lines.

**W15. The footprint preview reports a wrong pad pitch.**
- **Seen by:** S3 Eng.
- **Evidence:** S3-08-j1-footprint-preview.jpg says "18 pads, pitch 0.65 mm"; the USB-C signal pads are at 0.50 mm. Y1's real 1.76 mm is shown as "1.778 mm" (S3-19-y1-footprint.jpg). The student recorded 0.65 as fact.
- **Cause:** `scripts/model_preview.py:239-248` `_pitch` takes the median nearest-neighbour distance, while its docstring promises "the commonest".

**W16. The LED polarity claim cites a page the agent could not read.**
- **Seen by:** S3 Eng.
- **Evidence:** chat 02:30:01, "matching the library {{src:KT-0805G.pdf|p. 2 ...}}". The page text has no polarity mark, `read_file` returned `None` (turns-log 02:30:01), and the check compared the library with itself. `cites.json` marks it `file_only`, but the chat shows it as a source.

**W17. The library has no real courtyard.** Mech 15 holds EasyEDA's body outline, which lies inside the pads on all 20 footprints.
- **Seen by:** S3 Alti, Lect (WRONG), Eng (FRICTION: label "courtyard"). Confusions C53, C55, C55b, C58.
- **Evidence:** `alti/S3-footprints-1.png`, S3-19-y1-footprint.jpg, S3-23-d3-footprint.jpg, S3-26-d4-footprint.jpg, S3-27-sw1-footprint.jpg.
- **Mitigation:** the tool's own placer uses pads + 0.25 mm (`scripts/altium/layout.py:19`). Altium DRC and hand edits have no courtyard.
- **Cause:** `scripts/partlib_convert.py:20` maps F.CrtYd to Mech 15 as is; `scripts/model_preview.py:26` labels it "courtyard".

**W18. J1/J2 3D bodies and origin are offset, and the issue was reported only as a cosmetic "Built, check".**
- **Seen by:** S3 Alti (WRONG: bodies on the wrong side of the footprint), Lect r2 (WRONG: a production-relevant origin error reported as a 3D warning), Eng (FRICTION); S5 Alti (COSMETIC: bodies sunk into the board in place).
- **Confusions:** C56, C57, C66.
- **Evidence:** `alti/S3-footprints-2.png`, S3-29-agent-models-answer.jpg, S3-53-origin-3d-answer.jpg; manifest warnings J1 2.2, J2 2.8, J3 1.0 mm.
- **Cause:** easyeda2kicad writes a (0,0,0) offset, which `partlib_convert` keeps. The offset check never compares the origin with the pad or body centre.
- **Unverified:** the "origin 1.42 / 2.32 mm off the body centre" figure is the product agent's own claim. Engineer-S3 marks it UNVERIFIED, while lecturer-S7 cites it as "S3 measured". See W34.

**W19. The U1 exposed pad gets a full 5.5 x 5.5 mm paste opening, and it reaches the stencil Gerber.**
- **Seen by:** S3 Alti, Lect (WRONG); S7 Alti (WRONG: GTP aperture D38 R 0.2165 x 0.2165 in at 54.0, 41.5). Confusions C61, C62.
- **Evidence:** `alti/S7-gerber-bottom-paste.png`; `easyeda/C60420` pad 49 `F.Cu F.Paste F.Mask`; PasteMaskExpansion is 0 for all.
- **Cause:** there is no exposed-pad paste rule in `partlib_convert`.
- [LIMIT, stated]: the agent said it cannot make a paste window or vias (S3-45-u1-ep-answer.jpg).

**Schematic**

**W20. A false U4 "Pins conflict", and the app offers to replace a correct part.**
- **Seen by:** S4 Eng (WRONG), Des (FRICTION). Confusions C75, C76.
- **Evidence:** S4-17-bom-page-u4-pins-conflict.jpg, S4-18-u4-pins-conflict-click-alternatives.jpg (the Alternatives list includes Keystone parts that are not flash), S4-20-u4-conflict-explained.jpg. library-log 03:16:42 / 03:23:16.
- **Why it is false:** on the -IQ ordering code the QE bit is fixed at 1, so IO3 is the correct name (W25Q128JVSIQ.pdf.txt 891-895).
- **Cause:** the pin-name compare reads the first name in a multi-function cell and ignores ordering-code notes.

**W21. A false "D1 pins 2 and 5 are one terminal" warning (GND and +5V), raised on every draw; the offered fix is a hand edit of the SchLib.**
- **Seen by:** S4 Alti (WRONG), Eng (FRICTION), Lect (FRICTION). Confusions C90, C91, C98.
- **Evidence:** S4-51-draw-warnings-d1-a3.jpg, S4-53-erc-answer-d1-not-shorted.jpg; altium-log 03:59:26; C7519 `lib.kicad_sym:163-165` (a polyline through the zener).
- **Cause:** `scripts/altium/draw.py:172-176` (the SchLib `joined` detection) reads any polyline between two pin ends as a wire.

**W22. "Review this sheet: 0 errors" missed a real bus risk and a datasheet requirement; check results never state their scope.**
- **Seen by:** S4 Lect (WRONG), Eng (FRICTION). Confusions C71, C73.
- **Evidence:** S4-13-review-sheet-answer.jpg.
  - It missed the LSM6DSO I2C/I3C block listening on the shared SPI1 SCK/MOSI (LSM6DSOTR.pdf.txt:625, 1663).
  - It missed the VDDA 10 nF until asked, then reversed itself two minutes later.
  - Three "0 errors" results in the same format: a check tool, a model-only review with tools `[]`, and a post-draw check.
- **Cause:** `scripts/checks/schematic.py` (docstring 8-14) checks only connectivity and power names, and is blind on numeric pin names. Nothing checks decoupling, EP, pull-ups or crystals.

**W23. The decoupling check gives a false pass, and the agent contradicted its own table.**
- **Seen by:** S4 r2 Lect (WRONG), S5 Eng (WRONG), Lect (WRONG), Des (FRICTION). Confusions C97, C108.
- **Evidence:** S4-74-q4-answer-decoupling-by-hand.jpg, S5-23-second-answer-contradicts-table.jpg. "C10 is the only cap over the limit" came 16 s after a table showing C19 at 28.5 mm.
- **Cause:** `scripts/checks/board.py:249-294` measures each cap to the nearest supplied pad of **any** non-passive part, so the microSD slot is never flagged (no cap within 10.9 mm per Eng/Alti; "no cap of any net within 8 mm" per Lect).

**Placement and stack**

**W24. The placer is not pin- or net-aware for decoupling and crystals, and the misses become routing defects.**
- **Seen by:** S5 Alti (4 WRONG: C10, VDDA, microSD, HSE), Lect (WRONG), Eng (FRICTION); S6 Alti (WRONG: VCAP1 routed 17.4 mm with 2 vias).
- **Confusions:** C103, C106, C107.
- **Evidence:** S5-16-distance-answer-keepout-correction.jpg, S5-22-new-distance-table-route-or-not.jpg, `alti/S5-placement.png`, `alti/S6-routing.png`. Figures:
  - C10 (VCAP1) 15.7 mm from pin 22.
  - C22 (VDDA 1 uF) 20.9 mm.
  - C19 (SD bulk) 28.4 mm from J2-4.
  - Y1 7.3 / 8.1 mm from U1 pins 5/6.
- The second run made C13, C19 and C22 worse, and replaced the first without saying so. The engineer's measurements matched the agent's table within 0.4 mm. (C4 to U2-8: Lect 1.9 mm, Alti 2.7 mm.)
- **Cause:** `scripts/altium/layout.py:1773` `decap_hints` ties a cap to a pin only when the role names a part or regulator; `_DECAP_IC` (`:1683`) never targets connectors. There is no "near pin X" constraint.
- [LIMIT, stated]: "Placing again can't put single parts at a pin" (C103, C107).
- **Ruling:** DECISIONS 06:15 waived lecturer gate N1 as a tool limit; it is recorded as a system finding.

**W25. The corner "keep-outs" KO1-KO4 are unnetted Top copper, while the system reports them clean.**
- **Seen by:**
  - S5 Eng, Alti (WRONG).
  - S6 Lect (WRONG): the remedy deleted the student's requirement.
  - S5 Lect (WRONG): wrong keep-out instructions.
  - S6 Eng (FRICTION).
- **Confusions:** C101, C104, C115, C116.
- **What happened:**
  1. The first route was rejected after about 6 min with 4 shorts (H1-H4 against the Top region).
  2. The agent's fix (Idea v13) removed the keep-out requirement instead of the defect.
  3. The agent had first said "run library.build, then place again", then "draw them on the Keep-Out layer yourself".
- **Evidence:** S5-26-final-placement-fit.jpg, `alti/S5-placement.png`, S6-17-route-rejected-4-short-circuits.jpg, S6-20-answer-keepouts-are-top-copper.jpg, S6-21-idea-saved-v13-ko-removed.jpg.
  - Regions6: `V7_LAYER=TOP|KIND=0`, keep-out flag 0.
  - board-facts.json: `ko_*: met, "no copper inside"`.
  - The agent at 05:55:44: "today they have no copper in them".
- **Cause:**
  - `partlib_generate.py:425-430` writes a Keep-Out region.
  - `AdvisorBridge.pas` `LayerOf` (~797) passes the layer name to `String2Layer`, which (inferred) gives 0.
  - `scripts/checks/requirements.py:98` skips `in_component` regions.
- **Consequence:** see W32.

**W26. The agent denied what the tool does to the layer stack.**
- **Seen by:** S5 Eng (WRONG; stands after the S7 correction), Alti (FRICTION: no agent tool exposes the stack), Lect (FRICTION). Confusions C100, C109.
- **Evidence:** S5-07-agent-cannot-set-stack-ko-cards.jpg ("None of my Altium actions change layers"), S5-27-layer-stack-asked-unknown.jpg ("the stack is unknown; '4 layers' is the project setting").
- **What is true:**
  - `place_on()` calls `ensure_stack(prj, pcb, 4)` (`scripts/altium/bridge.py:1837-1839`).
  - The Layout header reads `copper_layer_count` from the PcbDoc (`ui/js/views/previews.js:761`, `scripts/preview_pcb.py:392-396`).
  - `STACKINFO` exists read-only (`bridge.py:290`).
- **Why it matters:** following the hand advice (negative Plane layers) would have conflicted with the router.
- [LIMIT, false claim: the stated limit does not exist.]

**W27. The stack is not JLC04161H; Altium defaults stay in the file.**
- **Seen by:** S5 Alti (WRONG), S6 Lect (WRONG, per ruling), S7 Alti (FRICTION: nothing in the exports carries the stack), S8 producer (FRICTION: the instruction is only in notes.md).
- **Evidence:** `alti/S5-stack.png`. Board6 has 4 x 1.4 mil Cu and 3 x 12.6 mil FR-4 (Er 4.8), 1.10 mm in total. JLC04161H-7628 is about 1.6 mm. S8-06-jlc-stackup-options-JLC04161H-7628.jpg and S8-07-jlc-default-stack-table.jpg show JLC's default is "No requirement".
- **Cause:** in `scripts/altium/bridge/AdvisorBridge.pas` `PcbStack`, the four `StackLayerProps(...)` calls are commented out (~2721-2724). `ensure_stack` (`bridge.py:1434`) checks only the copper count, so the defect is never detected.
- **Ruling (DECISIONS 06:57):** Alti read the file and is right; the engineer read the code path.

**Routing and DRC**

**W28. Entering a current makes power tracks narrower than the signals.**
- **Seen by:** S6 Eng, Alti, Lect (WRONG). Confusions C112, C113, C123.
- **Evidence:** S6-09-rules-applied-6-added-7-updated.jpg, `alti/S6-routing.png`; altium-log 06:36:11 `drawn_widths`.
  - Before: +3V3/+5V/VBUS planned at 0.254 mm.
  - After the student entered 0.3 / 0.5 / 0.5 A, all three were drawn at 0.127 mm, while every signal is 0.2032 mm.
  - At the end, +5V and VBUS are 0.4 mm (the student's Extra rule plus 1 A); +3V3 is still 0.127 mm (route #3, Alti r2).
- **Cause:** `scripts/altium/netcurrent.py:99` `w = max(need, wmin)` rounds up to the board minimum; the rail default (`POWER_WIDTH = 0.3`, `route.py:41`) is lost once a current is set.

**W29. Untented vias next to pads on a HASL board, with the mask slivers blamed on the footprints. The problem ships in the Gerbers.**
- **Seen by:** S6 Eng, Alti, Lect (WRONG); S7 Alti (WRONG: the S6 issues are in the Gerbers); S8 producer (offline Gerber check); Des S6 (FRICTION).
- **Evidence:** S6-27-routed-banner-421-drc.jpg, S6-32-answer-table-fixes.jpg ("It is the fine pitch of the footprint (comes with the part), not the routing"). SolderMaskExpansion `EXPANSION=2mil, ISTENTINGTOP=FALSE`. Counts, kept by source and route:
  - **Engineer (route 2, board-log 06:38:18):** 137 of 252 slivers are pad-to-via.
  - **Alti, Altium DRC:**
    - route 2: 83 dams under 0.10 mm (71 pad-via + 12 via-via), and 9 bare vias within 0.2 mm of a different-net pad;
    - route 3: 86 dams (71 + 15), and 10 bare vias.
  - **Alti S7:** GTS/GBS open every one of the 157 vias.
  - **Producer's approximate script:** 112 via-pad pairs closer than 0.1 mm, 16 overlapping a pad opening.
- **Cause:** the JLC preset leaves tenting off; there is no via-to-pad rule; the explanation text is fixed rather than derived from `parse_drc`.
- [LIMIT, stated]: tenting is "Find Similar Objects in Altium", and the Extra rules form has no tenting kind (C124, C126).

**W30. The silk fix the agent gave cannot work.**
- **Seen by:** S6 Eng (WRONG), Lect (WRONG in r1, downgraded to FRICTION in r2 after the app corrected itself when asked). No ruling recorded. Confusion C130.
- **Evidence:** S6-34-fix-the-board-checklist.jpg, S6-36-agent-cannot-fix-only-walk-through.jpg ("disable the extra 10mil SilkToSolderMaskClearance rule ... To clear 157"). The DRC shows the 10 mil rule at 0 and the 6 mil JLC rule at 157. The 07:17 answer corrected it (S6-58-r3-agent-silk-rule-and-slivers-answer.jpg).
- **Cause:** advice not checked against the per-rule counts the system holds.

**W31. The router ignores crystal layout rules.**
- **Seen by:** S6 Alti, Lect (WRONG), Eng (FRICTION).
- **Evidence:** `alti/S6-crystal.png`.
  - **Route 2:** an IMU_CS via in the centre of Y1; IMU_CS, SDIO_CMD and BOOT1 under Y1; SWD under Y2; HSE_IN 23.6 mm with 2 vias, HSE_OUT 10.9 mm with 2 vias.
  - **Route 3 (P5a NOT met):** the via is gone, but SDIO_CMD, IMU_CS, BOOT1 and SDIO_D0 run under Y1 and SWDIO/SWCLK/SWO under Y2. HSE_IN is 13.1 mm with 3 vias.
- **Cause:** no crystal handling in `scripts/altium/route.py` or `negotiate.py`.
- [LIMIT, stated when asked]: no crystal keep-out or via ban on the Rules page.

**W32. The hole-clearance rule is silently skipped, the page turns clear, the agent offers a false reassurance, and the inner pours end 0.16 mm from the M3 holes.**
- **Seen by:**
  - S6 r2 Lect (WRONG), Des (WRONG, UI).
  - S6 Alti (WRONG: pours 0.161 mm from the NPTH walls, JLC asks at least 0.2 mm; P5b NOT met).
  - S7 Alti (pours in G1/G2).
  - S7 Eng (COSMETIC on the "20 mil PlaneClearance" answer).
  - S8 producer: "Missed".
- **Severity dissent:** Lect WRONG vs Eng COSMETIC on the reassurance. No ruling recorded.
- **Confusions:** C125, C126.
- **Evidence:** S6-43-r2-apply-1-added-2-skipped.jpg ("1 added, 0 updated, 2 skipped (PlaneClearance, M3_Holes_Plane_Gap)" with no reason, and the Rules badge cleared), S6-44-r2-agent-skipped-rule-tenting-answer.jpg ("your board already has a 20 mil PlaneClearance rule"; that rule does not govern polygon pours on Mid signal layers), `alti/S7-gerber-inner.png`.
- **Cause:** the rule importer has no PlaneClearance or polygon-clearance writer; the skip is a toast count; the Extra rules form offers kinds the importer cannot write.
- [LIMIT, silent]

**Outputs and DFM**

**W33. Outputs pass with 424 DRC lines open, and the Outputs page, the manifest warning and the chat never say so.**
- **Seen by:** S7 Eng (WRONG), Lect (FRICTION), Des (WRONG UI: no readiness summary, U7); S6 Eng and Lect (FRICTION: the gate looks at unrouted nets only). Confusions C131, C132, C137.
- **Evidence:** S7-02-outputs-page-warning-U1-unchecked.jpg, S7-03-outputs-generated-21-files-2-warnings.jpg. The manifest `warning` names only U1.
- **Cause:** `stages.outputs_stage` blocks on `store.manufacturing_block`, which is `manufacturing_warning` + `route_block`, and `route_block` checks only unrouted nets (`scripts/store.py:4024-4087`).
- Reviewers agree that allowing the outputs is defensible (0 shorts, 0 clearance). Saying nothing is not.

**W34. The CPL centroid rule is unstated and wrong for asymmetric parts.**
- **Seen by:** S7 Alti (WRONG), Lect (FRICTION), Eng (FRICTION); S8 producer (rotation and origin unverified).
- **Evidence:** `scripts/skills/export_cpl.py` writes "Mid = the centre of the part's pads".
  - U5 (SOT-223): the CPL gives 43.345 against 44.000 from the origin, the 3D body centre and Altium's Pick Place (0.655 mm).
  - J1: 30.84 against an origin of 30.99.
  - J2: 75.56 against an origin of 75.315; Altium's file says 75.46.
  - Altium's own Pick Place output is a second CPL, and `outputs-check.json` counts that one as "the CPL".
- **Sources conflict (unresolved):**
  - **Engineer S7:** the J1/J2 CPL is about 1.3-2.1 mm from the body centre, by arithmetic on the agent's unverified S3 origin figures.
  - **Alti S7:** the CPL is within 0.15-0.25 mm of the footprint origin, which it takes as the JLC reference.
  - **Lecturer S7:** the origin error is "most likely carried".
  - JLC's assembly preview, which would settle it, was not reached (S8).
- **Cause:** the pad-centroid rule in `export_cpl.py` (its docstring says it was tuned on one board, 148/149 parts); no flag for parts whose origin and body centre differ.

**W35. The order note contradicts the Gerbers on via tenting.**
- **Seen by:** S7 Eng, Lect (WRONG), S8 producer (WRONG). Confusion C136.
- **Evidence:** `notes.md:43` "Tent vias (all vias 0.3048 mm hole ...)" sits next to "Vias are NOT tented in the board file". GTS/GBS have 157 openings of 0.028 in (S7-08-agent-added-all-to-notes.jpg). The producer still saw the line at S8, so lecturer S7 condition Q2 is not shown done.
- **Cause:** the order-note text is a plan, not derived from the files. Tenting is neither an importer rule nor an output option.

**W36. The notes agent dropped the student's recorded decisions on the first pass.**
- **Seen by:** S7 Lect (WRONG). Confusion C135.
- **Evidence:** S7-07-agent-says-no-readme-added-notes.jpg, S7-08-agent-added-all-to-notes.jpg. The first notes.md lacked VCAP1, +3V3 0.127 mm, signals under Y1/Y2, pours near M3, untented vias, J3 edge, tunable caps and RTC calibration, and its stack note did not say "Altium default". After the second pass the SD-slot and VDDA decap risks are still missing (Lect).
- **Dissent:** Eng S7 says "those were never said to the app, so this is not an app error" (FRICTION). The lecturer says they were in the S4/S6 chat and conditions. No ruling recorded.
- **Cause (Lect):** the README is built from the agent's memory of the chat, not from a structured list of conditions and risks.

**W37. Pre-order checks are blind to mask webs and copper-to-NPTH distance.**
- **Seen by:** S8 producer (WRONG).
- **Evidence:** nothing in `gerber_check.py`, `outputs_check.py` or `order_check.py` reads mask flashes. The producer's about-80-line script found the via-to-pad webs from the Gerbers alone. Related: the DRC summary shows "Board Clearance Constraint (Gap=0mil)" while the rule is 12 mil (S6 Eng COSMETIC), so the J3 edge distance is not read against JLC.

**Count:** W1-W37 = 37 distinct technical WRONG problems. W13 bundles 3 related part-selection checks.

### WRONG: UI state (designer, kept at the designer's severity; 8 items)

These are screen states that tell the student something untrue. Several overlap with the technical entries above, which are referenced in brackets.

- **U1. "Pins: nothing to verify" shown green.** S3-10-j1-pins-tab.jpg (designer-S3:19, "WRONG-looking"). Technical side: W14.
- **U2. Placement banner says "checked against the netlist" over failing warnings.** S5-12-placed-55-parts-8-warnings.jpg, S5-20-replaced-j1-left-j2-right-4-warnings.jpg (designer-S5:27). Also lecturer S5 WRONG ("false 'checked' banner"). "Checked" means netlist equality, not placement quality. File: `ui/js/views/previews.js` (PV_STEPS result text, :330-340).
- **U3. Check board shows 421 violations under a green tick.** S6-29-check-board-drc-421.jpg (designer-S6:16; Eng and Lect FRICTION). Cause: `ui/js/views/previews.js:587` sets the tone from warnings, not from the violation count (`drcSummary` at :357 would say 'bad').
- **U4. A rejected route is a dead end.** S6-17-route-rejected-4-short-circuits.jpg, S6-18-route-rejected-details.jpg (designer-S6:18). It shows raw Altium text and "437", with no cause in plain words, no action, and "board put back" hidden under details. File: `previews.js:588`.
- **U5. No way to accept or waive a finding the fab allows.** C121, S6-33-route-warnings-text.jpg (designer-S6:28). The red 421 never clears. Reuse the DFM "Accepted risks" component.
- **U6. A skipped rule is reported as success.** S6-43 (designer-S6:66). Technical side: W32. Files: `ui/js/views/rules.js`, `previews.js:587`.
- **U7. No readiness summary; the Outputs nav dot is green with risks open.** S7-02/S7-03 (designer-S7:14). Technical side: W33. Files: `ui/js/shell.js:101-104`, `ui/js/views/outputs.js` (:253, :314-317), `scripts/stages.py`.
- **U8. Outputs shows the Layout chips** ("What is wrong in the layout (424 open)"), plus an old Antigravity answer under a "Claude Code" footer (designer-S7:26). Files: `ui/js/chat.js:588`, `:608-617`.

### FRICTION (grouped by theme)

**Tool limits: what the app cannot do, and whether it says so**

| Limit | Says so? | Evidence |
|---|---|---|
| URL fetch of AN2606 fails; the spinner vanishes after about 70 s; the error text exists only in the DOM | **silent** | C21, S1-12-sources-fetch-failed.jpg (`pages.js:544`) |
| The rule importer cannot write PlaneClearance; the Extra rules form still offers that kind (and Differential pair) | **silent** | W32, C125, C126, S6-43 |
| JLC's DFM verdict needs sign-in; `dfm.py` only ingests a JLCDFM report PDF; the DFM page does not say so | **silent** | producer S8, S8-09-jlc-gerber-viewer-requires-signin-STOP.jpg |
| "Cannot change layers": claimed, but false | **false claim** | W26 |
| The pin checker cannot parse the STM32 pin table; U1 is left to a one-click Confirm | partly (verify text wrong) | Eng S7, S7-02 |
| Cannot fix footprints: EP paste window, thermal vias, courtyard, origin, 3D offset; a rebuild overwrites hand fixes (rebuild claim unverified by Lect) | stated when asked | S3-45-u1-ep-answer.jpg, S3-53-origin-3d-answer.jpg, C57, C62, C66 |
| No near-a-pin placement; cannot move single parts | stated when asked | C103, C107, S5-22 |
| Cannot tent vias, edit pads or mask expansion, move silk, or delete rules | stated when asked | S6-36-agent-cannot-fix-only-walk-through.jpg, C122, C126 |
| No 90 ohm / differential-pair routing | stated when asked | S6-11-answer-no-90ohm.jpg, C113 |
| The drawer cannot draw ports or cross-sheet nets; "needs about 3 sheets" | stated at refusal | S4-46-draw-error-details-3-sheets.jpg, C88 |
| No Altium compile/ERC step; connectivity proof needs Altium by hand | stated when asked | S4-53, S4-60-r2-q1-app-answer.jpg, C93 (Alti S4 FRICTION) |
| No README / order-note output | stated when asked | S7-07, C133, C134 |
| Keep-outs are not kept in the PcbLib | stated (S3-06 banner) | Lect S3 FRICTION |
| No incremental schematic update; one resistor means "replace Main? wipes the drawing" | stated | C98, S4-76-replace-main-question.jpg |
| PCBA preview needs a JLC cart entry (JLC side) | n/a | S8-08-jlc-pcba-toggle-next-stops-here.jpg |

**A. Long waits with no sign of life** (designer theme A, top fix 1)
- Agent answers take 30 s to 6.5 min, showing only "Thinking / Working ... N s".
- Antigravity shows no step list at all, where Claude Code shows "Steps (n)" (Des S3 r2, S4).
- Routes take 5-7 min with only a timer, and the text claims "a couple of minutes" (`previews.js:333`) (C114, C118, C127, C129; S6-13..S6-16).
- The first BOM proposal took about 4 min with an empty page.
- Library build: no per-part progress (C49). The running state is client-side only (`libBusy`, `ui/js/views/bom.js:151`), so it is lost on reload while Altium is still busy (C78, C79, C85).
- **Unverified:** the 45 s "New project" freeze happened under RAM pressure and was not reproduced (C5, RUN-STATE S0 note).
- **Lect S1:** about 316k input tokens and about $0.49 per turn, even for a 10 s "rewrite the description" ($1.86 for stage 1). Cause: the full project and skill context is reloaded every turn.

**B. The page, the chat and the numbers disagree** (theme B, top fix 4)
- Header totals change in the background (C32).
- "28 lines / 51 parts" (C36).
- The BOM says "Accepted risk" where DFM says "Checked by you" (C84; the manifest also lists U2/U4/U5 as `accepted_risks`, Eng S7).
- Layout starts at 2 layers and 152.4 x 101.6 mm, and "Set board" gives no message (C99).
- Rules: "Width wanted" differs from "Drawn" until the next route; +3V3 stays "board rule 0.4 mm" after leaving the scope (C128).
- Sheet text frames say "pins not checked: U2 / U4, J2 / D3, D4" after the student confirmed them (Alti S4 FRICTION; `draw.py:1061-1081` reads `pins_source: agent`). After the 3-sheet rewrite the chat repeats "a guess" (C89).
- "38 nets drawn" vs "55 nets" checked (17 NC singles) (Eng S4).
- Two different MCU current figures from two tables without a note: 35.5 vs 32.3 mA (Eng and Lect S2).
- The chat engine label differs from the footer (Des S6).
- Unexplained sidebar badges: Rules "6" then "8" with no board (C39, C45).

**C. Fixes leave the app as Altium hand steps, with no tracked state** (theme D, top fix 3)
- Every DRC fix (C120, C122), the 3D offsets (C57), the D1 SchLib edit (C91), Validate PCB Project (C93), "do not accept removal in Update PCB" (C23, C106), moving C10/Y1/C13 (C106) and tenting (C126).
- Two DRC groups (Board clearance 7, Silk to silk 1) were reported as "unknown, inspect in Altium" although board-log had the details: J3 pads at 0.300 mm against 0.3048, and H3/H4 designators over the edge (Eng S6).
- The advice to add EP thermal vias by hand collides with the system's own "via-in-pad is never allowed" (`scripts/altium/route.py:1866`, `jlc_preset.py:225`) (Eng S3 r2).
- There is no "Confirm polarity" or per-row confirm for D1/D2, and the D1/D2 rows and "Check datasheets" are dead controls (C58, C65, C81, C82; Des: "BLOCKER-class for the flow, small").

**D. Agent answers contradict or overreach** (theme F, top fix 8)
- SDIO D0 changed between answers without a note (C24).
- The review missed VDDA 10 nF and then reversed itself (C73).
- The DRC explanation was reversed (C130).
- "Fine as-is" for BME280 pads 54% longer than Bosch's land pattern, and "0.80 mm tab fits" a 0.60 mm drawing, both without a source (Lect, Eng S3 r2; C63, C64). Eng S3 r2: the slot comparison used only half the drawing.
- The stray-capacitance rule was cited to the wrong datasheet section (Eng S2 r2).
- "Checked: D1, D2, F1 and J3" contradicts the system's own verify data (Eng S2 r2; C44).
- Extended-part fees grew from $33.77 to $49.12 without mention (Eng S2 r2).
- The price basis is labelled "at 5 boards" but uses the 10-piece break (Eng S2).
- The ESD and regulator requirements written by the system cover neither VBUS nor heat (Eng S1).
- The bootloader-scanned pins are reused without a warning (Eng S1 r2).

**E. Chat format and consent** (theme E, top fix 6)
- 40-line answers and wide tables in a 300 px column (C22, C34).
- 13 "Idea proposal" chips (C9).
- Internal names leak: "bom.propose applied with warnings", "student_said must be a verbatim quote", "chat.ask", raw proposal IDs, "rules.py", "checks/board.py" (C31, C105, C108; Lect S2; Des S6).
- The consent guard refused "yes, replace the placement ..." and accepted only a bare "yes". The agent had already announced the replacement before it was refused (C105, Eng and Lect S5).
- Chips go stale or follow the wrong page (Des S1, S5, S7).
- "Next:" lines are free text that disagrees with the buttons (C28, Des S2).

**F. Previews cannot be judged** (theme G, top fix 7)
- Schematic: unreadable, nets as stubs, no zoom (C70; Alti S4 COSMETIC: label-stub style, power nets drawn both as labels and ports).
- U1 symbol: unreadable (C60).
- No paste or mask layers (C61).
- Part labels sit away from their footprints (C102).
- Symbol vs pad counts unexplained: J1 16 vs 18, J2 13 vs 15, both from 2 NPTH pegs (C52).
- Numeric pin names on D1, J3, SW1, Y2, D2 and F1 also blind the power-name check (Eng S3).
- The datasheet viewer has no zoom and the list shifts under the click (C59).
- Confirm-pins opens blank p.190 and the UFBGA100 page (C80).

**G. Start-up and navigation** (theme H, top fix 10)
- Opens on an old project (C1); "New project" is at the bottom of about 30 projects (C4).
- Defaults to 2 layers with no prompt (C6).
- The Altium link is unexplained until a build fails (C2, C29); Build library is the primary button with no Altium project (Des S2).
- Blank Schematic page with "press Draw" chips that cannot work yet (C68).
- Idea-stage Altium instructions (C23).

**H. Rules, route and DRC presentation** (theme I)
- The Rules first view is alarming and unexplained: "2 below JLC minimum" are Altium defaults (C110).
- The route rejection gives raw text (C115).
- An infeasible width rule fails the whole route after about 5 min ("pad U1-9 too close ... for a 0.299999 mm track"), with no pre-route feasibility check or neck-down, and the banner does not say the old routing is kept (C127; Lect S6 r2).
- "The board already has 63 parts or copper objects", with "Keep it" as the dark default (C117).
- "0 clearance before routing" next to "Board Clearance 5 -> 7" (C118).
- 421 shown as one sentence plus 16 paragraphs, pasted into the chat too, with no "JLC will make this / must fix" grouping, although `parse_drc` has every line. Alti classified route 2 as 83 real, 5 borderline, 173 rule or footprint noise and 160 cosmetic.
- No USB pair: D- hops to Mid-2 with 2 vias, and they run within 0.6 mm of each other for only 9.8 mm (Alti and Lect S6; low risk at Full-Speed).
- The Mid-2 +3V3 pour carries 36 signal segments (Alti S6).
- J3, a vertical header, was treated as an edge connector, with pads 0.30 mm from the edge. It is borderline against JLC's "> 0.3 mm" assembly limit, and neither the placer nor `checks/board.py` reports it (Alti S5/S6).
- High via counts on 2-pin nets (Alti S6).

**I. Outputs and ordering** (theme J, top fix 9)
- No README or order-note export, so the firmware bring-up, stack and tenting notes live only in `notes.md` ("Nothing derives from this file") (C133, C134; Eng, Lect S7).
- Deliverables are below the fold, with no full path (Des S7).
- Two export paths and two CPLs (Des and Eng S7).
- "Confirm" on the U1 banner is ambiguous (Des S7).
- The same warning is shown twice (Des S7).
- The stack-up instruction is not in the manifest (producer).
- The DFM page should say JLC's verdict needs sign-in (producer).
- C10/C11 are the same C19666 on two BOM lines (Alti S7, producer).

**J. Data and library plumbing**
- Building one part rebuilds and re-flags all 31 lines (C77; Eng S4).
- A failed restore after a failed build (WinError 1224) never reached the page (Eng S4).
- `lcsc` is empty while `code` holds the code on 8 lines. All 8 codes reached the BOM export (K4 met, Lect and Eng S7).
- NC is a magic net name, not a pin attribute (Lect S4). It compiled correctly as 17 singles.
- Decoupling is not bound to pins in the netlist format (Lect S4).
- The netlist writer does not know the drawer's sheet capacity, and the board-area warning came only at S4 (C74, C88).
- Firmware requirements live only in free text (Lect S4).
- The citation checker marks the course manuals "not in Sources" (`scripts/background.py:154-157`) (C67, C89; Eng S4/S5).
- AN2606 is a third-party Chinese mirror cited with untranslated quotes (C94; Lect S4, Eng S5 COSMETIC).
- The green LED was knowingly left dim (Eng S2; C40).
- The TVS clamp was not checked against the LDO input (Eng S2, later moot with LDL1117).
- The verify message on U2 claims exposed pads it does not have (Eng S4).

### COSMETIC (grouped)
- **Idea:** diagram blocks are stale or generic ("STM32 (MCU)", ESD in the power domain, 3V3 drawn only to the MCU); "Draft - 42 changes" counts; tiny diagram labels (Eng and Lect S1, Des S1).
- **BOM:** "All 14 lines Basic" while R3 is Preferred; ME6211 dropout 120 vs 100 mV; `availability: "low"` on lines with high stock; the Ref column is cut off; the orphan source 7V25080026.pdf (Eng S2, Des S2).
- **Library:**
  - The pin-1 marker sits on the USB-C shield tab (`model_preview.py:271`).
  - Footprint name "LED0805-R-RD" on a green LED.
  - "EasyEDA" vs "KiCad" source naming.
  - Generic "radio module antenna" banner text.
  - SW1/SW2 3D height 1.55 mm for a 2.0 mm part.
  - 0402/0603/0805 footprints have no silk.
  - Y2 typed `res` in the netlist.
  - The converter silently turns plated J1 pegs into NPTH (correct, but unlogged).
  - Sources: Eng S3, Alti S3, Lect S4.
- **Schematic:** C13 22 uF "exceeds" 4.7 uF (it is not a maximum); "8 parts" listed as 9 refs; J3 pin 9 GNDDetect open (Eng S4).
- **Layout and routing:**
  - The outline is 59.995 x 45.009 mm (rounding).
  - "Your board matches the preset" while the preset itself creates the silk and part of the sliver findings.
  - 4 acid traps and 9 duplicate GND segments.
  - The U1 EP has no via field.
  - Sources: Eng S5/S6, Alti S6.
- **Outputs:** "Altium wrote no BOM" next to a "BOM 1 file" folder; empty `reason` on accepted risks; "No record" label; Gerber inch 2:4 rather than metric (Lect, Eng, Alti S7).

## Student confusions (all of them)

Source: `roles/student-confusions.md`. Grouping and theme letters follow `roles/designer-SUMMARY.md`; the designer answered every entry in `designer-S1.md` ... `designer-S7.md`. Format: id | stage | what confused the student | screenshot.

### B. Page, chat and numbers disagree (19)
- C2 | S0 | Black "not linked to an Altium project" banner; unclear whether a new project needs a manual link | S0-02-engine.jpg
- C3 | S0 | Engine switch changed the model silently; chat footer kept showing the old engine | S0-02-engine.jpg
- C12 | S1 | Layer count shown as 2 (selector), "2-layer" (diagram) and 4 (requirement) until Save | S1-04-third-answer.jpg, S1-06-saved-v3.jpg
- C13 | S1 | Description still said I2C sensors, one LED, DFU after the requirements changed | S1-04-third-answer.jpg, S1-05-description-fixed.jpg
- C14 | S1 | Confirm active with an unsaved "42 changes" draft; unclear whether Confirm saves | S1-06-saved-v3.jpg
- C16 | S1 | Summary added "USB DFU backup" that the student never asked for | S1-06-saved-v3.jpg
- C27 | S1r2 | After Save v4 the page still said "confirmed", with no button to re-confirm the changes | S1-17-saved-v4-still-confirmed.jpg
- C28 | S1r2 | Agent gave two rules ("Save then Confirm" / "Save confirms"); MCU block still generic | S1-16-assumed-removed-chat.jpg, S1-17-saved-v4-still-confirmed.jpg
- C29 | S2 | New project shows "not linked to Altium"; nothing said one must be created | S2-02-settings-engine-claude.jpg
- C32 | S2 | Header price and checked counts changed by themselves while reading | S2-08-bom-approved-28-lines.jpg
- C48 | S2r2 | Settings showed an Altium project created after Stop, from a review question | S2-57-settings-altium-project-created.jpg
- C77 | S4 | Building one new cap reset all 31 lines to "to verify" | S4-21-build-library-started.jpg
- C84 | S4 | BOM says "Accepted risk" for parts DFM calls "Checked by you"; build still running ~15 min | S4-38-bom-accepted-risk-still-building.jpg
- C96 | S4 | Board size "Set" gave only a toast; Idea text still said 45 x 35 | S4-69, S4-71, S4-72
- C99 | S5 | Layout opened at 2 layers and 152 x 101 mm; "Set board" silent for ~30 s | S5-03..S5-05
- C109 | S5 | Agent said the real stack is unknown and "4 layers" is only a setting | S5-27
- C112 | S6 | After "Apply rules" the power widths dropped from 0.254 to 0.127 mm unexplained | S6-08, S6-09
- C125 | S6r2 | Plane-clearance rule "skipped" with no reason while the Rules badge turned clear | S6-43
- C128 | S6r2 | +3V3 still shown as "board rule 0.4 mm" after it was removed from the rule scope | S6-49..S6-51

### A. Silent or long waits, no progress or no end message (15)
- C5 | S0 | Page froze ~45 s after "New project", no spinner (unverified: RAM pressure) | S0-03a-new-project-dialog.jpg
- C7 | S1 | Only "Thinking / Steps (6/7)" for 45-75 s answers; no step names or estimate | S1-01-thinking.jpg
- C10 | S1 | Browser tab died during a wait; after reload unclear if the message was sent (nothing lost) | S1-03-second-answer.jpg
- C22 | S1r2 | 4-minute answer, then a wall of text with a 14-row table in the narrow chat | S1-13-decisions-answer-draft.jpg, S1-14-current-budget-fit.jpg, S1-15-pin-table.jpg
- C37 | S2 | "Check stock" gave no feedback for 30 s; passives stayed unchecked with no reason | S2-21-check-stock-no-feedback-30s.jpg
- C41 | S2r2 | Stop halted one step, but the agent went on to create the Altium project | S2-31-r2-msg1-typed.jpg
- C42 | S2r2 | 6-minute "Searching JLC" wait; key crystal facts hidden in cut-off card columns | S2-35-r2-5-cards-crystals-ldo.jpg
- C63 | S3r2 | 4-minute "Working... N s" wait; BME280 pads 54% longer called "fine" without a reason | S3-46, S3-47
- C69 | S4 | 5.5-minute wait; two near-identical warnings listing different unverified parts | S4-07
- C71 | S4 | "Review this sheet" took ~5 min with idle chips; it missed VDDA 10 nF | S4-13-review-sheet-answer.jpg
- C78 | S4 | Library build ran 6+ min with no progress; after reload no result message | S4-22-build-library-after-reload.jpg
- C79 | S4 | After reload the build state was gone, but a second click said Altium was still busy | S4-23-altium-still-working.jpg
- C85 | S4 | First build ended after 15-19 min with no message and no status change | S4-39-build-library-second-run.jpg
- C86 | S4 | Build hung 20+ min; error told the student to restart Altium and edit the project | S4-40-build-library-error-intlib-not-written.jpg
- C114 | S6 | Route ran 5-7 min with only a timer, no net count or percentage | S6-13..S6-16

### D. Tool cannot do it; fix is manual in Altium; no tracked state or accept (14)
- C57 | S3 | Only fix offered for 3D offsets: edit the PcbLib in Altium by hand | S3-32
- C66 | S3r2 | J1/J2 origin off the body (CPL impact) was hidden behind a 3D warning; fix only in Altium | S3-53
- C81 | S4 | D1/D2 had no per-part confirm dialog; only "Confirm all (3)" that also confirms unreadable J3 | S4-35-u5-confirmed-d1-d2-j3-left.jpg
- C82 | S4 | Clicking the D1/D2 rows and "Check datasheets" did nothing | S4-36-agent-d1-d2-polarity-match.jpg
- C100 | S5 | App said it cannot set the 4-layer stack; told to use Layer Stack Manager by hand | S5-06..S5-09
- C104 | S5 | Agent reversed itself: Build library does not create keep-outs; "draw them yourself" | S5-16
- C113 | S6 | No 90 ohm USB pair; power at 0.127 mm; +3V3 relies on a plane not yet poured | S6-11
- C116 | S6 | Tool's own keep-outs were top copper; the fix removed the keep-out requirement | S6-20
- C119 | S6 | Tracks under D1/D2 silk; the fix options have no button | S6-27
- C120 | S6 | "What is wrong in the layout" answer: every fix is manual in Altium | S6-31, S6-32
- C121 | S6 | JLC-acceptable items still count as violations; no way to waive and clear 421 | S6-33
- C122 | S6 | "Fix the board" gives an Altium checklist; the agent says it cannot do the fixes | S6-34..S6-36
- C124 | S6r2 | Extra rules form has no via-tenting kind | S6-38..S6-42
- C126 | S6r2 | The form accepted a rule kind the importer cannot write; tenting is manual only | S6-44

### F. Agent answers contradict earlier ones or drop decisions (13)
- C24 | S1r2 | SDIO D0 moved from PB4 to PB7 between answers without saying so | S1-15-pin-table.jpg, S1-09-research-answer-end.jpg
- C30 | S2 | Every BOM line Qty 1, "28 parts" instead of ~70; tiny "Check qty" tag | S2-08-bom-approved-28-lines.jpg
- C33 | S2 | Agent said "51 parts"; page showed 28 and "5 changes waiting"; old warnings repeated | S2-13-agent-answer-warnings-again.jpg
- C35 | S2 | After approving everything, reload still showed 28 parts, Qty 1 and "Check qty" tags | S2-15-qty-still-1-after-reload.jpg
- C36 | S2 | Quantity fix took two rounds (~8 min); "28 lines / 51 parts" and cut-off ref ranges | S2-19-after-approve-11.jpg
- C47 | S2r2 | R4 ended up on two lines after an approved card; parts count wrong for ~10 min | S2-55-stock-check-r4-duplicate.jpg
- C56 | S3 | Agent says "from EasyEDA", preview says "KiCad"; 3D offset warning only in chat | S3-29, S3-11
- C72 | S4 | Card showed "R5" for the new R14; "waits for approval" though the netlist was written | S4-15-agent-added-r14-c23-bom-proposal.jpg
- C73 | S4 | Review missed VDDA 10 nF until the student asked | S4-15-agent-added-r14-c23-bom-proposal.jpg
- C89 | S4 | After the 3-sheet split, earlier pin confirmations were reported as "a guess" again | S4-48-three-sheets-written.jpg
- C130 | S6r2 | DRC explanation contradicted the earlier advice; found only by asking | S6-57, S6-58
- C135 | S7 | First notes.md left out most recorded risks; a second request was needed | S7-08
- C136 | S7 | Order note "Tent vias" next to "Vias are NOT tented in the board file" | -

### G. Previews cannot be inspected or judged (13)
- C51 | S3 | J1 preview: pin-1 marker on a shield tab; two pad-naming schemes in one drawing | S3-08, S3-09
- C52 | S3 | J2 symbol 13 pins vs 15 pads; J3 symbol has numbers only | S3-15, S3-18
- C53 | S3 | Y1 courtyard smaller than its pads; plain "Built" and green pins on a scan | S3-19, S3-21
- C54 | S3 | D3 green "Checked" with no datasheet; footprint named "-R-" for a green LED | S3-23..S3-25
- C55 | S3 | Courtyards smaller than the pad span on Y1, D3 and D4 | S3-19, S3-23, S3-26
- C55b | S3 | SW1/SW2 same courtyard pattern: 4 of 4 small parts | S3-27
- C59 | S3 | Datasheet viewer too small with no zoom; the list shifted under the click | S3-34, S3-35
- C60 | S3r2 | U1 green "nothing to verify"; 49-pin symbol unreadable, no zoom | S3-37..S3-39
- C61 | S3r2 | Previews show no paste/mask layers; pin 1 vs the datasheet cannot be checked | S3-40..S3-42
- C65 | S3r2 | Confirmed the LED cathode by eye on a tiny drawing; no "Confirm polarity" button | S3-50, S3-51
- C70 | S4 | Schematic preview unreadable; had to read the page text to check the nets | S4-07, S4-08
- C80 | S4 | Confirm-pins dialog opened blank p.190 and a UFBGA page; 49-row list scrolls separately | S4-27-confirm-pins-u1-p42-table8.jpg
- C102 | S5 | Connectors on the long edges, labels away from their parts, left half crowded | S5-14

### E. Chat format: long answers, tables, internal leaks, consent mismatch (10)
- C9 | S1 | Long first answer plus 13 green "Idea proposal" chips; chat opened scrolled to the end | S1-02-first-answer.jpg
- C18 | S1r2 | 190 s "Working with the documents" on a plain question; unclear if the confirmed idea changes | S1-08-research-wait.jpg
- C19 | S1r2 | Red box blamed the agent for "system files" that were the student's notes; notes deleted | S1-09-research-answer-end.jpg
- C20 | S1r2 | AN2606 fetch failed twice; told to put the PDF in a "sources folder" with no guidance | S1-10-research-answer-top.jpg, S1-09-research-answer-end.jpg
- C31 | S2 | Code-like orange warnings ("bom.propose applied with warnings"); unclear if saved | S2-08-bom-approved-28-lines.jpg
- C34 | S2 | 40-line answer; SD card current "unknown", so the budget was not really recomputed | S2-13-agent-answer-warnings-again.jpg
- C67 | S3r2 | Citations to Altium docs flagged "not in Sources" and cannot be opened | S3-53
- C98 | S4 | Adding R15 needed "replace Main? wipes the drawing" and a full redraw | S4-76, S4-78
- C105 | S5 | "yes, replace the placement..." refused; only a short verbatim "yes" worked | S5-17, S5-18
- C108 | S5 | Page shifted under a click; follow-up contradicted the table and showed "chat.ask" text | S5-23, S5-24

### H. Start-up, navigation, first use (7)
- C1 | S0 | App opened on an old "demo" project; no start screen or hint how to begin | S0-01-home.jpg
- C4 | S0 | "New project" hidden at the bottom of a ~30-project switcher list | S0-03-new-project.jpg
- C6 | S0 | New project defaults to 2 copper layers with no hint that it matters | S0-03-new-project.jpg
- C15 | S1 | Holes "assumed" in a requirement, but the hole fields are empty and a separate button adds them | S1-06-saved-v3.jpg
- C17 | S1 | After Confirm, unclear what is locked and whether edits are still allowed | S1-07-confirmed-next-bom.jpg
- C21 | S1r2 | Sources "From URL" spun ~70 s, then vanished; the error was only in hidden page text | S1-11-sources-add-url.jpg, S1-12-sources-fetch-failed.jpg
- C68 | S4 | Blank Schematic page; "press Draw" failed with "write the schematic first" | S4-02, S4-03

### I. Rules, route results and numbers that need explaining (7)
- C39 | S2 | Red "6" badge on Rules appeared before any board existed | S2-30-library-build-failed-no-altium.jpg
- C110 | S6 | Rules "2 below JLC minimum" were Altium defaults; red badge 8 unexplained | S6-03..S6-05
- C111 | S6 | Net currents all default; no field for the USB differential pair | S6-05..S6-07
- C115 | S6 | Route thrown away after ~6 min (4 shorts); raw DRC text, "437", no next step | S6-17, S6-18
- C117 | S6 | Replace banner "63 parts or copper objects"; same warnings after re-placing | S6-22, S6-23
- C123 | S6r2 | 0.5 A gives a width equal to the board minimum; no hint to use trip current | S6-37, S6-40
- C127 | S6r2 | Route with a 0.3 mm power rule failed after minutes at U1-9; old routing state unclear | S6-45..S6-48

### C. Green or "done" over unverified, failed or ungated state (6)
- C50 | S3 | J1 "Built, check" plus green "Pins: nothing to verify" on a scanned datasheet | S3-08, S3-10
- C90 | S4 | Draw warning suggested D1 shorts GND to +5V on the USB input | S4-51-draw-warnings-d1-a3.jpg
- C118 | S6 | "Routed" banner with 421 DRC; footprints blamed; clearance numbers disagree | S6-27, S6-28
- C131 | S7 | Outputs warns only about U1; 424 DRC not mentioned; sticky header covers the list | S7-02
- C132 | S7 | Outputs generated with 424 DRC and U1 unchecked; "no BOM" next to "BOM 1 file" | S7-03
- C137 | S7 | Outputs made with 424 DRC open and U1 unchecked; no "are you sure" | S7-03

### J. Missing output / export features (2)
- C133 | S7 | Export menu has no README, order note or stack-up note | S7-04..S7-06
- C134 | S7 | No README button; the agent wrote the notes into notes.md instead | S7-07

### K. Engineering questions, good answers and positives (32)
Not UI findings in the designer's reading. Several of them are system findings handled above, mainly C38 (W11), C46 (W2), C75 (W20), C88 (tool limit), C101/C103/C107 (W24, U2).
- C8 | S1 | Vague idea became 12 "assumed" requirements (L432, 2 layers); easy to confirm unread | S1-02-first-answer.jpg
- C11 | S1 | Wording implied a separate 48 MHz crystal; JLC stock and price in the idea chat | S1-03-second-answer.jpg
- C23 | S1r2 | Idea page says "answer No in Altium Update PCB" with no context | S1-13-decisions-answer-draft.jpg
- C25 | S1r2 | "Should fit (planned)" instead of a yes/no fit check | S1-14-current-budget-fit.jpg
- C26 | S1r2 | Agent honestly kept the student's "push-pull" typo as assumed; visible only at the answer's end | S1-13-decisions-answer-draft.jpg
- C38 | S2 | Review chip "28 open" made the agent start a library build unasked; it failed | S2-29-whats-wrong-agent-builds-library.jpg
- C40 | S2 | SD current assumed 100 mA uncited; dim LED proposed; notes not on the BOM page | S2-26-14-passive-cards-lcsc.jpg
- C43 | S2r2 | Idea draft shows two different peak-current figures; board size empty | S2-40-idea-page-draft-7-changes.jpg
- C44 | S2r2 | Mixed trust marks; 3 of 8 datasheets possibly wrong or scans; no next step | S2-45-r2-msg3-answer-3-cards.jpg
- C45 | S2r2 | Datasheet check ran against the old MPN before the swap; Rules badge 6 to 8 | S2-51-r2-datasheets-scans.jpg
- C46 | S2r2 | Goal paragraph still named ME6211 after the LDO swap; Tj 86 vs 80 C | S2-52-r2-u5-approved-idea-saved-v7.jpg
- C49 | S3 | Build library ~2 min with a spinner; no per-part progress or model source | S3-03..S3-05
- C58 | S3 | Courtyard = body outline unexplained; student must confirm LED polarity with no button | S3-32
- C62 | S3r2 | EP = GND with a quote, but the app cannot add a paste window or vias | S3-45
- C64 | S3r2 | J1 slot "fits" and hole claims unquoted, read from scans; plated vs unplated unclear | S3-49
- C74 | S4 | Board-area warning (64%, try 60 x 45) first appeared at the schematic stage | S4-16-bom-approved-board-area-warning.jpg
- C75 | S4 | U4 red "Pins conflict" opened Alternatives incl. non-flash parts; no reason shown | S4-18-u4-pins-conflict-click-alternatives.jpg
- C76 | S4 | The conflict was only pin-7 naming; the BOM page did not say so | S4-20-u4-conflict-explained.jpg
- C83 | S4 | Positive: DFM separates "Checked by you" from "Accepted risks", J3 honestly "without a datasheet" | S4-37-dfm-all-confirmed-accepted-risks.jpg
- C87 | S4 | Positive: after fix #1, the C23 build finished in ~90 s, 31 of 31 | S4-43-library-built-31-of-31.jpg
- C88 | S4 | Draw refused: sheet too big and cross-sheet nets not drawable; the preview had one sheet | S4-46-draw-error-details-3-sheets.jpg
- C91 | S4 | D1 not shorted, but the offered fix is a hand SchLib edit plus Altium validate | S4-53-erc-answer-d1-not-shorted.jpg
- C92 | S4 | "Marked NC with no ERC markers" reads as contradictory; no open-pins view in the UI | S4-55-unused-pins-table.jpg
- C93 | S4r2 | Proving cross-sheet connectivity needs Altium steps; the UI shows no compiled net count | S4-60-r2-q1-app-answer.jpg
- C94 | S4r2 | PA10 pull-up answer took 6.5 min; AN2606 cited in Chinese; netlist needs a redraw | S4-62-r2-q2-pa10-pullup-proposal.jpg
- C95 | S4 | Firmware bring-up order given only as a notes.md path in the chat | S4-68
- C97 | S4 | Checks only a generic cap-to-any-pad distance; no cap-to-pin pairing | S4-74
- C101 | S5 | Placement banner "checked against the netlist" with 8 warnings; keep-outs not placed | S5-12, S5-13
- C103 | S5 | Distance table shows most decaps far from their pins despite the "checked" banner | S5-16
- C106 | S5 | Second placement fixed the edges but C13 got worse; "move in Altium", "do not accept removals" | S5-20
- C107 | S5 | Second placement worse for several caps; the placer cannot enforce near-pin | S5-22
- C129 | S6r2 | Positive: +5V/VBUS at 0.4 mm as asked; the banner explained which rule wins | S6-52..S6-56

**Count check:** 19 + 15 + 14 + 13 + 13 + 10 + 7 + 7 + 6 + 2 + 32 = **138 lines**. That is C1-C137 plus C55b, matching the 138 entries in `roles/student-confusions.md`, each listed once (script-checked).

## Verdict per role

### Lecturer: gate history

| Stage | Round 1 | Round 2 | Conditions | Status at the end of the run |
|---|---|---|---|---|
| 1 Idea | **FIX**: RTC with no battery, logging numbers, bus/pin plan, DFU unverified, "(assumed)" items confirmed | **PASS with conditions** | **C1** BOOT1/PB2 pull-down; **C2** SDIO pull-ups + card detect; **C3** "24 h on 16 GB" wording; **C4** current budget + LDO dissipation from datasheets; **C5** "time not set" records | C1, C2 met at BOM/schematic. C3, C4, C5 closed at S2 r2. |
| 2 BOM | **FIX**: LSE crystal gm margin, LDO at 95% of Pd, requirements still say ICM-42688-P, VDDA 1 uF, LED and missing datasheets | **PASS with conditions** | **K1** J1/J2/Y1 by eye vs scans, J3 vs Cortex map, LED polarity; **K2** tunable load caps + RTC calibration + LSE high-drive in README; **K3** C19 at the microSD slot; **K4** 8 LCSC codes in the export; **K5** DFU/PA10 open | K1 done (S3/S4). K2 in notes.md (Lect S7). K3 NOT met (C19 28.4 mm; N1 waived). K4 met (S7). K5 open (needs real hardware). |
| 3 Library | **FIX**: U1 and the LGAs never opened, J1 dimensions, LED polarity unsourced, 3D/origin/courtyard | **PASS with conditions** (withdrew the J1 zero-ring point) | **L1** EP to GND + J3 pin map; **L2** EP via grid and paste decision; **L3** J1/J2 origin before CPL or check in JLC preview; **L4** no hand placement near keep-outs; **L5** U3 pad length and J1 slot width to JLC DFM | L1 met (S4). L2 NOT met (no EP vias, full paste in GTP). L3 open (CPL dispute, JLC preview not reached). L4 held (no hand work). L5 open (no JLC DFM verdict). |
| 4 Schematic | **FIX**: prove cross-sheet connectivity, "NC" net, shared-SPI I2C/I3C risk, decoupling bound to nothing, board size | **PASS with conditions** (withdrew the inter-sheet WRONG after Alti's compile) | **M1** re-compile after the Main redraw; **M2** decoupling by hand at S5; **M3** 60x45, holes with keep-outs, edges, crystals tight; **M4** README firmware notes | M1 met by Alti 05:40 (55 nets, 226 pins), but Altium's ERC violation list was never read. M2 not done (tool limit, N1 waived). M3 partly: outline, holes and edges yes; keep-outs removed; crystals not tight. M4 met in notes.md. |
| 5 Placement | **PASS with conditions** (no FIX: remaining failures are tool limits) | n/a | **N1 (gate)** move C10, C19+C21, Y1, C22+C23 in Altium; **N2** BME280 away from U5/U1; **N3** confirm stack and keep-outs; **N4** USB pair short, no trace under Y1/Y2 | N1 waived by orchestrator ruling 06:15. N2 not followed up in later reviews. N3 answered by ruling 06:57 (Altium defaults, not JLC); keep-outs later removed. N4 not met (Alti S6). |
| 6 Routing | **FIX**: power widths not challenged, requirement deleted to pass, crystals not checked, DRC explanation taken on trust, accept-vs-write-down | **PASS with conditions** | **P1** README risk list + firmware notes; **P2** order must select JLC04161H-7628; **P3** JLC DFM items; **P4** CPL origin + LCSC codes; **P5** Alti recheck of route #3 | P1 met in content (Lect S7). P2 in notes.md only, not in the manifest. P3 not obtained (DFM behind login). P4: codes met, CPL open. P5: (a) crystal area NOT met, (b) pour-to-NPTH NOT met, (c) +5V/VBUS continuity met. |
| 7 Outputs | **PASS with conditions** | not run | **Q1** add the SD-slot and VDDA decap risks; **Q2** one unambiguous tenting line; **Q3** CPL vs JLC preview; **Q4/Q5** DRC triage + JLC DFM items; order page per P2 | Q2 not shown done (the producer still saw "Tent vias" at notes.md:43). Q1: no evidence. Q3-Q5 not possible (JLC preview behind login and cart). The order form was not configured (read-only run). |

**Student behaviour the lecturer valued:**
- measured instead of trusting banners;
- caught the agent's contradictions (C108, C130, C136);
- refused the one-click Confirm on U1;
- did no hand work in Altium;
- used the Extra rules form in S6 r2.

**What the lecturer rated as the tool's own errors** is reflected in the findings above.

### Designer
- **Scores:**
  - S0-1: 6.5 (r1), 6 (r2).
  - S2: 5.5 / 5.5.
  - S3: 6 (r1), 5.5 (r2).
  - S4: 5. S5: 5.5. S6: 5 (unchanged in r2). S7: 5.
  - **Overall 5.4/10** (`designer-SUMMARY.md`, whose table uses the round-2 values: 6 for S0-1 and 5.5 for S3).
- **Summary judgement (paraphrased):** the product is honest in words, but its colours, counts and Next buttons often say otherwise, and long steps give no sign of life.
- **Top 10 fixes (designer):**
  1. Named phases and honest estimates for every wait, surviving reload and always ending with a message.
  2. Tone from findings, not from "the step ran".
  3. A findings panel with Tool can fix / You fix in Altium (steps + "check again") / Accept with reason.
  4. One source of truth across page, chat and numbers.
  5. "Next" and chips follow state, plus a "Before you order" card on Outputs.
  6. Short chat answers with quick-reply buttons and no internal text.
  7. Previews a student can judge.
  8. A decision ledger the agent must carry over.
  9. Findable, complete deliverables, including a README row.
  10. The first minutes: New project visible, no freeze, a clear empty-page first step, the Altium-link banner fixed.
- **Keep:**
  - one-click Altium step buttons with Stop;
  - Replace / Keep consent with a backup;
  - Revoke on checked pins;
  - DFM "Checked by you" vs "Accepted risks";
  - export toast with Download;
  - one-click chat cards;
  - the U5 change card with old values crossed out;
  - honest admission of limits.

### Engineer (system side in the browser)
- **S1:** every request was implemented; no hallucinations, every number traces to a tool result or the datasheet. Description and diagram stale; guard data loss; BOOT1 missing.
- **S2:** part identity clean (MPN = LCSC = package on all lines; stock and price match supply-log). It got wrong what it should compute: quantities, crystal margin, VDDA, LDO dissipation, requirement sync. R2: engineering correct and sourced (gm_crit for 4 crystals, LDL1117 thermal, the 268 mA budget); plumbing wrong (canned approval text, project created after Stop).
- **S3:** library content good: all 30 footprints match their packages; the U1, LSM6DSO, BME280, W25Q128, LDL1117 and USBLC6 pin maps match their datasheets. What the page and agent say about verification is wrong (green Checked, pitch, polarity cite). R2: the app was honest about every fix it could not make.
- **S4:** the netlist is good engineering (every pin is a valid F411 alternate function; the straps are right), and the drawn project = netlist (55 groups, 224 pins). Wrong around it: false U4 conflict, silent failed build, "0 errors" with unstated scope.
- **S5:** outline, holes and edges as asked; the distance table is honest. Three false statements: keep-outs "no copper", stack denial, decap check passes everything but C10.
- **S6:** routing complete, and its main claims are true (39 nets, 0 unrouted/clearance/short, real pours, correct rejection of route 1). Wrong: sliver attribution, silk advice, power widths.
- **S7:** files complete and consistent (14 Gerber/drill files, BOM 55 parts / 31 lines all with LCSC, CPL in the Gerber frame). Wrong: the outputs gate is silent on 424 DRC, and the order note contradicts the Gerbers. Corrected its own S5/S6 stack statement.

### Alti (system output in Altium; computer use unavailable, so checks were done with the system's read-only scripts, raw file reads and Alti's own renders)
- **S3:** symbols and footprints consistent (159 pads cross-checked, 0 differences); U1, U2, U3, U4, U5, D1 and J1 pin maps correct. WRONG: J1/J2 3D bodies, no courtyard, EP full paste.
- **S4:** 3 sheets, 54 parts, 55 nets, matching the system netlist pin for pin. Native `DM_Compile` (read-only DelphiScript): **CONNECTED**, 29 cross-sheet nets each one net, 0 split / 0 merged, NC = 17 single-pin nets. Re-run after the R15 redraw: 226 pins, still identical. WRONG: false D1 short.
- **S5:** 4 copper layers in the right order, 60x45 outline, NPTH M3 holes at 3.5 mm, connectors on opposite short edges, no overlaps. WRONG: stack values are Altium defaults, KO as Top copper, C10/VDDA/microSD decoupling, HSE crystal 7-8 mm.
- **S6:** 39/39 nets, 0 shorts / clearance / unrouted, solid GND pour on Mid-1. DRC 421 classified as 83 real / 5 borderline / 173 noise / 160 cosmetic; **4 real issues** (crystal area, VCAP1 path, untented vias, pours near M3 holes). Route 3: 86 real DRC lines, +5V/VBUS 0.4 mm fixed, +3V3 still 0.127 mm. P5: (a) NOT met, (b) NOT met, (c) met.
- **S7:** Gerbers match route #3 and are not stale (manifest `pcb_sha256` equals the PcbDoc); the layer set and extensions are as JLC expects for Altium; drills match the PcbDoc. WRONG: CPL pad-centre rule (U5 0.655 mm), EP paste in GTP, S6 issues in the fab data.

### Producer (stage 8, JLC, read-only, never signed in)
- **Parse:** JLC parsed the zip: "Detected 4 layer board of 45x60mm (1.772x2.362 inches)", matching GM1 (S8-03-jlc-parsed-4layer-45x60.jpg).
- **Price:** anonymous, 5 pcs, defaults: **$8.00**, build 3-4 days, shipping estimate $25.99. JLC filled the defaults: FR-4 TG135, 1.6 mm, HASL, 1 oz outer / 0.5 oz inner.
- **DFM verdict: UNKNOWN.** The quote page showed no warning; the Gerber Viewer redirected to sign-in (S8-09). The producer stopped and did not visit jlcdfm.com.
- **Stack:** JLC offers JLC04161H-7628 under "Specify Stackup"; the default is "No requirement" (S8-06, S8-07). The Gerbers carry no stack, so the order form decides. The instruction exists only in notes.md.
- **Via covering:** "Tented" is greyed out on 4 layers. Control quotes without an upload showed this is JLC's own 4-layer behaviour, not a reaction to the file (S8-10, S8-11). What JLC does with the file's open vias under "Plugged" is unverified.
- **PCBA not tested:** NEXT saves the PCB to the cart and needs an account, so it was not pressed. BOM/CPL matching and rotation by JLC are untested.
- **Offline checks:**
  - JLC-format BOM (31 lines, all with LCSC) and CPL (55 rows, all Top); 55 = 55 designators.
  - All 157 vias untented on both sides.
  - Mask webs (approximate): 112 via-pad pairs under 0.1 mm, 16 overlapping.
- **Findings:** 2 WRONG ("Tent vias" note vs open vias; pre-order checks blind), 3 FRICTION, 1 COSMETIC. Of the lecturer's P2/P3 items, only hole counts, outline and layer count were "caught and right"; pour-to-NPTH was "missed".

## What worked well
- **Honest refusals where it mattered:**
  - "unknown" for ROM DFU at 25 MHz instead of a guess;
  - refused to cite the SD 100 mA without a source;
  - rejected AMS1117 with the tantalum-only quote;
  - said plainly it cannot add EP vias, fix footprints, move parts or route a 90 ohm pair;
  - DFM lists J3 as "accepted without a datasheet".
- **Datasheet-grounded engineering was right when produced** (engineer and lecturer checked):
  - the 29-pin S1 pin table against Table 8;
  - gm_crit for all four crystals, which rejected the tool's own earlier picks;
  - LDL1117 thermal (80 C, 55%);
  - the 268 mA budget and the 28-day logging figure;
  - the PA10 pull-up reasoning;
  - the firmware bring-up order (I2C_disable / I3C_disable before flash access).
- **Netlist and drawing:** every IC pinout is correct, including the bottom-view LSM6DSO and the SOT-223 tab. 54 parts drawn on 3 sheets in about 55 s. Altium's compile equals the system netlist exactly.
- **Fix #1:** the rebuild works in about 90 s.
- **Routing:** complete (39/39) with 0 shorts and 0 clearance, real GND and +3V3 pours, short decap-to-plane vias. A shorted route was correctly rejected and the board restored from backup. The Extra rules Width rule worked, and the banner explained which rule wins.
- **Placement:** the per-part distance table was accurate to within 0.4 mm of the engineer's own measurements.
- **Outputs:**
  - a complete, well-formed Gerber set (4 positive copper layers; separate PTH, NPTH and slot drills);
  - BOM with every LCSC code (all 8 K4 codes carried);
  - CPL in the Gerber frame;
  - not stale (sha256 match);
  - JLC parsed it on the first upload.
- **The stock check caught the duplicate R4 itself.** The JLC04161H-7628 order note came out correct and in bold.
- **UI patterns worth keeping:** see the designer's keep list above.

## Top 15 fixes, ranked (owner priority: technical correctness first)

1. **Claims must come from applied results, never from intent.**
   - Replace the fixed approval string (`scripts/serve.py:463`) with a report of what was applied.
   - Make `bom.propose` refuse no-op or count-only cards instead of "approved by auto".
   - Have the agent's summary read back the saved state ("Updated the draft", "51 parts").
   - Derive DRC advice from `parse_drc` per-rule counts (silk, slivers), and the order note from the files (tenting, stack).
   - Expose `STACKINFO` / `copper_layer_count` to the agent (`scripts/altium/bridge.py:290`) so it stops denying the stack step.
   - Covers W2, W8, W9, W26, W29, W30, W35.
2. **Tone and status follow findings, not "the step ran".**
   - Amber "not checked yet" in `ui/js/views/pages.js:70-78`.
   - Check board / route tone from `drcSummary` (`ui/js/views/previews.js:587`, :351-367).
   - Placement banner wording (`previews.js` :330-340).
   - Outputs dot from open items (`ui/js/shell.js:101-104`, `scripts/stages.py`).
   - A skipped rule is a warning on its row (`ui/js/views/rules.js`).
   - Covers W14, U1-U3, U6, U7.
3. **Persist the JLC04161H stack.** Restore and implement the `StackLayerProps` calls in `scripts/altium/bridge/AdvisorBridge.pas` (PcbStack, ~2721-2724). Make `ensure_stack` (`bridge.py:1434`) verify thicknesses and dielectric, not only the copper count. Write the stack into the order manifest. Covers W27.
4. **Real keep-outs and hole clearance.**
   - KO footprints on the Keep-Out layer (`partlib_generate.py:425-430`; `AdvisorBridge.pas` `LayerOf` ~797, use `eKeepOutLayer`).
   - Count component-owned copper in `scripts/checks/requirements.py:98`.
   - Add a hole-to-copper / polygon-clearance writer to the rule importer, and block Extra-rule kinds it cannot write.
   - The agent must never delete a requirement to pass a check.
   - Covers W25, W32.
5. **Via tenting and via-to-pad spacing in the JLC preset** (`scripts/jlc_preset.py` plus the rule importer: tent vias, or keep at least 0.2 mm copper from pads). Group DRC into "JLC will reject / JLC accepts / cosmetic", with "Accept with reason" (reuse the DFM Accepted-risks component; `ui/js/views/previews.js`, `ui/js/views/rules.js`). Covers W29, U5.
6. **Power widths:** `max(IPC width, preferred width)` in `scripts/altium/netcurrent.py:99`; a "use trip current" hint on Rules; a pre-route width-feasibility check with neck-down at fine-pitch pins. Covers W28 and FRICTION H.
7. **Pin-aware decoupling and crystals.**
   - Add a cap-to-pin association to the netlist format.
   - Place by it (`scripts/altium/layout.py:1773` `decap_hints`, `:1683` `_DECAP_IC`, `:90` `_SUPPLY_PIN`).
   - Check from each supply pin to its nearest cap, connectors included (`scripts/checks/board.py:249-294`).
   - Add a crystal body keep-out, a no-via rule on crystal nets and short HSE routing (`scripts/altium/route.py`, `negotiate.py`).
   - Covers W23, W24, W31.
8. **CPL correctness.** `scripts/skills/export_cpl.py`: use the footprint origin or body centre, state the rule in the file, and flag parts whose origin and body or pad centre differ (the S3 offset data already exists). Make `outputs-check` validate the CPL that is actually uploaded. Covers W34.
9. **Library converter.**
   - Generate IPC courtyards (pads + body + 0.25 mm) instead of copying F.CrtYd (`scripts/partlib_convert.py:20`).
   - Windowpane paste on exposed pads.
   - Normalise the origin and take the 3D offset from the source.
   - Fix `_pitch` (`scripts/model_preview.py:239-248`) and the pin-1 pick (`:271`).
   - Ignore polylines carrying a diode/zener graphic in the `joined` detection (`scripts/altium/draw.py:172-176`).
   - Make the pin checker parse STM32 package columns and ordering-code notes (U4 QE).
   - Covers W15, W17-W21, W14 (U1).
10. **BOM integrity and selection checks.**
    - Refuse N-part roles with one ref and duplicate refs.
    - Re-bind and re-verify the datasheet on any MPN change.
    - Add gm_crit (crystal vs MCU Gm_crit_max), LDO dissipation (package Pd / thetaJA) and MCU supply-scheme parts to `bom.propose`.
    - Covers W7, W10, W12, W13.
11. **A "Before you order" readiness card and generated order notes.**
    - Outputs page and manifest list DRC by class (0 short / 0 clearance / N JLC-relevant), unverified parts, open conditions and accepted risks, with one explicit "make anyway" (`scripts/store.py:4024-4087`, `stages.outputs_stage`, `ui/js/views/outputs.js`).
    - Generate a README / order note from board facts (stack, finish, tenting, bring-up items).
    - Add Gerber-level checks for mask webs and copper-to-NPTH (`gerber_check.py`, `outputs_check.py`, `order_check.py`).
    - The DFM page states that JLC's verdict needs sign-in and asks for the report PDF.
    - Covers W33, W35-W37, U7.
12. **Scope and Stop guard.** Review chips cannot call `library.build` or create an Altium project. Stop cancels the agent's remaining plan, and the chat reports every side effect. The consent check accepts "yes, ..." with extra wishes. Files: `ui/js/chat.js:588` (chip text), the server-side agent action gate. Covers W11 and FRICTION E.
13. **Tool guard.** Track only the files the agent's own tools wrote; never revert or delete others; use a plain message (`scripts/tool_guard.py` ~155-171, ~239). Covers W1.
14. **Long waits.** Named phases, typical time and "you can leave this page" for both engines and all Altium steps. The running state is held by the server and survives reload; every run ends with a message; a library build of one new part builds one part. Files: `ui/js/views/previews.js` (PV_STEPS :330-340), `ui/js/views/bom.js:151` (`libBusy`), `ui/js/chat.js`, `ui/js/kit.js`. Covers B1 residue and FRICTION A.
15. **One source of truth on the Idea page.**
    - Draft values drive the layers, description, frame title and diagram at once.
    - Goal and description are regenerated or linted on every change (part swaps included); "Set board size" updates the requirement.
    - Assumed items cannot silently become confirmed.
    - The confirmed flag resets on edit, with "Confirm again".
    - Files: `ui/js/views/idea.js` (:132-171, :221-240), idea skill (server).
    - Covers W2-W5 and FRICTION B.

## Run limits
- **JLC:**
  - JLC's DFM verdict was not obtained: the Gerber Viewer requires sign-in, jlcdfm.com was not visited, and no JLCDFM report PDF was ingested (`projects/Final-E2E-4L/checks/` does not exist).
  - PCBA was not tested (NEXT creates a cart item). BOM/CPL matching, part rotations and the J1/J2/U5 centroids were not verified by JLC, so the CPL dispute (W34) and lecturer L3/L5/P3/Q3 stay open.
  - Whether JLC plugs or leaves the file's open vias under "Plugged" is unverified.
  - The order form (JLC04161H-7628, via covering) was deliberately not configured.
- **Altium:** computer use is unavailable on the Team account. Alti checked Altium through the system's own read-only scripts (`bridge.py`, `dump.py`, `preview_*`, `checks/*`), raw PcbDoc record reads, a read-only DelphiScript compile, a DRC run through the bridge, and its own Gerber rasteriser. Altium's ERC violation list was never read. The sheet 03 SVG was checked from data only.
- **Simulated student, web UI only:** no hand moves in Altium by rule, so the N1 decap/crystal moves were waived (ruling 06:15) and routing and outputs were judged on the system's own placement. One board, one run. Engines alternated by stage, so engine-to-engine comparisons are not controlled.
- **Unverified numbers carried in this report:**
  - J1/J2 origin 1.42 / 2.32 mm off the body (agent claim);
  - the BME280 land-pattern figures (PDF encrypted for the engineer);
  - the U1 0.054 mm mask dam (from Altium DRC; not reproduced by the producer's script);
  - pour-to-NPTH 0.16 mm (Alti only);
  - the producer's mask-web counts (approximate rectangles).
- **Not reproduced:** the 45 s "New project" freeze (S0, under RAM pressure on an 8 GB machine).
- **Harness side effect:** the run folder inside the install triggered `tool_guard` (C18/C19), fixed by excluding it from git. LCSC stock data was about 5 hours old at S8 and not re-queried.
- **No physical board:** DFU via BOOT0 (K5), crystal start-up and VCAP1 behaviour remain bring-up tests.
- **Late gates:** lecturer S7 had one round only; there is no evidence its Q1/Q2 conditions were acted on before S8.
