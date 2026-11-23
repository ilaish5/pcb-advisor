# Brain eval baseline - 2026-11-23

Baseline for the brain-slim cuts (`docs/BRAIN-EVAL-COMPARE-2026-11-23.md` compares against it). Tip: **148e137**
(claude/beautiful-goldberg-b9e7c5, phase0-correctness merged). Every run used a frozen worktree of that tip, a scratch
`PCB_ADVISOR_ENGINE_HOME` per run, and empty stdin. Sonnet behind claude_code; agy (`--dangerously-skip-permissions`) behind antigravity.

## Health
- `python pcb.py probe --engine all`: claude_code PASS, antigravity PASS (both answer "PROBE-ALTIUM-7Q4X KESTREL-31": AGENTS.md is
  loaded by the engine itself from its engine home).
- `pytest -q -p no:cacheprovider` (stdin from NUL): full suite green on 148e137; `ruff check scripts tests` clean.

## 1. Bench evals (`pcb.py bench --engine E --evals`)
Runs: claude_code 2 full runs (incidents + QA + behaviour) and 2 behaviour-only runs (behaviour is the noisy eval); antigravity
2 full runs (agy takes ~30 min a run: fewer repeats there). "mean input tok/call" = input + cache writes + cache reads over all
the engine's internal turns of one `agent.respond` (claude_code reports the cache split; agy reports input only). claude_code
cost is what the CLI reports; agy reports none.

| run | engine | incidents caught | qa score | behaviour pass | calls | errors | mean input tok/call | median | mean fresh input | cost USD | minutes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| before-cc-1 | claude_code | 12/12 | 0.823 | 10/13 | 50 | 0 | 127063 | 128882 | 4 | 7.21 | 13.2 |
| before-cc-2 | claude_code | 12/12 | 0.798 | 8/13 | 50 | 0 | 130418 | 128790 | 4 | 7.19 | 13.7 |
| bbefore-cc-3 | claude_code | - | - | 9/13 | 13 | 0 | 110376 | 128143 | 3 | 1.90 | 2.7 |
| bbefore-cc-4 | claude_code | - | - | 9/13 | 13 | 0 | 104750 | 127853 | 3 | 1.85 | 2.6 |
| before-ag-1 | antigravity | 11/12 | 0.930 | 11/13 | 50 | 0 | 44712 | 41456 | 44712 | 0.00 | 29.4 |
| before-ag-2 | antigravity | 11/12 | 0.956 | 12/13 | 50 | 0 | 45651 | 41508 | 45651 | 0.00 | 31.3 |

Incidents (engine caught the expected point):
| incident | before-cc-1 | before-cc-2 | bbefore-cc-3 | bbefore-cc-4 | before-ag-1 | before-ag-2 |
|---|---|---|---|---|---|---|
| 01 u4-footprint-variant | yes | yes | - | - | yes | yes |
| 02 jlc-no-match-11 | yes | yes | - | - | yes | no |
| 03 u9-expensive-flash | yes | yes | - | - | yes | yes |
| 04 u7-variant-out-of-stock | yes | yes | - | - | yes | yes |
| 05 u4-standard-only | yes | yes | - | - | yes | yes |
| 06 mp2315-vcc-cap | yes | yes | - | - | yes | yes |
| 07 tc-fault-output-type | yes | yes | - | - | no | yes |
| 08 f103-no-usb-dfu | yes | yes | - | - | yes | yes |
| 09 f411-swap-vcap | yes | yes | - | - | yes | yes |
| 10 j1-faces-inward | yes | yes | - | - | yes | yes |
| 11 outline-in-all-gerber-layers | yes | yes | - | - | yes | yes |
| 12 cpl-rotation-vs-jlc-models | yes | yes | - | - | yes | yes |

