# Engineer review, Stage 1 (Idea + requirements)

## Video highlights
- S1-03-second-answer.jpg | Agent says "Updated the draft" but the description still says I2C and USB DFU flashing.
- S1-09-research-answer-end.jpg | Guard blames the agent and reverts the student's own notes: data loss.
- S1-15-pin-table.jpg | All 29 pins match the datasheet, but BOOT1 (PB2) for DFU is missing.
- S1-17-saved-v4-still-confirmed.jpg | Eleven requirements changed in v4, yet the idea still reads "confirmed".

Reviewed: screens S1-01..S1-07, roles/student.md, projects/Final-E2E-4L/{idea.json, project.json, turns-log.jsonl,
usage-log.jsonl, chats/2026-11-27-0103.jsonl + .cites.json, sources/STM32F411CEU6.pdf(.txt)} (DocID026289 Rev 4).
Engine: Claude Code CLI / Opus. 4 chat turns, 16 requirements, confirmed 01:08:13.
Scope (PROTOCOL "Who judges what"): (1) did the system do what the student asked, (2) is what it produced or claimed correct.

## Verdict
(1) Every student request was implemented in the requirement list: MCU, layers, size, SWD, SPI IMU, I2C BME280,
flash, both crystals, LEDs, buttons, CC resistors. The description and one diagram label were not updated, and the
agent did not say so. (2) No hallucinations: every number and quote traces to a tool result or the datasheet. The
requirements the system wrote itself are sound, but two are thin.

## System findings

- [WRONG] The description paragraph went stale twice and the agent did not say so: after turn 2 (MCU, layers, SWD)
  and turn 3 (SPI IMU, flash, crystals, LEDs) the agent answered "Updated the draft..." while the top paragraph still
  said "An STM32 ... over I2C ... the same USB port loads the firmware (USB DFU). A status LED and a BOOT button"
  (S1-03-second-answer.jpg; student.md "noticed: top description paragraph still says both sensors on I2C"). That
  contradicts what the student asked: SWD as the main flashing path and the IMU on SPI. It was fixed only when the
  student asked (turn 4, `idea.describe`, S1-05). Generic cause: `idea.propose` and `idea.diagram.edit` do not trigger
  a description refresh or a description-vs-requirements check (turns-log applied lists at 01:06:12 and 01:07:05 have
  no `idea.describe`).
- [WRONG] A diagram label contradicts the student's request: the block `swd` still reads "SWD header / Debug
  (optional)" (idea.json diagram shape `swd`, S1-07-confirmed-next-bom.jpg), while the student said "I have an
  ST-Link so keep the SWD header", and the requirement became "(main)". The agent's turn-3 claim "The diagram now shows
  the flash and the RTC crystal" is true, but it missed this stale label. Same generic cause: no
  diagram-vs-requirements consistency check before Confirm idea.
- [FRICTION] The regulator requirement, written by the system, sizes current but not heat: "SD writes need roughly
  100 mA peaks, so pick a 300 mA+ LDO" (idea.json `Regulator`). The 300 mA+ figure is reasonable: my estimate of the
  peak is about 150-200 mA (F411 at 96 MHz, SD write, flash program, 2 LEDs). But at 5 V in and 3.3 V out that is
  about 0.34 W, which in a SOT-23-5 means a 70-85 C rise. The requirement says nothing about package or dissipation,
  so the BOM stage can legally pick a part that runs hot.
