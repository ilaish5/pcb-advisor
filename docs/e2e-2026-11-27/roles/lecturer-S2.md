# Lecturer – Stage 2 (BOM + stock)

## Video highlights
- S2-15-qty-still-1-after-reload.jpg | Agent says "51 parts", but the page still shows Qty 1 and 28 parts.
- S2-35-r2-5-cards-crystals-ldo.jpg | The gm_crit check shows both crystals fail Tables 37/38; replaced with 6 pF and 8 pF parts.
- S2-57-settings-altium-project-created.jpg | An Altium project exists even though the student pressed Stop during a review question.
- S2-28-all-28-in-stock.jpg | Lecturer round 1: FIX. LSE crystal gm margin, LDO at 95% of Pd, IMU requirement out of date.
- S2-55-stock-check-r4-duplicate.jpg | Lecturer round 2: PASS with conditions. Crystals, LDO and requirements fixed; scanned datasheets carried to stage 3.

# Round 1

Evidence: `roles/student.md` (S2), `roles/student-confusions.md` C29–C40, `screens/S2-01..30`, `projects/Final-E2E-4L/bom.json`
(28 lines, 51 parts), `proposals.jsonl`, `idea.json`, `idea-draft.json`, the chat from 01:32, and the datasheets in `sources/` (I checked them myself).

## What is good
- You read the BOM critically and named five real problems in one message: quantities, PB2, IMU stock, AMS1117 with a ceramic cap,
  and a current budget from datasheets instead of typical values.
- You swapped the IMU for stock reasons (ICM-42688-P had 11 pcs against the 15 you need → LSM6DSO, 21,690 pcs). The LSM6DSO covers ±8 g, ±1000 dps and a 208 Hz ODR.
- You replaced the AMS1117 because its datasheet promises stability only with a 22 µF tantalum. The ME6211 is quoted as "compatible
  with low ESR ceramic capacitors". That is the right reasoning, with a source.
- VCAP1 = 4.7 µF ceramic (C10) matches Table 16 ("single VCAP pin: 4.7 µF, ESR < 1 Ω"). There is a 4.7 µF on VDD (C11), per Figure 17 note 2.
- All 28 lines have LCSC codes and were stock-checked with a timestamp. The passives are JLC Basic.
- Stage 1 conditions: **C1** PB2/BOOT1 pull-down R13 ✓. **C2** SDIO pull-ups R6–R10 (47k) ✓. The card-detect pull-up is not in the BOM, so say
  in S4 whether you use the internal one. **C4** done only in part (see Q2). **C3 and C5 not done** (see Q3).

## Questions you must answer (round 1)
1. **Will your RTC crystal start?** Y2 (Q13FC13500004, CL 12.5 pF) has no datasheet in Sources. Table 38 of the F411 gives
   Gm_crit_max = **0.56 µA/V** (low-power) and **1.50 µA/V** (high-drive) for the LSE. gm_crit = 4·ESR·(2πf)²·(C0+CL)².
   With the ESR ≈ 70 kΩ and C0 ≈ 1 pF typical of this crystal family (my numbers, not verified), you get about **2.2 µA/V**. That fails
   even in high-drive. Show the calculation from the real crystal datasheet, or choose a CL ≤ 7 pF crystal (ST AN2867). Do the same for
   Y1: Table 37 gives Gm_crit_max = 1 mA/V for the HSE, and a 25 MHz CL 12 pF crystal with ESR 40–50 Ω lands at about 0.8–1.0 mA/V, at the edge. Your
   15 pF load caps come from the agent's "2·(CL − about 5 pF stray)" estimate. Where is your stray figure from?
2. **LDO dissipation, condition C4.** The ME6211 datasheet gives Pd = **300 mW** for SOT-23 (absolute maximum). Your own budget is 168 mA ×
   (5 − 3.3) V ≈ **0.29 W**, which is 95% of the maximum at 25 °C with no derating. Is 168 mA a peak or a continuous figure? What junction temperature do you get?
   Do you move to the SOT-89 variant (500 mW) or another part? Also, the U5 line still links **AMS1117-3.3.pdf** as its datasheet, and the VBUS
   budget used the AMS1117's 11 mA quiescent current. Which part's numbers are you actually using?