QA (score = 0.5 cite + 0.25 length + 0.25 language; words):
| case | before-cc-1 | before-cc-2 | bbefore-cc-3 | bbefore-cc-4 | before-ag-1 | before-ag-2 |
|---|---|---|---|---|---|---|
| q01 | 0.50 (101w) | 0.50 (133w) | - | - | 1.00 (96w) | 0.83 (84w) |
| q02 | 0.47 (133w) | 0.50 (97w) | - | - | 1.00 (95w) | 1.00 (72w) |
| q03 | 0.67 (56w) | 0.67 (55w) | - | - | 0.50 (90w) | 0.50 (93w) |
| q04 | 1.00 (63w) | 1.00 (90w) | - | - | 0.50 (88w) | 1.00 (81w) |
| q05 | 0.83 (103w) | 0.83 (99w) | - | - | 0.83 (81w) | 1.00 (106w) |
| q06 | 1.00 (60w) | 1.00 (91w) | - | - | 1.00 (77w) | 1.00 (79w) |
| q07 | 1.00 (82w) | 1.00 (107w) | - | - | 1.00 (108w) | 1.00 (118w) |
| q08 | 1.00 (79w) | 0.58 (132w) | - | - | 1.00 (90w) | 1.00 (85w) |
| q09 | 1.00 (122w) | 0.83 (82w) | - | - | 1.00 (83w) | 1.00 (90w) |
| q10 | 1.00 (78w) | 1.00 (86w) | - | - | 1.00 (72w) | 1.00 (65w) |
| q11 | 0.75 (119w) | 0.73 (140w) | - | - | 0.75 (100w) | 0.75 (102w) |
| q12 | 0.99 (155w) | 0.75 (102w) | - | - | 1.00 (119w) | 1.00 (67w) |
| q13 | 1.00 (71w) | 1.00 (82w) | - | - | 1.00 (85w) | 1.00 (89w) |
| q14 | 1.00 (61w) | 1.00 (70w) | - | - | 1.00 (87w) | 1.00 (64w) |
| q15 | 0.83 (91w) | 1.00 (89w) | - | - | 0.83 (82w) | 0.83 (68w) |
| q16 | 0.94 (163w) | 0.94 (162w) | - | - | 1.00 (100w) | 1.00 (98w) |
| q17 | 0.90 (168w) | 0.89 (175w) | - | - | 1.00 (93w) | 1.00 (93w) |
| q18 | 1.00 (92w) | 1.00 (94w) | - | - | 1.00 (88w) | 1.00 (90w) |
| q19 | 0.47 (134w) | 0.46 (139w) | - | - | 1.00 (116w) | 1.00 (89w) |
| q20 | 1.00 (73w) | 1.00 (84w) | - | - | 1.00 (66w) | 1.00 (90w) |
| q21 | 0.83 (94w) | 0.81 (132w) | - | - | 1.00 (114w) | 0.99 (125w) |
| q22 | 1.00 (103w) | 1.00 (79w) | - | - | 1.00 (85w) | 1.00 (86w) |
| q23 | 0.46 (160w) | 0.46 (164w) | - | - | 0.83 (94w) | 1.00 (117w) |
| q24 | 0.50 (121w) | 0.50 (122w) | - | - | 1.00 (75w) | 1.00 (69w) |
| q25 | 0.44 (138w) | 0.50 (85w) | - | - | 1.00 (53w) | 1.00 (78w) |

Behaviour (pass, failed checks):
| case | before-cc-1 | before-cc-2 | bbefore-cc-3 | bbefore-cc-4 | before-ag-1 | before-ag-2 |
|---|---|---|---|---|---|---|
| b01 he | pass | pass | pass | pass | pass | pass |
| b02 en | pass | FAIL max_words | pass | pass | pass | pass |
| b03 en | FAIL max_words,mpn_guard | FAIL max_words,mpn_guard | FAIL max_words,mpn_guard | FAIL max_words,mpn_guard | pass | pass |
| b04 he | pass | pass | pass | pass | pass | pass |
| b05 he | FAIL regex | FAIL regex | FAIL regex | FAIL regex | FAIL regex | pass |
| b06 en | pass | pass | pass | FAIL max_words | pass | pass |
| b07 en | pass | pass | pass | pass | pass | pass |
| b08 he | pass | pass | pass | pass | pass | pass |
| b09 en | pass | pass | pass | pass | pass | pass |
| b10 he | FAIL lang,max_words | FAIL lang,max_words | FAIL lang,max_words | FAIL lang | FAIL lang | FAIL lang |
| b11 he | pass | FAIL max_words | FAIL max_words | pass | pass | pass |
| b12 he | pass | pass | pass | pass | pass | pass |
| b13 he | pass | pass | pass | pass | pass | pass |


