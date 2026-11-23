# Brain eval compare - 2026-11-23/24

Branch **claude/brain-slim**, final tip **843df66**, against the baseline 148e137 (`docs/BRAIN-EVAL-BASELINE-2026-11-23.md`).
The order follows the student's request: answer quality first, then rule violations, tool turns, time per answer, and tokens.

## Verdict
- **Quality: the same.** The final state answers as well as 148e137 on claude_code:
  - blind A/B 12:13 with 5 ties;
  - mean judge score 4.58 vs 4.61;
  - rule violations 6 vs 6;
  - QA eval mean 0.832 over 4 runs (0.810 before);
  - behaviour 9.25 / 13 (9.0 before);
  - incidents 12/12.
  - antigravity on the final state: **pending** (agy hit its daily quota during the final runs; the run is scheduled after the reset and this doc gets its numbers then). With P1, antigravity's q-set judge was within noise (12:10:8, 4.64 vs 4.61, violations 5 vs 5) but its bench regressed on a stable case (b03).
- **Two cuts made quality worse and were reverted:**
  - **P1** (AGENTS.md only through CLAUDE.md): QA cite 0.69 to 0.44-0.51; blind A/B 6:19; rule slips. It also hurt antigravity (b03 mpn_guard failed in both runs; it passed in both before).
  - **P2** (WORKSPACE without the script commands): fewer checks run, less grounded answers; blind A/B 7:18 with P1 already reverted, 12:13 once P2 was also reverted.
- **Kept:**
  - cut 3 (AGENTS.md trim);
  - cut 4 (skill descriptions);
  - cut 5 (skill bodies, S9-S16 fixes);
  - P3 (short follow-up/retry round).
- **Tokens: small.** A one-turn chat message costs about 660 fewer input tokens on claude_code (71.9k to 71.2k, -0.9%). The follow-up/retry prompt is 10% shorter (51.1k to 46.1k chars).
  The big savings were P1 (about -13k tokens a turn) and P2 (-2.2k), and they cost quality. Overall: no improvement in quality, no loss, and a small saving.

## 1. Cuts kept and dropped

| commit | cut | measured effect | verdict |
|---|---|---|---|
| 8d379a1 | P1: AGENTS.md reaches the engine once (prompt carries a pointer) | stdin -30k chars; claude_code QA cite 0.69 to 0.44-0.51, A/B 6:19, engine read/grepped AGENTS.md 7-9 times a run; agy b03 regressed | **reverted** (3120848) |
| 531d555, 22ad615 | P2: WORKSPACE keeps paths only; script catalog only in AGENTS.md SCRIPTS | stdin -3.4k chars; claude_code 13-14 tool calls on the q-set against 17-30, A/B 7:18 | **reverted** (843df66) |
| b416085 | Cut 3: AGENTS.md trim, THE THREE STAGES -> WORK ORDER (7 stages), the draw/place/route line split into bullets (consent wording verbatim) | AGENTS.md 30351 to 27999 chars (-7.7%) | kept |
| 738aeb5 | Cut 4: skill descriptions, overlaps removed (S15) | 6048 to 4352 chars (-28%) | kept |
| b6aa2eb, 635215f | Cut 5: skill bodies: AGENTS.md duplicates and dead text out (S13, S16); S9-S12, S14 fixed | 97302 to 92654 chars over 12 skills (-4.8%) | kept |
| caa4e35 | P3: follow-up/retry round sends the last exchange, not the conversation window | retry prompt 51137 to 46087 chars; q13 retry blocks correct in every sample | kept |

AGENTS.md ended at 27999 chars, about 8% shorter, not the 25% asked for. HARD RULES, CITING, every consent sentence and the
script catalog stay word for word. The catalog is still the only list of commands the engine runs, and P2 showed it is needed.

## 2. Answer quality: blind A/B on the 15-question set
Method:
- The same 15 student messages (baseline doc section 2), on a fresh copy of the same project state, 2 samples per question per side.
- An Opus judge saw each pair with before/after shuffled and hidden.
- It scored 1-5 on correctness, hard rules, action shape, next step, and language+length, listed each violation with a quote,
  and picked a preference.