3. **Which IMU does the board have?** The BOM says LSM6DSO. The confirmed requirement and the goal paragraph in `idea.json` still say **ICM-42688-P**.
   The change exists only in an unsaved Idea draft (`idea-draft.json`), and even that draft's goal still says ICM. Stage 1 conditions
   **C3** ("24 h on a 16 GB card" is still in the Logging line) and **C5** (records marked "time not set" when there is no host) were not touched either. Save
   a consistent requirement set.
4. **Decoupling against Figure 17.** You have 12×100 nF for VBAT, 3×VDD, VDDA, the IMU, BME280, flash, SD and NRST. Where is the **1 µF on VDDA** that the
   F4 power-supply scheme shows next to its 100 nF? (The figure is a graphic, so check it visually.) The SD card is your biggest load: the 100 mA is
   uncited. The SD Physical Layer Simplified Specification is free, so why is it not in Sources? Is 10 µF of bulk enough for the
   hot-insertion surge of a push-push slot?
5. **Known-bad choices and parts without datasheets.** You approved 680 Ω for the green LED after the tool told you it gets "about 1 mA or less".
   At Vf = 3.1 V that is 0.3 mA, which is practically off. Why not the 360 Ω it offered? And eight lines have **no datasheet** (J1 USB-C, J2 microSD, J3 SWD,
   Y1, Y2, D1, D2, F1). How will you check the USB-C and microSD pinouts and footprints in stage 3 without them?

## Verdict round 1: **FIX**
The BOM is complete, in stock and mostly sensible. But Q1 can stop the RTC from starting, Q2 runs the regulator at its absolute
limit, and Q3 leaves the requirements contradicting the BOM. Fix through the BOM and Idea chat, Save the Idea page, and answer Q4–Q5.

---

## System findings (the TOOL)
- [WRONG] Wrong datasheet bound to a BOM line after an MPN swap. Evidence: `bom.json` U5 has `mpn: ME6211C33M5G-N` but `datasheet:
  AMS1117-3.3.pdf`. The chat budget at 01:39 adds "the LDO's own 11 mA" from the AMS1117 and was not redone after the swap (01:42). Why it matters:
  every later pin or limit check on U5 reads the wrong document. Generic cause: the BOM line update changes `mpn` and `lcsc` but does not
  re-bind or clear `datasheet`.
- [WRONG] Crystals were chosen with no datasheet and no oscillator margin check. Evidence: `bom.json` Y1 and Y2 have `datasheet: ""`. The load caps come from
  "2·(CL − about 5 pF stray)" (chat 01:34). The F411 Table 38 LSE Gm_crit_max of 0.56/1.50 µA/V was never compared with the crystal (my estimate
  ≈ 2.2 µA/V uses typical values and is unverified). Why it matters: an LSE that does not start is a classic STM32 board failure. Generic cause:
  part selection has no rule like AN2867 for crystals (gm_crit, CL, ESR), and it accepts parts with no datasheet.
- [WRONG] The agent claimed a state the page did not show. Evidence: chat 01:39:22 says "The BOM now has 51 parts". S2-13 and S2-15 show 28 lines with
  every Qty at 1, and the red "Check qty" tags remain after reload (C30, C33, C35). The fix cost two rounds (C36). The agent itself admitted
  "the earlier cards gave only a count, the page counts parts from the reference list". Generic cause: the BOM card accepts a quantity with no
  refs and is "applied with warnings" instead of being refused. The agent's reply does not check the result it describes.
- [WRONG] An action outside the request and outside the stage. Evidence: the chip "What is wrong in the BOM (28 open)" → the agent says "I'm building the library
  now", calls `library.build`, and after it fails says "I'm creating the project and then building the library" (chat
  01:49:52, 01:50:19; S2-29, C38). The student stopped it. Why it matters: a review question must not create Altium projects. Generic
  cause: no scope guard between "review" prompts and stage-changing actions. The chip text "28 open" invites a fix.
- [FRICTION] The requirement change was parked in an unsaved draft. Evidence: `idea-draft.json` (01:39:21) has "Motion sensor: LSM6DSO … (replaces ICM-42688-P)",
  `idea.json` still has ICM-42688-P, and the draft's own goal paragraph still says ICM. The BOM page gives no prompt to save the Idea page. Why it
  matters: requirements and BOM silently disagree, and later stages read `idea.json`. Generic cause: cross-stage idea proposals land in a
  draft that is not visible from the current page, and the goal is not regenerated (the same cause as the S1 finding).
