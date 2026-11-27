# Engineer review, Stage 2 (BOM + stock)

## Video highlights
- S2-08-bom-approved-28-lines.jpg | First BOM: every line Qty 1, "28 parts", though roles name two parts.
- S2-13-agent-answer-warnings-again.jpg | Agent claims "BOM now has 51 parts"; its cards changed nothing.
- S2-45-r2-msg3-answer-3-cards.jpg | Good catch: crystal gm math checks out; both crystals fail and are replaced.
- S2-57-settings-altium-project-created.jpg | An Altium project was created although the student pressed Stop.

Scope: system side only (what the app showed, claimed and stored). Evidence: projects/Final-E2E-4L/{bom.json,
proposals.jsonl, supply-log.jsonl, turns-log.jsonl, chats/2026-11-27-0103.jsonl, idea.json, sources/*.txt},
screens S2-01..S2-30, student.md and student-confusions.md C29-C40. BOM.csv does not exist yet (no export was made).

## Verdict
Part identity is clean: all 28 lines have MPN = LCSC code = package, `exact: true`, and every stock and price the
chat quoted matches supply-log. The datasheet quotes the agent made are real. The system got wrong what it should
compute itself: quantities (two rounds and a false "51 parts" claim), MCU support parts from the datasheet (VDDA
1 uF), oscillator margin for the LSE crystal, LDO dissipation, and keeping the requirements in step with the IMU
swap. It also started an unrequested library build.

## System findings

- [WRONG] The first BOM had Qty 1 on every multi-part role. The 01:34 proposal created 28 lines with one ref each,
  although the roles say "CC1/CC2 pull-downs", "I2C SCL/SDA pull-ups", "SDIO CMD/D0-D3 pull-ups" and "Decoupling
  (MCU VBAT, 3x VDD, VDDA; IMU ...; flash; SD)" (S2-08; C30). The system only attached a warning card ("the role names
  2 parts but there is 1", C31) and still let "Approve all" apply. The agent's answer did not mention quantities at
  all. So the student got a 28-part BOM for a board the idea describes as about 70 parts. Generic cause: bom.propose
  accepts a line whose role implies N parts with a single ref; this should be refused or auto-expanded, not warned.
- [WRONG] False claim "The BOM now has 51 parts" (chat 01:39:22). The quantity cards the agent sent at 01:39 changed
  nothing: proposals.jsonl p20261127013921739 (R3) has `changes == before` ({value 680, role "LED series
  resistors"}), and it was "approved by auto". The page stayed at 28 parts and Qty 1 (S2-15, C35). The agent
  admitted it at 01:42 ("the earlier cards gave only a count, the page counts parts from the reference list"), and
  only the re-sent cards with `refs` (e.g. p20261127014221913 R1 to [R1, R2]) fixed it. Generic cause: a count field
  is silently dropped from a card, a no-op card is applied and counted as done, and the chat reports the intended
  result instead of what was applied.
- [WRONG] The LSE crystal was picked without the STM32's oscillator-margin check, and it likely fails it. Y2 is
  Q13FC13500004 (Epson FC-135) with CL 12.5 pF (bom.json Y2 value "32.768 kHz 12.5 pF"). The F411 LSE allows
  Gm_crit_max 0.56 uA/V in low-power mode and 1.50 uA/V in high-drive mode (datasheet Table 38, txt ~4789). With
  FC-135 figures I know from memory (ESR max 70 kOhm, C0 about 1 pF; no crystal datasheet is in sources/):
  gm_crit = 4 x 70k x (2 x pi x 32768)^2 x (13.5 pF)^2 = about 2.2 uA/V, above both limits. ST's AN2867 guidance
  for STM32F4 LSE is a low-CL (6-7 pF) crystal. The same FC-135 with CL 7 pF gives about 0.8 uA/V (passes in
  high-drive). Generic cause: the BOM flow never fetches crystal datasheets and never computes gm_crit vs the MCU's
  Gm_crit_max. The HSE was not checked either: Y1 X322525MOB4SI 25 MHz vs Gm_crit_max 1 mA/V (Table 37, txt 4741),
  so its margin is unknown.
- [WRONG] VDDA decoupling is missing the datasheet's 1 uF. For packages where VREF+ is tied to VDDA (UFQFPN48), the
  F411 datasheet asks for "1 uF // 10 nF" on VDDA (Figure 43, txt ~6418-6425). The BOM gives VDDA only one 100 nF
  from the C1 group (bom.json C1 role "... VDDA ..."), and there is no 1 uF line. The other MCU support parts are
  right: VCAP1 4.7 uF X5R 0603 (C10, Table 16 asks 4.7 uF, ESR < 1 ohm), 4.7 uF on VDD (C11, Figure 17 note 2),
  100 nF per VDD, VBAT 100 nF, NRST 100 nF, BOOT0 and PB2 10k pull-downs (R5, R13).
- [WRONG] The LDO was chosen on its 500 mA rating, but its package limits it below the system's own budget. The
  ME6211 datasheet gives PD = 300 mW for SOT-23 (abs-max table, ME6211 txt ~195-200). The agent's own budget is
  "about 168 mA on 3V3" (chat 01:42). (5.0 - 3.3) V x 0.168 A = 0.29 W at 5.0 V VBUS, and 0.33 W at the 5.25 V
  USB maximum, so the part is at or over its rating at the stated peak. The chat only says "It's 500 mA" (01:42). A
  SOT-89 package (PD 500 mW in the same table) or a check of average vs peak was needed. The claim "500 mA" is true
  for the die but misleading for this board. Generic cause: no dissipation check in LDO selection.
- [WRONG] The requirements were not updated after the IMU swap. U2 is now LSM6DSOTR (bom.json U2, approved
  01:40:22), but idea.json still says "Motion sensor: ICM-42688-P 6-axis IMU on SPI" (status confirmed), and
  "Logging: IMU 200 Hz" while the agent itself said the LSM6DSO "has a 208 Hz rate" (chat 01:39; LSM6DSOTR txt 368:
  ODR steps include 208, no 200). The BOM and the confirmed requirements now contradict each other, and nothing
  flags it. The pin plan still fits: SPI1 plus CS PA4 plus INT1 on PB0 works for the LSM6DSO. Generic cause: no
  BOM-vs-requirements consistency check (the same family as the S1 description and diagram staleness).
- [WRONG] The system took an action the student did not ask for. The chip "What is wrong in the BOM (28 open), and how
  do I fix it?" led to "To fix it, I'm building the library now", and then "I'm creating the project and then
  building the library" (chat 01:49:52 and 01:50:19; S2-29, C38). It failed only because no Altium project was
  linked, and then the student pressed Stop. A review question must not trigger a build plus an Altium project
  creation. Generic cause: the chip's "how do I fix it" wording plus an agent allowed to call library.build and
  project creation without a confirmation gate.
- [FRICTION] The green LED was knowingly left dim. D3 KT-0805G (Vf 2.6-3.1 V) with R3 680 ohm gives 0.3-1.0 mA. The
  agent said so (01:47), but left 680 ohm on both LEDs and quoted "360 ohm gives about 2 mA", which holds only at
  Vf min: (3.3 - 2.6) / 360 = 1.9 mA, while at Vf max (3.3 - 3.1) / 360 = 0.6 mA. A 3.3 V rail with a 3 V green LED
  needs a lower-Vf LED or about 100-150 ohm. The note is on neither the BOM line nor the role (C40).
- [FRICTION] The MCU current number changed between stages without a reason. In S1 it was "at most 35.5 mA (Table
  25)": ART on, 105 C max, which is correct. In S2 it is "32.3 mA (Table 24, p. 71)": ART off and the 85 C column
  (Table 24 txt 4098: 100 MHz 29.5 / 31.5 / 32.3 / 33.3). Both are real cells, but the S2 cell is lower and less
  representative (firmware runs with ART on), and the "Max" column was picked without stating the temperature.
- [FRICTION] The price basis is mislabelled. The first answer said "about $46 per board at 5 boards" (01:34), but
  supply-log prices are the 10-piece break (`qty_break: 10`, e.g. ICM-42688-P $25.56, STM32 $4.70). The page footer
  says "Prices at qty 10" (S2-28). For 5 boards each IC is bought at the 1-9 price (STM32 $5.31 per the S1 lookup),
  so $21.88 per board is an underestimate. The $33.77 extended fee is correct as computed: 11 Extended lines x $3.07
  (store.py:523, 561).
- [FRICTION] TVS vs LDO rating was not checked: D2 SMF5.0A clamps at about 9.2 V at rated pulse current (my memory,
  no TVS datasheet in sources), above the ME6211 VIN abs max of 6.5 V (ME6211 txt 191). This is acceptable for a
  hobby board behind a PTC, but no check was made or mentioned. Standoff 5.0 V vs USB VBUS max 5.25 V: slight
  leakage at high VBUS, also not mentioned.
- [COSMETIC] "All 14 lines now have JLC Basic parts" (01:47): R3 0402WGF6800TCE is "Preferred", not Basic
  (bom.json R3 library_type). The conclusion "no extra Extended fees" still holds.
- [COSMETIC] The ME6211 dropout was given as "120 mV at 100 mA" (01:34); the datasheet says 100 mV typ at 100 mA and
  210 mV at 200 mA (ME6211 txt 68, 471).
- [COSMETIC] bom.json `availability: "low"` on Extended lines with huge stock (e.g. J1 TYPE-C-31-M-12, stock 404,603;
  U5 ME6211, 210,430). The page shows the right tags (S2-08 "Extended fee"), but the stored field is misleading for
  any later consumer.

## Claims checked (TRUE)
- MPN, LCSC code and package are consistent on all 28 lines (bom.json `supply.LCSC.exact: true`, code = lcsc, package
  = LCSC package). There are 51 refs in total, matching "51 parts" after the 01:44 re-send. W25Q128JVSIQ is the 3 V
  JV part (my S1 concern is resolved).
- Stocks quoted in chat match supply-log: LSM6DSOTR 21,690; BME280 758; STM32 2,705; ME6211 210,440 at 01:32 vs
  210,430 at 01:49; ICM-42688-P 11 at $25.56 (C1850418).
- AMS1117 "only promises stability with '22 uF solid tantalum'": TRUE (AMS1117 txt 424-430). The quiescent current
  of 11 mA is the max (txt 324-330). Rejecting it for a ceramic-stable LDO was correct.
- ME6211 "compatible with low ESR ceramic capacitors": TRUE (txt 57). "500 mA": TRUE as IOUTMAX (txt ~466), but see
  the dissipation finding.
- Flash program 25 mA: TRUE (W25Q128JV ICC5 max 25 mA, txt 3190).
- LSM6DSO 0.55 mA, "typical only, no max given": TRUE (txt 4, 426). 208 Hz ODR and +-16 g / +-2000 dps cover
  +-8 g / +-1000 dps: TRUE.
- BME280 0.714 mA: the value is in the BME280 text (txt 239); whether it is typ or max is ambiguous in the extract.
  It is immaterial to the budget.
- Budget arithmetic: 32.3 + 25 + 9.7 + 0.714 + 0.55 = 68.3 mA; +11 mA AMS1117 Iq = 79; +100 mA SD = 168. TRUE. The
  agent was honest that the SD 100 mA is not cited ("the SD spec isn't in Sources").
- PB2 = BOOT1 at pin 20 (Table 8): TRUE. R13 10k pull-down was added (my S1 round-2 finding is resolved in the BOM).
- Load caps "2 x (CL - about 5 pF stray)": the formula is stated as an estimate. 15 pF fits CL 12 pF and 12.5 pF with
  about 5 pF stray. The issue is the LSE crystal choice, not the caps.
- Pull-ups: SDIO 47k (5) is within the SD spec range of 10-100k; I2C 4.7k; CC 5.1k x 2; BOOT0 and BOOT1 10k. All
  sound.
- USB parts: USBLC6-2SC6 (C7519), TYPE-C-31-M-12 16-pin USB 2.0 (C165948), nSMD050-16V 0.5 A hold 1206 (C70075),
  SMF5.0A (C151296), TF-01A push-push (C91145). Real parts, codes consistent with package, and suitable in function.

## For the lecturer (student decisions, not system findings)
- The student accepted the 10-piece price basis and the dim green LED (C40). The IMU swap was the student's call,
  and correct given 11 in stock.

## Still to check later (S3/S4)
LSM6DSO CS pull-up (SPI mode lock) and flash /CS pull-up; BME280 CSB to VDDIO and SDO address strap; TF-01A
card-detect pin wiring; crystal footprints and pin 1 of the 4-pad 3225; LGA-14 footprints for U2 and U3.

---

# Round 2 (chat 01:55-02:14, BOM 30 lines / 52 refs, idea v8)

Checked against: F411 datasheet Tables 37/38 and the HSE text (txt ~4718-4763); Q13FC13500004.pdf (text);
SC-32S-6pF.pdf (text); X322525MOB4SI.pdf and S3225000081040.pdf (scans, which I read as images); LDL1117S33R.pdf
(Tables 1 and 3, 6.2, Equation 1); cites.json, library-log.jsonl, altium-log.jsonl, serve.py.

## Verdict (round 2)
The engineering in this round is correct and well sourced. Every number I could check matches its datasheet:
gm_crit for all four crystals, LDL1117 thermal, VDDA 1 uF, the 268 mA budget and the 28-day figure. The round-1
findings on LSE, HSE, VDDA, LDO dissipation and IMU requirement are resolved in the BOM and the Idea data. What is
still wrong is system plumbing: a canned approval message claims schematic and library updates that do not exist,
the Stop did not prevent an Altium project from being created, and "checked" datasheets are unchecked in the
system's own verify data.

## System findings (round 2)

- [WRONG] A canned approval text claims work that never happened: "Approved. U5 is updated in the BOM, on the
  schematic label and in the library" (chat 02:12:16). No library exists (bom.json U5 `library: missing`, all lines
  missing), and the schematic is an empty skeleton (altium-log 01:50:19 `skeleton ... created: []`). The text is
  fixed in scripts/serve.py:463, `"updated in the BOM, on the schematic label and in the library"`, for every
  non-new proposal regardless of state. Generic cause: the confirmation string does not report what was really
  applied.
- [WRONG] (round-1 finding, now confirmed worse) The unrequested build did create an Altium project. altium-log:
  01:50:11 `new-project` (Final-E2E-4L.PrjPcb, Main.SchDoc, Final-E2E-4L.PcbDoc), then 01:50:19 `skeleton`. Yet the
  chat at 01:50:19 says only "(Not applied: library.build: stopped by the student before it ran)", so the student
  is told nothing ran (S2-57, C41). Stop cancelled the build but not the project creation that came before it, and
  the chat note hides the side effect.
- [FRICTION] "Checked: D1, D2, F1 and J3. Each file names its part" (02:10:48) contradicts the system's own verify
  data. bom.json library_entry: J3 is `unchecked`, "text is mostly Chinese/Japanese/Korean, so a pin table cannot
  be matched" (HX-PZ1.27-2x5P.pdf has 66 chars per page); F1 is `unchecked`; D1 and D2 were never verified
  (`None`). "Names its part" is true, but calling it "checked" overstates it. U5 also keeps a stale verify note,
  "LDL1117S33R.pdf does not mention ME6211A33PG-N": verify ran against the previous MPN and was not re-run after
  the swap.
- [FRICTION] A duplicate designator was accepted: R4 sat on both the 360 ohm line (R3) and its own 680 ohm line until
  the 02:14 stock check found it (chat 02:14:12, C47). The system caught and fixed it itself, but bom.propose
  should refuse a ref already used on another line.
- [FRICTION] The stray-capacitance rule was cited to the wrong section, and the agent did not say how it read it.
  "10 pF can be used as a rough estimate of the combined pin and board capacitance" is cited as "LSE oscillator",
  but in the datasheet it sits in the HSE section (txt 4720-4763, before Table 37). The formula C = 2 x CL - 10 pF
  reads the 10 pF as per-leg stray. Read as total stray, it would give negative caps. The resulting LSE caps of 2 pF
  are below the 5-25 pF range in the same ST paragraph. The card does say "tune on the prototype", which keeps this
  from being WRONG.
- [FRICTION] Five new Extended lines were added without mentioning the fee: R3 360 ohm (0402WGF3600TCE), C15 5.6 pF,
  C17 2 pF, Y1 and Y2 are Extended (bom.json). The extended fee went from $33.77 to $49.12 (16 x $3.07). At 01:47 the
  agent itself had steered passives to Basic to avoid fees. The crystals are justified. The three passives could
  probably have been Basic values (e.g. 330 ohm), but the system neither checked nor mentioned it.
- [COSMETIC] On 8 lines (U5, Y1, Y2, R3, C15, C17, C22, R4) `lcsc` is empty or null, while `code` and
  supply.LCSC.code hold the exact code (e.g. U5 C435835, Y1 C479202, Y2 C2692145, C22 C52923). order_check.py and
  design_report.py fall back to `code`, so this is not an error today. Re-check in S7 that the JLC BOM export
  carries these codes.
- [COSMETIC] The Logging requirement still says "IMU 200 Hz", and 6.4 kB/s, 553 MB/day and 28 days are computed at
  200 Hz. The LSM6DSO has 208 Hz (the agent said so itself at 01:39), which gives 6.66 kB/s, 575 MB/day and about
  27.8 days. The difference is negligible, but the requirement names a rate the part does not have.
- [COSMETIC] An orphan source: 7V25080026.pdf (TXC 25 MHz 8 pF) was downloaded during the crystal search and is not
  attached to any line.

## Claims checked (round 2, all TRUE)
- Y2 old, Q13FC13500004: R1 max 70 kOhm, C0 1 pF, CL 12.5 pF (datasheet text). 4 x 70k x (2 pi x 32768)^2 x
  (13.5 pF)^2 = 2.16 uA/V, above 1.50 (high-drive) and 0.56 (low-power) in F411 Table 38. FAILS, which matches my
  round-1 estimate.
- Y2 new, SC-32S 6 pF: the series sheet gives 70 kOhm max and C0 1.0 pF typ (SC-32S-6pF.pdf text shows the 12.5 pF
  CL; the 6 pF option comes from the Seiko page, as the agent disclosed). (1 + 6) pF gives 0.58 uA/V: passes only in
  high-drive (0.39 of the limit) and fails low-power. TRUE. The requirement "LSE drive: high-drive in firmware" was
  added to idea.json; it is correct and necessary.
- Y1 old, X322525MOB4SI: the scan (YSX321SL sheet) shows ESR 50 ohm max for 16-31 MHz and C0 3 pF max. With CL
  12 pF: 4 x 50 x (2 pi x 25 MHz)^2 x (15 pF)^2 = 1.11 mA/V, above the F411 HSE Gm_crit_max of 1 mA/V. FAILS. TRUE.
- Y1 new, JGHC S3225000081040: the scan (S32 series) shows ESR 60 ohm max for 20-29.999 MHz and C0 3 pF max, with
  CL 8 pF. 4 x 60 x (2 pi x 25 MHz)^2 x (11 pF)^2 = 0.716 mA/V. Passes. TRUE. Its pinout (crystal on pins 1 and 3,
  GND on 2 and 4) matches the YXC part it replaces.
- "The formula comes from ST AN2867, which is not in Sources": honest. cites.json marks these citations `file_only`
  (no quote compared); I verified the numbers by hand.
- VDDA 1 uF: TRUE (Figure 43, "1 uF // 10 nF", cite `ok`). C22 CL05A105KA5NQNC (C52923) was added. The existing
  100 nF on VDDA covers the 10 nF part.
- SD current: the quote "In SPI mode ... up to 0.36W (100mA at 3.6V on VDD1)" was found in the file (cite `ok`).
  The 0.72 W / 200 mA default for SD mode is cited `file_only`; it is consistent with SD Physical Layer v4.10 Table
  4-12 as I know it, and the third-party copy is disclosed. "Hot insertion unknown (sections 6.1-6.3 are not in the
  simplified spec)": honest.
- ME6211 (intermediate step): "0.29 W is 95% of 300 mW" TRUE; SOT-89 PD 500 mW TRUE (abs-max table); "0.46 W = 91%
  of 500 mW" TRUE (0.268 x 1.7 = 0.456 W).
- LDL1117S33R: thetaJA 120 C/W (Table 3); the tab is VOUT, with pins GND 1 / VOUT 2 / VIN 3 (Table 1); "Any good
  quality ceramic capacitor can be used" (6.2); PDMAX = (125 - TA) / RthJA (Equation 1), which gives 0.83 W at 25 C;
  VIN 2.5-18 V. Tj = 25 + 0.458 x 120 = 80 C; 0.458 / 0.83 = 55%; +0.1 V of VBUS adds 0.1 x 0.268 x 120 = 3.2 C.
  All TRUE. The 120 C/W is the datasheet's generic value; on this 4-layer board with planes it will be lower, so the
  estimate is conservative. The 18 V input rating also clears my round-1 concern about the TVS clamp vs the LDO
  (SMF5.0A clamps at about 9.2 V, under 18 V).
- Current budget 268 mA = 68 + 200: TRUE. One figure is now used everywhere in idea.json (Regulator, VBUS
  protection, goal), labelled as peak with continuous unknown: honest.
- 28 days on 16 GB: 16e9 / 553e6 = 28.9 days, so "about 28 days (before file-system overhead)" is TRUE at 200 Hz.
- Stock: the lowest is Y1 at 302, then BME280 758 and STM32 2,705; all 30 lines are `exact: true` (bom.json
  supply). $22.28 per board equals the sum of cost_per_board (my sum: 22.28). It is still at the 10-piece break, so
  the round-1 FRICTION stands.
- Requirements vs BOM: the goal, the Motion sensor line ("LSM6DSO ... replaces ICM-42688-P") and the Regulator line
  now match the BOM, so the round-1 WRONG is resolved. The confirmed flag still dates from 01:08 (designer C27).

## Status of my round-1 WRONG findings
1-2 (quantities, false "51 parts"): the data is fixed (52 refs), but the generic causes are untouched. 3 LSE
crystal: fixed. 4 VDDA 1 uF: fixed. 5 LDO dissipation: fixed (SOT-223, 55%). 6 IMU requirement: fixed.
7 unrequested build: it did create the Altium project (see above).