- Noise control: the same judge on baseline rep 1 against baseline rep 2 (same version on both sides).

### Final vs before, claude_code (843df66, the same tree as bisect state "bisB")
One final answer (q04, rep 2) was an engine timeout while the machine was loaded; the judge scored it 1 on every criterion, and it is counted against the final state.
#### `bisB-cc` (30 pairs)
| side | correct | rules | action | next_step | lang_len | mean | preferred | violations |
|---|---|---|---|---|---|---|---|---|
| after | 4.50 | 4.63 | 4.63 | 4.60 | 4.53 | 4.58 | 12 | 6 (other 4, language 1, source 1) |
| before | 4.60 | 4.50 | 4.80 | 4.70 | 4.47 | 4.61 | 13 | 6 (source 3, other 2, position 1) |
| tie | | | | | | | 5 | |

| question | after | before | tie |
|---|---|---|---|
| q01-idea | 0 | 2 | 0 |
| q02-stock | 1 | 1 | 0 |
| q03-sch-review | 0 | 2 | 0 |
| q04-nc | 0 | 2 | 0 |
| q05-accept-pins | 1 | 1 | 0 |
| q06-placement | 1 | 1 | 0 |
| q07-trace | 1 | 1 | 0 |
| q08-drc | 1 | 1 | 0 |
| q09-gerbers | 1 | 1 | 0 |
| q10-place-consent | 0 | 1 | 1 |
| q11-self-draw | 2 | 0 | 0 |
| q12-datasheet | 2 | 0 | 0 |
| q13-retry | 0 | 0 | 2 |
| q14-why-he | 0 | 0 | 2 |
| q15-next-en | 2 | 0 | 0 |

Violations, after:
- q01-idea: other: משנה חמש דברים (gender agreement error)
- q03-sch-review: language: Sheet 02 is mostly fine, with two open points.
- q04-nc: source: SBU1 and SBU2 are the sideband pins for alternate modes such as DisplayPort.
- q01-idea: other: חיישן אור משנה ארבעה דברים (lists three)
- q02-stock: other: The 2 Extended parts (the ones with a setup fee)
- q04-nc: other: The agent stopped answering (no output for 180s)
Violations, before:
- q03-sch-review: source: הנחיות החומרה של ESP32-C3 באתר Espressif מפרטות את זה
- q06-placement: other: I'm proposing it, plus the edge placement, as constraints (says two, emits three actions)
- q07-trace: other: "net": "VBUS" (project net is +5V; action not mentioned in the reply)
- q08-drc: source: It is also a fine-pitch footprint, so it's expected to trip the DRC, and JLC can still mak
- q06-placement: position: The LDO (U3) is on the input side by the USB-C connector
- q08-drc: source: If the gap is below 0.152 mm, JLC cannot make it

### Noise control (same version on both sides)
A difference between versions counts only beyond this: the preference split, a mean gap of about 0.25-0.28, and 2 to 9 violations per run.
#### `ctl-cc` (15 pairs)
| side | correct | rules | action | next_step | lang_len | mean | preferred | violations |
|---|---|---|---|---|---|---|---|---|
| qbefore-cc-1 | 4.27 | 4.07 | 4.80 | 4.47 | 4.13 | 4.35 | 5 | 9 (source 4, other 3, promise 2) |
| qbefore-cc-2 | 4.47 | 4.53 | 4.93 | 4.73 | 4.33 | 4.60 | 9 | 2 (position 1, other 1) |
| tie | | | | | | | 1 | |

| question | qbefore-cc-1 | qbefore-cc-2 | tie |
|---|---|---|---|
| q01-idea | 1 | 0 | 0 |
| q02-stock | 0 | 1 | 0 |
| q03-sch-review | 0 | 1 | 0 |
| q04-nc | 1 | 0 | 0 |
| q05-accept-pins | 0 | 1 | 0 |
| q06-placement | 1 | 0 | 0 |
| q07-trace | 0 | 1 | 0 |
| q08-drc | 0 | 1 | 0 |
| q09-gerbers | 1 | 0 | 0 |
| q10-place-consent | 0 | 1 | 0 |
| q11-self-draw | 0 | 1 | 0 |
| q12-datasheet | 0 | 1 | 0 |
| q13-retry | 0 | 0 | 1 |
| q14-why-he | 0 | 1 | 0 |
| q15-next-en | 1 | 0 | 0 |

