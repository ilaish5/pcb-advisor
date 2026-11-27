# Lecturer – Stage 1 (Idea + requirements)

## Video highlights
- S1-04-third-answer.jpg | Agent says "all fixes applied", but the description still puts both sensors on I2C.
- S1-09-research-answer-end.jpg | Tool answers "unknown" for ROM DFU at 25 MHz instead of guessing: a correct refusal.
- S1-15-pin-table.jpg | SDIO pin plan PB15/PA6/PB7/PA8/PA9/PB5, checked against datasheet Table 8 and correct.
- S1-07-confirmed-next-bom.jpg | Lecturer round 1: FIX. RTC without a battery, no logging numbers, DFU unverified.
- S1-17-saved-v4-still-confirmed.jpg | Lecturer round 2: PASS with conditions. No way to re-confirm after 19 changes.

# Round 1

Evidence read: `roles/student.md` (S1), `screens/S1-01..07`, `projects/Final-E2E-4L/idea.json`, `idea-versions.json`,
`chats/2026-11-27-0103.jsonl` + `.cites.json`, `turns-log.jsonl`, `project.json`.

## What is good
- You took charge of the tool: you overrode the L432 with the F411CEU6, moved the IMU to SPI, and named the missing parts
  (W25Q128, both crystals, CC 5.1k, RESET/BOOT0, 2 LEDs). Every fix landed in `idea.json`.
- You caught the stale description paragraph yourself, before you confirmed (S1-04 against S1-05).
- The 25 MHz HSE is the right call. The F411 has no HSI48/CRS, and the ±1% HSI is not accurate enough for USB FS.
  The datasheet quote about the 48 MHz clock was checked (`cites.json`: "quote found in file").
- You checked JLC stock and price for the MCU, with a timestamp (C60420, Extended, 2705 pcs, $5.31).
- Your USB-C sink is correct: 5.1k on CC1 **and** CC2.

## Questions you must answer (round 1)
1. **Timestamps without a battery.** You wrote "USB only, no battery" and also "the 32.768 kHz LSE runs the RTC for the timestamps".
   On every unplug VBAT loses power and the RTC resets. Where does a valid time come from after each power-up? What do you do with the
   F411 VBAT pin: tie it to 3V3, add a coin cell or supercap, or take the time from the host over USB? As written, this requirement
   contradicts itself.
2. **Logging numbers.** "At a fixed rate" is not a requirement. Give the IMU ODR and full-scale range, the BME280 rate, the record size
   and the logging duration. Without those numbers nobody can say whether the SPI clock, the SD write bandwidth and the buffering are enough.
   Then tell me what the 16 MB W25Q128 is for, when you already have a microSD card. Is it a buffer, the config store, or a fallback?
   If you cannot name its job, remove it.
3. **Bus and pin plan on a 48-pin package.** The F411 has a 4-bit SDIO, so why is the SD card on SPI? If the SD card shares an SPI bus with
   the IMU and the flash, how do you deal with SD cards that keep driving MISO in SPI mode? Show a pin budget for the 36 GPIO:
   USB, SWD, HSE, LSE, IMU SPI + INT, flash CS, SD + card-detect, I2C, 2 LEDs. Do it now, not in stage 4.
4. **DFU backup, verified?** The "USB DFU via BOOT0 as backup" requirement was written for the STM32L4. The tool cited the AN2606
   **L4** tables, and the line survived the MCU swap with no new source. Show me the AN2606 entry for the STM32F411: is USB DFU supported,
   and is a 25 MHz HSE inside the frequencies the bootloader detects? Do you need PA9 (VBUS sense) for it?
5. **What you actually confirmed.** You confirmed 16 requirements. Six of them still say "(assumed)" in their own text: LDO 300 mA+,
   push-push microSD/FAT, connector edges, 4×M3 holes, JLC top-side/Basic/5 boards, ESD on D+/D- only. Which of these did you decide,
   and on what basis? In particular: what is your total current budget against the 500 mA USB default? Is there any VBUS protection
   (TVS or polyfuse), or does the ESD part cover only the data lines? And do 4 M3 holes leave room on 45×35 mm with a connector on each short edge?

## Verdict: **FIX**
The idea is coherent and the parts are sensible. But Q1 is a functional contradiction in your own goal text, and Q2/Q4 are
requirements nobody verified. Answer through the Idea chat, update the requirements (no "(assumed)" left on anything you have decided), Save, and
re-confirm.

---

## System findings (the TOOL, not the student)
- [WRONG] Contradictory requirements accepted without a warning: the RTC timestamps need a VBAT backup, but the board has no battery. Evidence: `idea.json` agreed "Power: USB-C only … no battery" plus "RTC clock: 32.768 kHz LSE for the RTC", and the goal text
  "LSE crystal runs the RTC for the timestamps". The agent wrote that sentence itself (chat 01:07:44) and never flagged it.
  Why it matters: the board will log wrong timestamps after every power cycle. Generic cause: the idea skill does not check the agreed
  items against each other (power source against RTC/VBAT, and more generally needs against provisions) before Confirm.
