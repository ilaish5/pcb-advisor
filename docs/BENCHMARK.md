# Benchmark: device replay

- date: 2026-10-13 21:37
- commit: e1777a8
- mode: deterministic

## Scores

| # | Incident | Reality | Target | Det | Engine | Earlier | Errors |
|--:|---|:-:|:-:|:-:|:-:|:-:|---|
| 1 | U4 footprint is A7670C, not A7670G | F | C | yes | - | yes |  |
| 2 | 11 BOM lines have no match at JLC | F | B | yes | - | yes |  |
| 3 | U9 external flash costs $19.4 (Extended) | F | B | yes | - | yes |  |
| 4 | U7 TPS3823A-33DBVR is out of stock at JLC | F | B | yes | - | yes |  |
| 5 | U4 is "Standard only" for JLC assembly | F | B | yes | - | yes |  |
| 6 | 1 uF on the VCC pin of MP2315, above the 0.22 uF maximum | D | D | yes | - | no |  |
| 7 | TC_FAULT: is the MAX31856 FAULT pin push-pull or open-drain? | D | D | yes | - | no |  |
| 8 | Flashing over USB is impossible with the STM32F103 (no USB DFU in ROM) | E | A | yes | - | yes |  |
| 9 | F411 swap: VCAP_1 capacitor missing and R82 D+ pull-up now redundant | E | D | yes | - | yes |  |
| 10 | J1 power connector is placed facing the board centre | E | E | yes | - | no |  |
| 11 | Board outline (Mechanical 1) plotted into every Gerber layer | F | F | yes | - | no |  |
| 12 | CPL rotations disagree with the JLC 3D models (29 alerts) | F | F | yes | - | no |  |

**deterministic caught 12/12, engine not run, earlier than reality 7**

## History

- 2026-10-11 17:25 07c515c deterministic: deterministic caught 0/12, engine not run, earlier than reality 0
- 2026-10-11 17:43 07c515c+I1 engine:claude_code (baseline copy): engine caught 7/12 (8-12 not run: usage limit), earlier 5
- 2026-10-11 18:13 07c515c+I1 engine:antigravity (baseline copy, no skip flag): engine caught 2/12, earlier 1, qa 0.63, behaviour 0.23
- 2026-10-13 21:17 e1777a8 deterministic: deterministic caught 0/12, engine not run, earlier than reality 0
- 2026-10-13 21:24 e1777a8 deterministic: deterministic caught 12/12, engine not run, earlier than reality 7
- 2026-10-13 21:37 e1777a8 deterministic: deterministic caught 12/12, engine not run, earlier than reality 7