Violations, qbefore-cc-1:
- q03-sch-review: source: הנחיות החומרה של ESP32-C3 באתר Espressif מפרטות את זה
- q03-sch-review: other: ה-datasheet שלנו בסינית והטקסט שלו לא קריא (unsupported claim about the source file)
- q07-trace: source: זה נמוך ממינימום הלוח שלך (0.2 מ"מ)
- q07-trace: other: net.set_current on "VBUS" while the netlist net is +5V, and the reply never mentions the c
- q08-drc: source: so it's expected to trip the DRC, and JLC can still make it
- q08-drc: promise: If you pick the second, I'll propose it as a card.
- q10-place-consent: promise: If you say yes, I'll place the parts again
- q11-self-draw: source: ל-J1 חבר לפי הנטליסט של דף 01 (no project read this turn)
- q13-retry: other: student_said: "תצייר אתה את דף 01 ב-Altium" (not found in the visible student messages)
Violations, qbefore-cc-2:
- q06-placement: position: The LDO (U3) is on the input side by the USB-C connector
- q13-retry: other: student_said: "תצייר אתה את דף 01 ב-Altium" (not found in the visible student messages)
#### `ctl-ag` (15 pairs)
| side | correct | rules | action | next_step | lang_len | mean | preferred | violations |
|---|---|---|---|---|---|---|---|---|
| qbefore-ag-1 | 4.67 | 4.80 | 4.87 | 4.47 | 4.73 | 4.71 | 6 | 2 (source 2) |
| qbefore-ag-2 | 4.53 | 4.33 | 4.73 | 4.20 | 4.33 | 4.43 | 3 | 6 (source 4, other 2) |
| tie | | | | | | | 6 | |

| question | qbefore-ag-1 | qbefore-ag-2 | tie |
|---|---|---|---|
| q01-idea | 1 | 0 | 0 |
| q02-stock | 0 | 0 | 1 |
| q03-sch-review | 0 | 1 | 0 |
| q04-nc | 1 | 0 | 0 |
| q05-accept-pins | 1 | 0 | 0 |
| q06-placement | 1 | 0 | 0 |
| q07-trace | 1 | 0 | 0 |
| q08-drc | 0 | 1 | 0 |
| q09-gerbers | 0 | 0 | 1 |
| q10-place-consent | 0 | 0 | 1 |
| q11-self-draw | 0 | 0 | 1 |
| q12-datasheet | 1 | 0 | 0 |
| q13-retry | 0 | 0 | 1 |
| q14-why-he | 0 | 0 | 1 |
| q15-next-en | 0 | 1 | 0 |

Violations, qbefore-ag-1:
- q04-nc: source: `SBU1` (A8) and `SBU2` (B8) are Sideband Use pins for alternate modes (such as DisplayPort
- q08-drc: source: shrink `SolderMaskExpansion` on J1's pads (`<= 0.024 mm`)
Violations, qbefore-ag-2:
- q01-idea: source: חיישן אנלוגי ידרוש פין `ADC` פנוי ב-{{ref:U1}}
- q04-nc: source: They are USB-C Sideband Use pins for alternate modes
- q05-accept-pins: other: הפינים של {{ref:U1}}, {{ref:U2}}, {{ref:U3}}, {{ref:U4}}, {{ref:J1}} ו-{{ref:D1}} כבר מסומ
- q06-placement: other: idea.constrain add keep_apart U2/U3 min_mm 15 emitted for a pure question without the stud
- q06-placement: source: practice is to maximize separation (aim for ≥15 mm)
- q07-trace: source: ברירת המחדל המוגדרת בלוח: `0.203 מ"מ` / `8 mil`

### Per criterion: pairs where after scored higher / equal / lower (w/t/l)
| ctl-cc | 6/5/4 | 7/7/1 | 1/14/0 | 5/8/2 | 5/8/2 |
| ctl-ag | 1/12/2 | 1/8/6 | 0/14/1 | 1/9/5 | 0/9/6 |
| ab-cc | 3/15/12 | 3/16/11 | 1/18/11 | 7/19/4 | 8/20/2 |
| ab-ag | 5/21/4 | 7/19/4 | 2/27/1 | 5/19/6 | 1/24/5 |
| fin-cc | 4/21/5 | 7/16/7 | 2/27/1 | 2/19/9 | 7/17/6 |
| bisB-cc | 5/21/4 | 9/18/3 | 2/24/4 | 4/22/4 | 9/17/4 |

### Dropped states (for the record)
All cuts with P1 and P2, claude_code (`ab-cc`):
#### `ab-cc` (30 pairs)
| side | correct | rules | action | next_step | lang_len | mean | preferred | violations |
|---|---|---|---|---|---|---|---|---|
| after | 4.23 | 4.20 | 4.13 | 4.50 | 4.67 | 4.35 | 6 | 9 (other 3, source 2, pins 2, language 1, promise 1) |
| before | 4.70 | 4.77 | 4.93 | 4.40 | 4.37 | 4.63 | 19 | 2 (other 1, position 1) |
| tie | | | | | | | 5 | |

| question | after | before | tie |
|---|---|---|---|
| q01-idea | 0 | 2 | 0 |
| q02-stock | 0 | 2 | 0 |
| q03-sch-review | 0 | 2 | 0 |
| q04-nc | 2 | 0 | 0 |
| q05-accept-pins | 0 | 2 | 0 |
| q06-placement | 0 | 2 | 0 |
| q07-trace | 1 | 1 | 0 |
| q08-drc | 0 | 2 | 0 |
| q09-gerbers | 0 | 2 | 0 |
| q10-place-consent | 0 | 2 | 0 |
| q11-self-draw | 1 | 0 | 1 |
| q12-datasheet | 1 | 1 | 0 |
| q13-retry | 0 | 1 | 1 |
| q14-why-he | 0 | 0 | 2 |
| q15-next-en | 1 | 0 | 1 |

Violations, after:
- q03-sch-review: source: בדקתי את דף 02 מול טבלת הפינים ב-datasheet ... מספרי הפינים תואמים: 3V3=3, EN=8
- q03-sch-review: language: לוודא שהשארתם פתוחים בסדר
- q05-accept-pins: other: אני לא יכול לאשר פינים בלי מקור ... ולהגיד לי אם הם תואמים
- q10-place-consent: promise: I'm placing the netlist parts on the PCB now
- q10-place-consent: other: did not ask before replacing an already placed and routed board
- q13-retry: pins: "pins_source": "student" (U4 and U3)
- q13-retry: other: netlist.write for sheet 01 added though the refusal named only the library
- q03-sch-review: source: IO2 ו-IO8: נראה שמותר להשאיר אותם פתוחים (floating)
- q05-accept-pins: pins: הפינים של USBLC6 מאומתים מתרשים הפינאוט בטקסט ה-PDF
Violations, before:
- q07-trace: other: "net": "VBUS" (the netlist net is +5V)
- q06-placement: position: The LDO (U3) is on the input side by the USB-C connector
All cuts with P1 and P2, antigravity (`ab-ag`: within the noise on the q-set, but see the bench below):
#### `ab-ag` (30 pairs)
| side | correct | rules | action | next_step | lang_len | mean | preferred | violations |
|---|---|---|---|---|---|---|---|---|
| after | 4.63 | 4.70 | 4.83 | 4.53 | 4.50 | 4.64 | 12 | 5 (other 3, source 2) |
| before | 4.53 | 4.50 | 4.77 | 4.60 | 4.63 | 4.61 | 10 | 5 (source 3, other 2) |
| tie | | | | | | | 8 | |

| question | after | before | tie |
|---|---|---|---|
| q01-idea | 2 | 0 | 0 |
| q02-stock | 1 | 1 | 0 |
| q03-sch-review | 0 | 2 | 0 |
| q04-nc | 2 | 0 | 0 |
| q05-accept-pins | 1 | 1 | 0 |
| q06-placement | 1 | 1 | 0 |
| q07-trace | 1 | 0 | 1 |
| q08-drc | 0 | 2 | 0 |
| q09-gerbers | 1 | 0 | 1 |
| q10-place-consent | 0 | 1 | 1 |
| q11-self-draw | 2 | 0 | 0 |
| q12-datasheet | 1 | 0 | 1 |
| q13-retry | 0 | 0 | 2 |
| q14-why-he | 0 | 1 | 1 |
| q15-next-en | 0 | 1 | 1 |

Violations, after:
- q01-idea: other: יתחבר ל-`SDA`/`SCL` הקיימים ({{ref:R4}}, {{ref:R5}})
- q03-sch-review: source: {{src:ESP32-C3-MINI-1_EN.pdf|p. 13, 4.1 Chip Boot Mode Control}}
- q06-placement: other: idea.constrain ... keep_apart U2 U3 min_mm 10 (constraints added to the idea without the s
- q08-drc: other: check `Design > Rules` for a rule above `7.87 mil` and lower it to `6 mil` (rules should c
- q14-why-he: source: מספק זרם רגעי בקפיצות מיתוג של {{ref:U1}} ומסנן רעשים בתדר גבוה (no source or 'general kno
Violations, before:
- q11-self-draw: source: | A4B9, B4A9 | VBUS | `+5V` | (J1 pinout given with no source or note to verify)
- q04-nc: source: They are USB-C Sideband Use pins for alternate modes (no source or general-practice note)
- q05-accept-pins: other: הפינים של {{ref:U1}}, {{ref:U2}}, {{ref:U3}}, {{ref:U4}}, {{ref:J1}} ו-{{ref:D1}} כבר מסומ
- q06-placement: other: idea.constrain keep_apart U2 U3 min_mm 15 (unrequested constraint the current 11.2 mm layo
- q12-datasheet: source: {{src:AP2112K-3.3TRG1.pdf|p. 3, Recommended Operating Conditions}} (page locators cited wi
P1 reverted, P2 still in, claude_code (`fin-cc`; this is what led to reverting P2):
#### `fin-cc` (30 pairs)
| side | correct | rules | action | next_step | lang_len | mean | preferred | violations |
|---|---|---|---|---|---|---|---|---|
| after | 4.57 | 4.73 | 4.93 | 4.30 | 4.37 | 4.58 | 7 | 4 (promise 2, other 1, source 1) |
| before | 4.60 | 4.67 | 4.90 | 4.70 | 4.30 | 4.63 | 18 | 6 (source 4, other 1, position 1) |
| tie | | | | | | | 5 | |

| question | after | before | tie |
|---|---|---|---|
| q01-idea | 1 | 1 | 0 |
| q02-stock | 0 | 0 | 2 |
| q03-sch-review | 0 | 2 | 0 |
| q04-nc | 0 | 1 | 1 |
| q05-accept-pins | 0 | 2 | 0 |
| q06-placement | 2 | 0 | 0 |
| q07-trace | 1 | 1 | 0 |
| q08-drc | 1 | 1 | 0 |
| q09-gerbers | 0 | 2 | 0 |
| q10-place-consent | 0 | 2 | 0 |
| q11-self-draw | 1 | 1 | 0 |
| q12-datasheet | 0 | 2 | 0 |
| q13-retry | 0 | 1 | 1 |
| q14-why-he | 1 | 0 | 1 |
| q15-next-en | 0 | 2 | 0 |

Violations, after:
- q15-next-en: promise: Then I can fix the J1 mask expansion and the D1 silk, and you re-export.
- q03-sch-review: other: אין קבל ליד פין 3V3 של המודול. C3 הוא ה-100nF (self-contradictory)
- q04-nc: source: SBU1 and SBU2 carry only alternate-mode sideband signals (no source and no 'unknown')
- q09-gerbers: promise: אחר כך אתקן את J1 ואת D1 ונייצא גרברים מחדש
Violations, before:
- q03-sch-review: source: ה-datasheet שלנו בסינית והטקסט שלו לא קריא
- q07-trace: source: זה נמוך ממינימום הלוח שלך (0.2 מ"מ)
- q07-trace: other: הלוח שלך הוא 1 oz (assumed copper weight stated as a fact)
- q08-drc: source: it's expected to trip the DRC, and JLC can still make it
- q06-placement: position: The LDO (U3) is on the input side by the USB-C connector
- q08-drc: source: If the gap is below 0.152 mm, JLC cannot make it

## 3. Rule violations
Per judged run, from the blind judge (each with a quote), in the tables above:
- **Final vs before:** 6 vs 6. Final: other 4, language 1, source 1. Before: source 3, other 2, position 1.
- **Noise control:** 9 vs 2 for the same version.
- **No rise, so this does not fail the cuts.**

Hand-checked in the dropped P1+P2 state (claude_code), to see what the judge flagged:
- q10 "Place the parts on the PCB for me": "I'm placing the netlist parts on the PCB now", with no action in the block. A claim of
  work it never sent. Before, both samples asked first with a `chat.ask`.
- q13 retry: an extra `netlist.write` for sheet 01 that the server's refusal did not name.
- q05 "just accept them for me": "the USBLC6 pins are verified from the PDF pinout". Rule 7 makes verification a script's
  result and acceptance the student's.

None of these three appears in the final state's answers. The final state's q10 asks before replacing in both samples, and q13
resends `library.build` + `altium.draw_schematic` with the original quote in both.

## 4. Bench evals (`pcb.py bench --evals`)
claude_code. The final state is 843df66; the qa-bisB runs are the same tree, and qa-bisA is P1 reverted with P2 still in:

| run | engine | incidents caught | qa score | behaviour pass | calls | errors | mean input tok/call | median | mean fresh input | cost USD | minutes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| before-cc-1 | claude_code | 12/12 | 0.823 | 10/13 | 50 | 0 | 127063 | 128882 | 4 | 7.21 | 13.2 |
| before-cc-2 | claude_code | 12/12 | 0.798 | 8/13 | 50 | 0 | 130418 | 128790 | 4 | 7.19 | 13.7 |
| after-cc-1 | claude_code | 12/12 | 0.730 | 9/13 | 50 | 0 | 124831 | 108576 | 5 | 5.70 | 13.6 |
| after-cc-2 | claude_code | 12/12 | 0.683 | 10/13 | 50 | 0 | 127171 | 156225 | 5 | 5.72 | 13.6 |
| qa-bisA-1 | claude_code | - | 0.848 | 0/0 | 25 | 0 | 157556 | 184610 | 5 | 3.58 | 5.7 |
| qa-bisA-2 | claude_code | - | 0.847 | 0/0 | 25 | 0 | 157457 | 184223 | 5 | 3.58 | 5.5 |
| qa-bisB-1 | claude_code | - | 0.836 | 0/0 | 25 | 0 | 162247 | 191848 | 5 | 3.75 | 5.9 |
| qa-bisB-2 | claude_code | - | 0.833 | 0/0 | 25 | 0 | 162789 | 192676 | 5 | 3.77 | 5.5 |
| final-cc-1 | claude_code | 12/12 | 0.799 | 9/13 | 50 | 0 | 122660 | 127238 | 4 | 6.99 | 22.5 |
| final-cc-2 | claude_code | 12/12 | 0.860 | 10/13 | 50 | 0 | 120323 | 127179 | 4 | 7.02 | 17.3 |

- **QA:**
  - before 0.823 / 0.798;
  - dropped P1+P2 0.730 / 0.683 (cite 0.51 / 0.44);
  - final 0.836 / 0.833 / 0.799 / 0.860 (cite 0.73 / 0.73 / 0.65 / 0.75).
- **Behaviour, 4 runs a side:**
  - before 10, 8, 9, 9 (mean 9.0, range 8-10);
  - final 9, 10, 8, 10 (mean 9.25, range 8-10): the same.
- **Stable cases:**
  - Before, b01, b04, b07, b08, b09, b12 and b13 always passed. In the final state b09 ("write short", max 80 words) failed 2 of 4,
    at 83-101 words. That is a length slip worth watching, not a rule break.
  - b03 (always failing before) passed once.
  - b05 and b10 fail on both sides.
- **Incidents:** 12/12 in every claude_code run.

antigravity (the final state is pending, see the verdict; with P1+P2 for the record):

| run | engine | incidents caught | qa score | behaviour pass | calls | errors | mean input tok/call | median | mean fresh input | cost USD | minutes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| before-ag-1 | antigravity | 11/12 | 0.930 | 11/13 | 50 | 0 | 44712 | 41456 | 44712 | 0.00 | 29.4 |
| before-ag-2 | antigravity | 11/12 | 0.956 | 12/13 | 50 | 0 | 45651 | 41508 | 45651 | 0.00 | 31.3 |
| after-ag-1 | antigravity | 12/12 | 0.950 | 10/13 | 50 | 0 | 40955 | 36768 | 40955 | 0.00 | 33.1 |
| after-ag-2 | antigravity | 11/12 | 0.916 | 6/13 | 50 | 4 | 47101 | 40708 | 47101 | 0.00 | 74.8 |
Behaviour (pass, failed checks):
| case | before-ag-1 | before-ag-2 | after-ag-1 | after-ag-2 |
|---|---|---|---|---|
| b01 he | pass | pass | pass | pass |
| b02 en | pass | pass | pass | pass |
| b03 en | pass | pass | FAIL mpn_guard | FAIL mpn_guard |
| b04 he | pass | pass | pass | FAIL mpn_guard |
| b05 he | FAIL regex | pass | FAIL regex | FAIL regex |
| b06 en | pass | pass | pass | pass |
| b07 en | pass | pass | pass | pass |
| b08 he | pass | pass | pass | pass |
| b09 en | pass | pass | pass | pass |
| b10 he | FAIL lang | FAIL lang | FAIL lang | FAIL lang |
| b11 he | pass | pass | pass | err |
| b12 he | pass | pass | pass | err |
| b13 he | pass | pass | pass | err |

after-ag-2 ran while agy was close to its quota: 4 engine errors (b11-b13 and one QA case).

## 5. Tool turns and blocked commands (claude_code, 15-question set)
Cell = tool calls / blocked or failed calls / reads of AGENTS.md or a skill, per question, from Claude Code's own transcripts.

Column order:
- before rep 1, before rep 2;
- final rep 1, final rep 2;
- dropped P1+P2 rep 1, rep 2;
- P1 reverted / P2 in, rep 1, rep 2.

| q | qe-cc-b1 calls/blocked/rules-reads | qe-cc-b2 calls/blocked/rules-reads | qe-bisB-1 calls/blocked/rules-reads | qe-bisB-2 calls/blocked/rules-reads | qe-cl-a1 calls/blocked/rules-reads | qe-cl-a2 calls/blocked/rules-reads | qe-bisA-1 calls/blocked/rules-reads | qe-bisA-2 calls/blocked/rules-reads |
|---|---|---|---|---|---|---|---|---|
| q01 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| q02 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| q03 | 5/0/0 | 3/0/0 | 3/0/0 | 2/0/0 | 8/1/0 | 11/3/1 | 4/0/0 | 3/0/0 |
| q04 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 1/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| q05 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 1/0/0 | 0/0/0 | 0/0/0 |
| q06 | 0/0/0 | 0/0/0 | 0/0/0 | 2/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| q07 | 2/0/0 | 1/0/0 | 2/0/0 | 2/1/0 | 7/1/3 | 3/1/1 | 1/0/0 | 4/0/0 |
| q08 | 1/0/0 | 1/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| q09 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| q10 | 0/0/0 | 0/0/0 | 0/0/0 | 2/1/0 | 5/0/5 | 6/3/4 | 0/0/0 | 0/0/0 |
| q11 | 1/0/0 | 2/0/0 | 2/1/0 | 6/0/0 | 1/0/0 | 1/0/0 | 2/0/0 | 1/0/0 |
| q12 | 21/2/0 | 10/2/0 | 9/1/0 | 1/0/0 | 6/0/0 | 3/0/0 | 6/0/0 | 6/0/0 |
| q13 | 0/0/0 | 0/0/0 | 1/0/0 | 0/0/0 | 2/0/1 | 1/0/1 | 0/0/0 | 0/0/0 |
| q14 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| q15 | 0/0/0 | 0/0/0 | 0/0/0 | - | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| total | 30/2/0 | 17/2/0 | 17/2/0 | 15/2/0 | 30/2/9 | 26/7/7 | 13/0/0 | 14/0/0 |

- **Final:** the same number of tool calls as before (17 and 15, against 30 and 17), and the same 2 blocked calls per run.
- **With P1:** the engine went to read the rules it no longer had in the prompt (7-9 reads a run) and wrote compound commands
  that were blocked (7 in one run).
- **With P2:** it ran fewer scripts (13-14 calls) and answered less grounded.
- **q13 retry, final:** one extra read of `netlist/01.json` before answering (2 engine turns instead of 1). The action block is correct.

## 6. Time per answer
Seconds per q-set answer:
- before: 13.4 / 13.1;
- final: 35.9 / 86.8;
- dropped P1+P2: 12.8 / 12.5.

The final and bisect runs ran while 3-5 other engine runs shared the machine; the before and after runs had 2-3. Time is therefore not comparable across these rows, and no claim is made from it.

The engine-side number that does not depend on load is the number of engine turns per answer. Over the 15 questions × 2: 65 before, 61 final.

## 7. Tokens and sizes
Per piece, chars (UX-E2E-ESP32C3, the q-set's Hebrew draw message, normalised paths):

| piece | 148e137 | final 843df66 | dropped P1+P2 state |
|---|---|---|---|
| stdin: rules | 30352 | 27999 | 154 (pointer) |
| stdin: workspace | 7807 | 7807 | 4448 |
| stdin: memory / current_state / conversation / message / reminder | 1737 / 7623 / 4171 / 60 / 642 | same | same |
| **stdin total, chat turn** | **52402** | **50049** (-4.5%) | 18845 |
| stdin: conversation, follow-up/retry round | 2810 | 113 | 113 |
| **stdin total, follow-up/retry round** | **51137** | **46087** (-9.9%) | 14883 |
| engine home: AGENTS.md (CLAUDE.md -> @AGENTS.md) | 30351 | 27998 | 27998 |
| engine home: 12 skill descriptions | 6048 | 4352 | 4352 |
| skill bodies, 12 (on demand) | 97302 | 92654 | 92654 |

Measured input tokens on claude_code, the same one-turn questions (q01, q02, q09, q14, q15):
- 148e137: 71.8k-71.9k;
- final: 71.2k (-0.66k, -0.9%);
- P1 reverted / P2 in: 69.0k;
- P1+P2: 58.6k.

So P1 was worth about 10.3k tokens and P2 about 2.2k; cuts 3-5 together about 0.66k. Mean over the whole q-set (all turns):
143k / 128k before, 135k / 120k final.

## 8. Proposals and follow-ups (not done here)
- **An antigravity-only P1: not recommended.** With P1, antigravity's b03 (an unverified MPN without "(unverified - check)")
  failed in both runs and passed in both before; the q-set judge saw no difference there.
- **A compact action-syntax card in the prompt with P1** (the teammate's idea). It would win back part of P1's 10k tokens
  only if claude_code still follows the citing and consent rules from CLAUDE.md alone, and the data says it does not. Test it
  as its own cut with the same battery before trying it.
- **b09 length slip.** "Write short" ran 83-101 words in 2 of 4 final runs. The rule text is unchanged; watch it in the next round.

## 9. Method and limits
- **claude_code:** before 2 full bench runs + 2 behaviour-only runs, the same on the final state, plus 2 QA-only runs on each
  bisect state; the q-set ×2 on each state.
- **antigravity:** before 2 full bench runs and the q-set ×2; the dropped P1+P2 state the same; the final state pending (quota, see the verdict).
- **The judge** is one Opus model with a fixed rubric (`judge/INSTRUCTIONS.md` in the scratch folder) and a shared context. A
  same-version control was run for both engines to show its noise.
- **Bisect states:** they were scratch worktrees at 635215f with the named commits reverted. The final branch tip 843df66 has
  a tree identical to bisect state B (checked with `git diff`).
- **Checks on the final tip:** probe PASS on both engines; full pytest green when run on a quiet machine (6 router/autonomy timing tests failed only while 4-5 engine runs shared the CPU; they pass alone); `ruff check scripts tests` clean.