- [WRONG] Unsourced claim survived the MCU change. Evidence: `idea.json` "Flashing and debug … USB DFU via BOOT0 button as backup".
  Its only support was the first answer's "ST AN2606, STM32L4 bootloader tables" (chat 01:04:46). After the swap to the F411 (01:06:12)
  it was not re-checked, and no cite exists in `cites.json`. I believe the F411 ROM DFU does exist, so this is a process defect, not a
  proven false claim. Why it matters: project rule "rather refuse than be wrong". Generic cause: when an agreed item is replaced
  (MCU), the items derived from it are not re-validated or marked "unverified".
- [WRONG] Agent claimed "Updated the draft with all your fixes" while the description still contradicted the requirements. Evidence: S1-04, where the
  description still says the sensors are on I2C, "A status LED and a BOOT button", "STM32 microcontroller", next to the 16 updated
  requirements (chat 01:07:05). The student had to ask a 4th turn (S1-05). Why it matters: the goal text feeds the later stages, and a
  student who does not notice confirms a wrong goal. Generic cause: requirement edits do not regenerate or flag the `goal`
  paragraph. Reply 1 did write it (`Idea described`), replies 2–3 did not.
- [WRONG] "Confirmed" items still carry "(assumed)" in their text. Evidence: `idea-versions.json` v2 "42 changes saved", where all 16 are
  `status: confirmed, by: agent`, and 6 still contain "(assumed)" (Regulator, Storage, Connectors, Board holes, Assembly, ESD).
  Why it matters: later stages cannot tell a real decision from a guess, so the data contradicts itself. Batch accept is what the owner wants,
  but the gate should either strip the marker or say "6 assumptions are still open, accept them as they are?" in one click. Generic
  cause: Save/Confirm promotes drafts without looking at the assumed marker.
- [FRICTION] The requirements cannot be seen at the moment of confirmation. Evidence: S1-02/03/04 show one requirement row ("Power") in a
  small scroll box above a large diagram. In S1-06/07 no requirement row is visible at all when Confirm idea is pressed. Why it matters:
  the student confirms 16 items he never sees on screen. Generic cause: the Idea page layout gives the diagram priority over the list.
- [FRICTION] Draft and saved state disagree on layers. Evidence: S1-03, where the 4-layer requirement is in the draft but "Copper layers 2"
  is still shown, and the diagram frame says 2-layer until Save (student log). Why it matters: a student can believe 4 layers is set when
  the project setting is 2. Generic cause: `project.json` board.layers is only written on Save, and the draft does not show it as pending.
- [FRICTION] Cost and latency per small edit. Evidence: `turns-log.jsonl` shows about 316k input tokens and about $0.49 per turn even for
  "rewrite the description" (77k tokens, $0.38, 10 s). The other turns took 30–55 s. Stage 1 cost about $1.86 for 4 turns. Generic cause: the full project and
  skill context is reloaded every turn.
- [COSMETIC] The diagram contradicts the requirements. Evidence: `idea.json` block `swd` role "Debug (optional)" against the agreed item "SWD header …
  (main)". The `mcu` block still says "STM32 (MCU)", not F411CEU6. The only 3.3 V connector goes to the MCU, while the IMU, BME280, SD and flash
  get no power line. Generic cause: block text is not regenerated from the agreed items.

Good tool behaviour worth keeping: the first draft marked every guess "(assumed)" and the L432 "unverified – check". The datasheet quote was
verified automatically. The JLC stock line had a source and a timestamp. The chat answers were short with one "Next:" step.

---

# Round 2 (last)

Evidence: `roles/student.md` section "Answers to lecturer S1", `roles/student-confusions.md` C16–C28, `screens/S1-08..17`,
`projects/Final-E2E-4L/idea.json` (version 4, saved 01:26:48, 19 requirements), and `sources/STM32F411CEU6.pdf.txt`
(I checked it myself).

## Answers checked
1. **RTC / VBAT: answered.** VBAT is tied to 3V3 and there is no coin cell. The PC sets the time over USB after each plug-in. This matches the datasheet
   ("VBAT pin should be connected to VDD", `STM32F411CEU6.pdf.txt:1085`). You admitted the weakness yourself. Accepted as a design decision.
2. **Logging numbers: answered.** 200 Hz, ±8 g, ±1000 dps, BME280 at 1 Hz, 32 B records. 6.4 kB/s and 553 MB/day are correct.
   The flash now has a job: config, calibration and a no-card buffer. Wording problem, see condition C3.
3. **Bus and pins: answered, and verified.** You moved the SD card to 4-bit SDIO, which removes the shared-MISO problem. I checked the pin table against Table 8 of the datasheet:
   SDIO_CK=PB15 (28), CMD=PA6 (16), D0=PB7 (43), D1=PA8 (29), D2=PA9 (30), D3=PB5 (41) are all correct. SPI1 is on PA5/PB4/PA7, I2C1 on
   PB8/PB9, and there are no collisions among the listed pins. PA9 as SDIO D2, so no VBUS sensing, is a sound trade-off for a bus-powered board.