- [FRICTION] Two different "datasheet" figures for the same quantity. Evidence: the MCU current is "35.5 mA, Table 25" in S1 round 2 (student.md Q5)
  and "32.3 mA, Table 24, p. 71" in S2 (chat 01:39). There is no note on which is right or why it changed. Generic cause: no reuse of earlier sourced
  values in the session.
- [FRICTION] Changes were applied without asking, and listed as raw IDs. Evidence: chat 01:39:22 "Applied without asking (important mode, the student can undo):
  p20261127013921739, …", and "Approved 28 proposals: p2026…" lists (01:35, 01:44, 01:48). Why it matters: the student cannot see what was
  applied. Generic cause: the confirmation message shows proposal IDs instead of refs and values.
- Good tool behaviour worth keeping: it refused to call the AMS1117 stable with ceramic and cited the tantalum-only text. It refused to cite the 100 mA SD
  current without a source. It warned about ICM-42688-P stock before approval (11 against 15 needed). It worked out the dim green LED with calc.py and offered
  360 Ω. It corrected its own count in the chat ("31 → 28 cards"). It found the PB2 = BOOT1 pin in Table 8 itself.

---

# Round 2 (last)

Evidence: `roles/student.md` "Answers to lecturer S2", confusions C41–C48, `screens/S2-31..57`, `bom.json` (30 lines, 52 parts, no
duplicate refs), `idea.json` v8 (02:13:51, no draft pending), and `sources/` (LDL1117S33R Table 3, F411 Tables 37/38; I checked them myself).

## Answers checked
1. **Crystals: fixed, with a source.** The old Y2 (2.16 µA/V) and Y1 (1.11 mA/V) both failed. Y2 is now SC-32S 6 pF at 0.58 µA/V, which is
   under the 1.50 µA/V high-drive limit and just over the 0.56 low-power limit. "LSE drive: firmware must set high-drive" is now a requirement, which is correct.
   Y1 is now S3225000081040 8 pF at 0.72 mA/V, under 1 mA/V. My own check with ESR 70 kΩ and C0 ≈ 0.9 pF gives about 0.57 µA/V for Y2, which agrees. The load caps
   (2 pF, 5.6 pF) rest on an **unsourced 5 pF-per-side stray estimate**. If the real stray is 2 pF lower, a 6 pF tuning fork shifts by
   tens of ppm, up to about 100 ppm (my estimate), which is several s/day. You accepted "tune on the prototype". See condition K2.
2. **LDO: fixed.** LDL1117S33R in SOT-223: Table 3 gives θJA = 120 °C/W, Tj ≈ 25 + 0.46×120 = 80 °C, and (125−25)/120 = 0.83 W, so all the numbers check.
   §6.2 covers ceramic caps. The datasheet is now bound to U5 and the budget uses LDL1117 numbers. The 268 mA is a peak, so this is conservative. Accepted.
3. **Requirements: fixed.** The goal, the Motion sensor line (LSM6DSO), Logging (about 28 days on 16 GB), "time not set", LSE drive, Regulator and
   VBUS protection all agree on 268 mA. Conditions C3 and C5 from stage 1 are closed. No unsaved draft is left.
4. **VDDA: fixed** (C22 1 µF plus 100 nF). **SD current: corrected** from 100 mA to 200 mA in SD mode (Table 4-12, from a third-party copy of the
   simplified spec, so "file only"). Hot-insertion bulk: "unknown" is an honest answer. See K3.
5. **LED: fixed** to 360 Ω. Green current is 0.5–1.9 mA over the Vf range from the tool's earlier 2.6–3.1 V figure, dim but visible. **Datasheets: attached, but 3
   are scans (J1, J2, Y1), J3 has no pin table, and Y2 is an HTML page.** You said so honestly. See K1.

## Verdict round 2: **PASS with conditions** (carried forward)
- **K1 (S3 library):** footprints and pinouts for J1 USB-C, J2 microSD and Y1 must be checked **by eye against the scans**, and J3 against the 10-pin
  Cortex-debug pinout. D3/D4 LEDs and SW1/2 have no datasheet at all, so their polarity and pad marks need a source before placement. Alti/engineer: please verify.