- [FRICTION] The ESD requirement, written by the system, covers only D+/D- ("ESD protection diodes on USB D+/D-
  (assumed)"). Nothing is said about VBUS (TVS, polyfuse) or the CC lines on a connector the user plugs in and out.
  This is acceptable for a hobby board, but it was the system's own default and it was never put to the student.
- [COSMETIC] Six requirements are status "confirmed" but their text still ends with "(assumed)": Regulator, Storage,
  Connectors, Board ("holes assumed"), Assembly, ESD (idea.json `agreed`). After Confirm idea, a reader cannot tell
  which were really decided.
- [COSMETIC] Diagram: the ESD block is coloured as `power` domain (it sits on the USB data lines), the 3.3 V rail is
  drawn only to the MCU (not to the IMU, BME280, SD and flash), and the MCU block says "STM32 (MCU)", not F411CEU6
  (idea.json shapes `esd`, `mcu`, connector `conn_4`).

## Claims checked (all TRUE)
- "The F411's USB needs 'a dedicated 48 MHz clock'": TRUE (datasheet txt line 1530; cites.json ok). "So I added an
  external crystal" is correct: the F411 has no HSI48/CRS, and the 16 MHz HSI (about 1%) is too coarse for USB FS.
- HSE "4-26 MHz": TRUE (txt line 23). The first proposal "e.g. 8 MHz" was valid.
- 25 MHz HSE gives an exact 48 MHz: TRUE. From Table 41 (fPLL_IN 0.95-2.10 MHz, VCO 100-432 MHz): M=25, N=192, Q=4
  gives 48.000 MHz, and P=2 gives SYSCLK 96 MHz. With exact 48 MHz USB the F411 maxes out at 96 MHz for any common
  crystal, so this is not an error.
- JLC C60420 = STM32F411CEU6: TRUE. turns-log 01:05:27 `jlc.py part`: mpn STM32F411CEU6, UFQFPN-48(7x7), exact,
  stock 2705, 1-9 at $5.314, Extended. The chat figures match exactly, and the datasheet came from the C60420 LCSC URL.
- USB DFU backup on the F411: consistent with the system table (mcu-bootloaders.json "STM32F411 ... USB DFU", AN2606).
  That the ROM DFU accepts a 25 MHz HSE is from my memory of AN2606, not checked against a local copy.
- Turn-1 "STM32L432 (unverified - check)": honestly marked unverified, and it matches the system table.
- "frame says 4-layer": TRUE. project.json `board.layers: 4`, board 45 x 35.
- 5.1k Rd on CC1 and CC2 separately: correct for a USB 2.0 sink.

## For the lecturer (student decisions, not system findings)
- "W25Q128" with no suffix: the 3 V part is W25Q128JV; FW and JW are 1.8 V parts. The student should pin the
  suffix. If the BOM stage picks a 1.8 V part without warning, that becomes a system finding in S2.

## My S2 checklist (datasheet-mandated parts the BOM must produce)
VCAP_1 4.7 uF, ESR < 1 ohm (Table 16); one 4.7 uF plus 100 nF per VDD pin (txt ~3414); VDDA 1 uF // 10 nF (txt ~6418);
BOOT0 pull-down; PB2/BOOT1 held low (txt 2350); NRST 100 nF; HSE and LSE load caps computed from each crystal's CL;
LDO package and dissipation; W25Q128 suffix and voltage.

---

# Round 2 (screens S1-08..S1-17, chat 01:16-01:26, idea.json v4)

Checked against sources/STM32F411CEU6.pdf (DocID026289 Rev 4), extracted text: Table 8 pin definitions (UFQFPN48 column),
section 3.13 Boot modes, Table 25, the 6.3 USB OTG FS note, and Table 37.

## Verdict
The datasheet answers are correct, and every citation points at the right table or section. All 29 pin assignments
in the pin table exist in the 48-pin package with the stated function and pin number. The agent was honest about
what it could not verify: DFU with 25 MHz and the PA9 need were reported as unknown because AN2606 could not be
fetched. There are two system errors. A guard reverted the student's own files and blamed the agent. The pin plan
for the DFU backup misses BOOT1 (PB2) and ignores the bootloader pins it reuses, although the agent quoted the very
section that lists them.

## System findings (round 2)

- [WRONG] The tool guard reverts files the agent did not write and blames the agent. The chat ended with "the agent
  edited system files: docs/e2e-2026-11-27/roles/student-confusions.md, .../S1-08-research-wait.jpg; they were
  restored" (chat 01:19:25, S1-09). Both files were written by the student during the turn, and the student found
  entry C18 and the screenshot deleted (student-confusions.md C19). Cause: scripts/tool_guard.py `snapshot()` at turn
  start, then `restore()` on any repo file whose bytes differ at turn end. It writes back the old bytes, or
  `git rm --cached` + `unlink` for files that are new or untracked (tool_guard.py ~155-171). It has no way to tell
  who changed a file, and `refusal()` (~239) always says "the agent edited". This is a false claim in chat and a
  data-loss path for any file edited in the install while an agent turn runs. The trigger here was the test setup
  (notes kept in the repo), but the mechanism is generic. The designer filed the wording (designer-S1 C19); the data
  loss is the engineering part.
- [WRONG] The pin plan supports "USB DFU via BOOT0 as backup" but leaves BOOT1 (PB2) undefined. The F411 picks
  system memory only with BOOT0=1 and BOOT1=0 (datasheet Table 8: "20 ... PB2 ... BOOT1"). The table lists
  "RESET / BOOT0" only (chat 01:25:16, S1-15), and PB2 (pin 20) is neither assigned nor tied low. At reset PB2 is a
  floating input, so the BOOT0 button can boot from SRAM instead of the ROM bootloader. It needs a pull-down or a tie
  to GND. The system should have added it unasked, because the student asked for a DFU backup via BOOT0.
- [FRICTION] (missed warning) The pin plan puts board signals on pins the ROM bootloader scans. The agent quoted
  section 3.13 itself ("using USART1(PA9/10) ... I2C1(PB6/7), I2C3(PA8/PB4), SPI1(PA4/5/6/7) ...", datasheet txt
  ~1024), and its plan then uses PA9 (SDIO D2), PA8 (D1), PB7 (D0), PB4 (SPI1 MISO), PA4/5/6/7 (IMU CS, SCK, SDIO CMD,
  MOSI) for other devices, with PA10 (USART1 RX) left floating. Activity or noise on a scanned interface can make the
  bootloader pick it instead of USB DFU. DFU is labelled "unverified", so this is not a false claim, but the reason
  for the risk was in the agent's own quote and it said nothing. Fix direction: the pin-plan step should cross-check
  assignments against the MCU's bootloader pin list when DFU is a requirement.
- [FRICTION] The confirmed flag does not follow content. idea.json still has `confirmed: true, confirmed_at
  2026-11-27T01:08:13` while version 4 was saved at 01:26:48 with 3 new and 8 changed requirements
  (idea-versions.json). Later stages will treat requirements the student never confirmed as confirmed. The agent also
  told the student "press Save ... then Confirm idea", a button the page no longer offers (S1-17). The UI side is
  designer-S1 C27/C28; the data side matters for the BOM stage.
- [COSMETIC] SDIO D0 changed between answers (PB4 at 01:19 to PB7 at 01:25), but technically both are correct:
  Table 8 has SDIO_D0 on PB4 (pin 40) and on PB7 (pin 43), and the second answer gave the reason ("so that PB4 is
  free for SPI1 MISO"). The first answer presented one option as "the pins" without saying D0 has two choices. So C24
  is not a technical error.
- [COSMETIC] The diagram MCU block still reads "STM32 (MCU)" (idea.json shape `mcu`). The round-1 SWD label is fixed
  ("Main flashing (ST-Link)"), and so are the "(assumed)" tags.

## Claims checked (round 2)
- 4-bit SDIO on UFQFPN48: TRUE. Table 8, UFQFPN48 column: PB15 (28) SDIO_CK, PA6 (16) SDIO_CMD, PB4 (40) or PB7 (43)
  SDIO_D0, PA8 (29) SDIO_D1, PA9 (30) SDIO_D2, PB5 (41) SDIO_D3.
- "D2 can only go on PA9; the other D2 pin, PC10, isn't in that package": TRUE (PC10 row has "-" in the UFQFPN48 column).
- PA9 is SDIO_D2 on the F411: TRUE (PA9 row: TIM1_CH2, I2C3_SMBA, USART1_TX, USB_FS_VBUS, SDIO_D2).
- Every other pin in the table: TRUE for function and number. PA11/PA12 = 32/33 (D-/D+), PA13 = 34 SWDIO, PA14 = 37
  SWCLK, PB3 = 39 JTDO-SWO, PH0/PH1 = 5/6, PC14/PC15 = 3/4, VBAT = 1, PA5 = 15 SPI1_SCK, PB4 = 40 SPI1_MISO,
  PA7 = 17 SPI1_MOSI, PA4 = 14, PB0 = 18, PB1 = 19, PB12 = 25, PB8/PB9 = 45/46 I2C1_SCL/SDA, PB13/PB14 = 26/27,
  NRST = 7, BOOT0 = 44. No pin is assigned twice.
- "USB DFU in ROM: yes" with the 3.13 quote: TRUE (txt ~1024, verbatim).
- "HSE 4-26 MHz, Table 37": TRUE (Table 37 "HSE 4-26 MHz oscillator characteristics").
- PA9 note: TRUE. 6.3 USB OTG FS note: "When VBUS sensing feature is enabled, PA9 should be left at their default
  state (floating input)". The fix (no VBUS sensing on a bus-powered board, PA9 as D2) is professionally correct for
  the application. For the ROM DFU it is unknown, as the agent said.
- "MCU at most 35.5 mA at 100 MHz with all peripherals on (Table 25)": TRUE. Table 25, external clock, PLL on, all
  peripherals, 100 MHz, max at 105 C = 35.5 mA (typ 31.7). It is the worst case, and the board will run at 96 MHz, so
  this is conservative.
- Current budget "about 175 mA, around 35% of 500 mA": the arithmetic is TRUE (35.5 + 100 + 25 + 10 + 2 = 172.5 mA).
  The non-MCU figures are labelled typical and unverified, honestly. A 500 mA hold polyfuse and a 5 V TVS are sound
  for a 500 mA USB 2.0 sink. Note for S2: pick a TVS with standoff (VRWM) at or above 5.25 V (USB 2.0 VBUS max) so it
  does not leak at high VBUS.
- "About 21 mm free on each short edge" with 7 mm per corner: TRUE as arithmetic (35 - 2 x 7 = 21). The 7 mm is
  plausible: the hole centre is 3.5 mm in (idea.json constraints h1: 3.2 mm hole, inset 3.5) plus an M3 head radius of
  about 3 mm plus margin. A USB-C 2.0 receptacle (about 9 mm) and a push-push microSD slot (about 14-15 mm) fit. The
  wording "7 mm keep-out around each hole" reads like a radius, which would leave only 14 mm; the number is right but
  the phrase is ambiguous. It is correctly labelled "planned", to be checked at placement.
- Logging math: TRUE. 200 Hz x 32 B = 6.4 kB/s; x 86400 s = 553 MB/day; fits 16 GB.

## Updated S2 checklist (adds to round 1)
PB2/BOOT1 pull-down; pull-ups on SDIO CMD and D0-D3 (SD spec, roughly 10-100k); VBAT 100 nF to the 3V3 tie; TVS VRWM
at or above 5.25 V; PA10 not left floating if DFU is kept (pull-up or pull-down).