4. **DFU: honestly marked as unverified.** "USB DFU via BOOT0 as backup (unverified: AN2606 not read)" is the right answer when the source
   cannot be read. SWD is the main path, so DFU does not block anything.
5. **Assumptions: decided.** No "(assumed)" is left in `idea.json`. The polyfuse and TVS on VBUS are added. The 175 mA budget against 500 mA is a stated
   estimate. The mechanical fit (about 21 mm free per short edge) is a planning number that must be re-checked at placement.

## Verdict round 2: **PASS with conditions** (carried into stage 2 and later)
- **C1 (S4 schematic):** BOOT1 = PB2 (pin 20, Table 8 "PB2 … BOOT1") must be held low for the BOOT0 system-memory boot. PB2 is
  missing from your pin table. Add a pull-down. Also check in AN2606, once someone uploads it, whether the bootloader needs a defined level on PA10
  (USART1_RX); this is unverified.
- **C2 (S4):** SDIO needs pull-ups on CMD and D0–D3 (not on CK), and card-detect needs a pull-up or the internal one. Put them on the schematic.
- **C3 (now, a one-line text fix):** "24 h on a 16 GB card" reads as if 16 GB lasts 24 h. At 553 MB/day, 16 GB lasts about 29 days.
  State the target duration instead. Also note that the 16 MB flash buffer covers only about 43 min at 6.4 kB/s.
- **C4 (S2 BOM):** Redo the current budget from the real datasheets once the parts are chosen. Choose the LDO for 300 mA or more, with dropout checked at
  5 V minus the polyfuse drop, and dissipation of (5−3.3)×0.175 ≈ 0.3 W checked against the package θJA.
- **C5 (S2):** The firmware must mark records as "time not set" when the board runs from a charger with no host. Accepted, but write it down.

---

## System findings, round 2 (new)
- [FRICTION] The confirmation is not invalidated by later edits, and the agent's instruction does not match the page. Evidence: `idea.json`
  `confirmed_at: 01:08:13`, but version 4 with 19 changes was saved at 01:26:48. The page still shows "confirmed 27 Nov 2026" and "Next: BOM", with no Confirm
  button (S1-17). The agent still says "press Save, then Confirm idea" and, in the same reply, "pressing Save confirms them too" (C27, C28).
  Why it matters: later stages trust a confirmation that is older than the content, and the student cannot tell which version is
  approved. Generic cause: the confirmed flag is not reset or re-offered after edits. The skill's "Next:" line is fixed text and does not
  depend on the page state.
- [FRICTION] The tool sends the student for a document it cannot fetch, and the failure is silent. Evidence: the agent says AN2606 "timed out twice" and
  tells the student to put it into sources (S1-09, S1-10). Sources → From URL with the same link spins for about 70 s and then vanishes. The error text
  exists only in the DOM, nothing is visible on screen (S1-12, C20, C21). Why it matters: the one source needed to verify DFU never arrives, and the student does not know.
  Generic cause: the URL-fetch failure is not surfaced, and there is no "upload the PDF yourself" fallback hint. (Good part: the agent said
  "unknown" instead of guessing. Keep that.)
- [FRICTION] The guard reverts edits the agent did not make. Evidence: S1-09 has a red box, "the agent edited system files … they were restored",
  and the files were the student's own note and screenshot, written while the turn ran (C19). They were deleted from disk. Why it matters:
  user data is lost and the message blames the wrong actor. This was triggered by the test harness writing into the repo, but generic cause: the post-turn diff guard attributes every repo
  change made during a turn to the agent.
- [FRICTION] A pin was changed between two answers without saying so. Evidence: S1-09 has SDIO D0=PB4 (40), and S1-15 has D0=PB7 (43). Both are valid
  per Table 8 (PB4 and PB7 both carry SDIO_D0), and the change is right (it frees PB4 for SPI1_MISO), but no "I changed D0 from PB4"
  note was given (C24). Why it matters: the student cannot tell whether this is a correction or a mistake. Generic cause: no diff against earlier claims in
  the session.
- Status of the round-1 findings: the RTC contradiction was fixed only because the lecturer asked, and the tool never raised it itself (stands). DFU is now honestly
  "unverified" (handled well once asked). The description was regenerated together with the requirements this time (improved).
  The "(assumed)" markers are gone, but the student had to ask for the last two to be removed (S1-17). The MCU block still says "STM32 (MCU)"
  and not F411CEU6 (COSMETIC, still open). The SWD block is fixed.
- Watch at S4 (engineer/Alti): whether the schematic step adds the PB2/BOOT1 pull-down and the SDIO pull-ups without being asked.
  The idea-stage pin table omitted PB2 even though it was built for BOOT0 DFU entry.