- **K2 (S4/S7):** keep the 2 pF and 5.6 pF load caps as tunable pads and plan to use the RTC smooth calibration. The firmware note "LSE high-drive" goes into the
  outputs/README.
- **K3 (S5 placement):** C19 10 µF right at the microSD slot. Hot-insertion is unverified and accepted for a prototype.
- **K4 (S7 outputs):** 8 lines (U5, Y1, Y2, R3, C15, C17, C22, R4) have an empty `lcsc` field. The LCSC code is only in `code`/`supply`. The
  JLC BOM export must still carry C435835, C479202, C2692145, C270607, C1574, C1558, C52923, C25130. Check it.
- **K5:** still open from S1: USB DFU and AN2606 unverified, and PA10 level not checked. SWD stays the main path.
- Note: the Extended count grew (R3 360 Ω, 2 pF, 5.6 pF, crystals, U5), so one-off fees are now $49.12 against the "Basic preferred" requirement. That is acceptable for 5 boards.
  A Basic 330 Ω (if one is available) would have avoided one fee.

---

## System findings, round 2 (new)
- [WRONG] Stop did not stop the plan: an Altium project was created as a side effect of a review question. Evidence: chat 01:50:19 says "I'm creating the
  project and then building the library", followed by "library.build: stopped by the student". Settings now shows `Final-E2E-4L.PrjPcb`, `.PcbDoc`, `Main.SchDoc`
  (S2-57, C41, C48), where before it said "Not linked" (C29). Why it matters: an outward, persistent action the student did not ask for and believed he had stopped. Generic cause: Stop cancels
  only the pending step, not the agent's remaining plan. Project creation has no student gate.
- [WRONG] An approved card created a duplicate reference. Evidence: the R3 change ("R3 now 360, R4 stays 680") left R4 on both lines, and the header read 53 parts for about 10 min
  until the stock check caught it (S2-55, C47). Generic cause: applying a BOM card does not enforce unique refs across lines.
- [FRICTION] The datasheet check ran against the old part. Evidence: "U5 ← LDL1117S33R.pdf: unchecked (does not mention ME6211A33PG-N … may be the
  datasheet of another part)" (S2-51, C45). The attach was validated before the MPN change was applied, so the warning was false. Generic cause:
  the order of operations inside a multi-field line change.
- [FRICTION] The goal paragraph went stale again after a part change. Evidence: v7 goal still said "ME6211, SOT-89" after the LDL1117 swap (S2-52, C46),
  and the card said "Tj about 86 C" while the requirement says 80 °C. This is the third time (S1 ICM/I2C, S2 r1 ICM, S2 r2 LDO). Generic cause: the goal
  is not regenerated or linted against agreed items and BOM parts on change.
- [FRICTION] Datasheet trust is invisible on the BOM page. Evidence: chat lines "J1 … unchecked (may be the datasheet of another part)", "Y1 has no
  text to read (a scan)", and claims marked "File only, not verified" mixed with green ticks (S2-45, S2-51, C44). The BOM page shows none of this. Generic cause:
  `sources/*.quality.txt` and the attach check results are not surfaced on the line.
- [FRICTION] One field, two places. Evidence: `bom.json` U5, Y1, Y2, R3, C15, C17, C22 and R4 have `lcsc: ""` but `code` and `supply.LCSC.code` set
  (different card paths fill different fields). Risk for the JLC BOM export, unverified until S7 (K4).
- [FRICTION] The idea confirmation stays stale (repeats S1 C27). Evidence: `confirmed_at` is 01:08:13, while v5–v8 were saved 02:04–02:13 with the requirement set
  changed. "confirmed 27 Nov" is still shown.
- Good tool behaviour worth keeping: the gm_crit calculation used Tables 37/38 and the crystal datasheets, and it rejected two crystals the tool itself had picked earlier.
  It corrected the SD current with a cited table. It said honestly that scans cannot be pin-checked and that hot-insertion is unknown. The U5 card showed old values crossed out next to the new ones,
  which the student called the clearest card in the app. The stock check caught the duplicate R4.