### Noise
- claude_code behaviour: 10, 8, 9, 9 of 13 (mean 9.0, range 8-10). QA: 0.823 / 0.798. A change counts only outside these ranges.
- antigravity behaviour: 11, 12 of 13; QA 0.930 / 0.956; incidents 11/12 in both runs (a different miss each run: 07, then 02).
- Stable over all 6 runs: b01, b04, b07, b08, b09, b12, b13 always pass; b10 always fails (lang). Stable per engine: b03 and b05
  fail on every claude_code run (b03: max_words + mpn_guard; b05: regex). Flaky: b02, b06, b11 (max_words on claude_code), b05 on agy.
- QA on claude_code loses mostly on length (q01, q02, q19, q23-q25 run 100-165 words and score 0.44-0.5).

## 2. Fixed question set (15 student messages, same project state)
Project state: a copy of UX-E2E-ESP32C3 (ESP32-C3 sensor board; idea confirmed, BOM clean, current stage = schematic with 2 open
pins and 24 pins missing from the netlist, board routed, outputs blocked by the NC gate, 9 DFM findings). A fresh copy for every
question, the project's own chat as history. 2 repetitions per engine. The full replies, actions and tools are kept in the scratch
run files (qbefore-*.json); they go to the blind judge together with the after runs (compare doc).

| id | stage | lang | message |
|---|---|---|---|
| q01-idea | idea | he | אני רוצה להוסיף ללוח גם חיישן אור. מה זה משנה בדרישות? |
| q02-stock | bom | en | Is U3 (the AP2112K) still in stock at JLC, and what does it cost per board? |
| q03-sch-review | sch | he | תבדוק לי את הסכמה של דף 02 (המודול). משהו חסר או לא תקין? |
| q04-nc | sch | en | J1 pins A8 and B8 (SBU1/SBU2) have no net. Should I connect them or mark them NC? |
| q05-accept-pins | sch | he | יש חלקים שהפינים שלהם לא מאומתים. פשוט תאשר אותם בשבילי שנוכל להמשיך. |
| q06-placement | pcb | en | Where should the SHT40 and the LDO go on the board, and how far apart? |
| q07-trace | pcb | he | כמה רוחב מסלול צריך לקו ה-5V מה-USB? |
| q08-drc | rules | en | Altium DRC shows clearance errors between the USB-C connector pads. What should I do? |
| q09-gerbers | outputs | he | אפשר כבר להוציא גרברים ולשלוח ל-JLC? |
| q10-place-consent | pcb | en | Place the parts on the PCB for me. |
| q11-self-draw | sch | he | אני אשרטט את דף 01 בעצמי ב-Altium. רק תגיד לי מה לחבר לכל פין של J1. |
| q12-datasheet | bom | en | What is the maximum input voltage of the AP2112K, and what output capacitor does its datasheet ask for? |
| q13-retry | sch | he | server retry: altium.draw_schematic refused, prereq.library_not_built (after the student wrote: תצייר אתה את דף 01 ב-Altium) |
| q14-why-he | sch | he | למה צריך קבל 100nF ליד המודול? תסביר קצר. |
| q15-next-en | any | en | What should I do next? |

Per question: total input tokens, seconds, words, actions emitted.

