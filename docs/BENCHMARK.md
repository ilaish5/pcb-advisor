# Benchmark: device replay

- date: 2026-10-11 17:25
- commit: 07c515c
- mode: deterministic

## Scores

| # | Incident | Reality | Target | Det | Engine | Earlier | Errors |
|--:|---|:-:|:-:|:-:|:-:|:-:|---|
| 1 | U4 footprint is A7670C, not A7670G | F | C | no | - | no |  |
| 2 | 11 BOM lines have no match at JLC | F | B | no | - | no |  |
| 3 | U9 external flash costs $19.4 (Extended) | F | B | no | - | no |  |
| 4 | U7 TPS3823A-33DBVR is out of stock at JLC | F | B | no | - | no |  |
| 5 | U4 is "Standard only" for JLC assembly | F | B | no | - | no |  |
| 6 | 1 uF on the VCC pin of MP2315, above the 0.22 uF maximum | D | D | no | - | no |  |
| 7 | TC_FAULT: is the MAX31856 FAULT pin push-pull or open-drain? | D | D | no | - | no |  |
| 8 | Flashing over USB is impossible with the STM32F103 (no USB DFU in ROM) | E | A | no | - | no |  |
| 9 | F411 swap: VCAP_1 capacitor missing and R82 D+ pull-up now redundant | E | D | no | - | no |  |
| 10 | J1 power connector is placed facing the board centre | E | E | no | - | no |  |
| 11 | Board outline (Mechanical 1) plotted into every Gerber layer | F | F | no | - | no |  |
| 12 | CPL rotations disagree with the JLC 3D models (29 alerts) | F | F | no | - | no |  |

**deterministic caught 0/12, engine not run, earlier than reality 0**

## Baseline engine runs (I1 runtime pack, 2026-10-11)

Run from a clean copy of commit 07c515c + the I1 harness (so the I2 skills did not leak in). Answers:
`docs/bench-runs/2026-10-11-baseline-*`.

| engine | incidents caught | earlier than reality | Q&A eval | behaviour eval | notes |
|---|---|---|---|---|---|
| claude_code | 7/7 run (1-7) | 5 | not measured | not measured | 8-12 and all evals failed: session usage limit (exit 1); re-run skipped by user decision |
| antigravity | 2/12 | 1 | 0.63 / 25 | 0.23 / 13 | no skip-permissions flag: 33/50 answers empty (agy denied a shell command) |

## History

- 2026-10-11 17:25 07c515c deterministic: deterministic caught 0/12, engine not run, earlier than reality 0
- 2026-10-11 17:43 07c515c+I1 engine:claude_code (baseline copy): engine caught 7/12 (8-12 not run: usage limit), earlier 5
- 2026-10-11 18:13 07c515c+I1 engine:antigravity (baseline copy, no skip flag): engine caught 2/12, earlier 1, qa 0.63, behaviour 0.23