| question | qbefore-cc-1 | qbefore-cc-2 | qbefore-ag-1 | qbefore-ag-2 |
|---|---|---|---|---|
| q01-idea | 72k, 17.1s, 100w, idea.propose,idea.diagram.edit | 72k, 14.7s, 88w, idea.propose,idea.diagram.edit | 48k, 40.3s, 85w, - | 52k, 37.1s, 86w, - |
| q02-stock | 72k, 8.6s, 75w, - | 72k, 9.2s, 85w, - | 43k, 21.0s, 62w, - | 40k, 23.7s, 74w, - |
| q03-sch-review | 225k, 23.4s, 131w, - | 225k, 20.8s, 118w, - | 137k, 122.6s, 115w, - | 131k, 82.7s, 137w, - |
| q04-nc | 72k, 7.9s, 97w, - | 72k, 7.1s, 77w, - | 56k, 39.9s, 83w, - | 58k, 52.5s, 47w, - |
| q05-accept-pins | 72k, 11.6s, 81w, - | 72k, 10.6s, 78w, - | 50k, 30.6s, 60w, - | 51k, 29.9s, 68w, - |
| q06-placement | 72k, 8.8s, 102w, idea.constrain,idea.constrain,idea.constrain | 72k, 19.9s, 111w, idea.constrain,idea.constrain,idea.constrain | 82k, 97.2s, 87w, - | 67k, 91.6s, 84w, idea.constrain,idea.constrain,idea.constrain |
| q07-trace | 218k, 18.2s, 69w, net.set_current | 144k, 15.6s, 81w, net.set_current | 72k, 74.1s, 94w, - | 76k, 77.8s, 89w, - |
| q08-drc | 147k, 13.2s, 154w, - | 147k, 16.4s, 158w, - | 197k, 96.5s, 101w, - | 243k, 135.2s, 112w, - |
| q09-gerbers | 72k, 13.8s, 94w, - | 72k, 10.2s, 65w, - | 44k, 27.6s, 72w, - | 44k, 27.7s, 75w, - |
| q10-place-consent | 72k, 7.2s, 46w, chat.ask | 72k, 7.6s, 59w, chat.ask | 43k, 21.8s, 61w, chat.ask | 50k, 47.9s, 47w, chat.ask |
| q11-self-draw | 146k, 9.7s, 73w, - | 148k, 13.7s, 124w, - | 46k, 19.6s, 107w, - | 46k, 17.4s, 109w, - |
| q12-datasheet | 689k, 38.4s, 160w, - | 533k, 25.7s, 149w, - | 54k, 29.3s, 69w, - | 57k, 26.7s, 95w, - |
| q13-retry | 71k, 6.5s, 12w, library.build,altium.draw_schematic | 71k, 6.4s, 10w, library.build,altium.draw_schematic | 40k, 16.5s, 20w, library.build,altium.draw_schematic | 46k, 17.1s, 19w, library.build,altium.draw_schematic |
| q14-why-he | 72k, 9.7s, 68w, - | 72k, 10.2s, 75w, - | 50k, 32.9s, 34w, - | 44k, 26.0s, 38w, - |
| q15-next-en | 72k, 6.3s, 73w, - | 72k, 8.3s, 63w, - | 39k, 20.2s, 55w, - | 39k, 21.5s, 69w, - |
| **mean** | 143k, 13.4s | 128k, 13.1s | 67k, 46.0s | 70k, 47.7s |


## 3. Sizes of one turn (UX-E2E-ESP32C3, the q-set's Hebrew draw message; paths normalised)
What the server sends on stdin:

| piece | chars |
|---|---|
| rules or pointer | 30352 |
| workspace | 7807 |
| memory | 1737 |
| current_state | 7623 |
| conversation | 4171 |
| student_message | 60 |
| reminder | 642 |
| TOTAL stdin prompt | 52402 |

A follow-up / retry round (the server's message instead of the student's):

| piece | chars |
|---|---|
| rules or pointer | 30352 |
| workspace | 7807 |
| memory | 1737 |
| current_state | 7623 |
| conversation | 2810 |
| server_message | 156 |
| reminder | 642 |
| TOTAL stdin prompt | 51137 |

Loaded by the engine itself on every turn (CLAUDE.md -> @AGENTS.md; Claude Code lists the skill descriptions):

| piece | chars |
|---|---|
| AGENTS.md (engine home) | 30351 |
| skill descriptions (12) | 6048 |

So on 148e137 AGENTS.md reaches the model twice a turn (stdin + engine home).
