# Benchmark: device replay

- date: 2026-10-13 22:36
- commit: bd68c2e
- mode: engine:claude_code

## Scores

| # | Incident | Reality | Target | Det | Engine | Earlier | Errors |
|--:|---|:-:|:-:|:-:|:-:|:-:|---|
| 1 | U4 footprint is A7670C, not A7670G | F | C | yes | no | yes |  |
| 2 | 11 BOM lines have no match at JLC | F | B | yes | yes | yes |  |
| 3 | U9 external flash costs $19.4 (Extended) | F | B | yes | yes | yes |  |
| 4 | U7 TPS3823A-33DBVR is out of stock at JLC | F | B | yes | yes | yes |  |
| 5 | U4 is "Standard only" for JLC assembly | F | B | yes | yes | yes |  |
| 6 | 1 uF on the VCC pin of MP2315, above the 0.22 uF maximum | D | D | yes | yes | no |  |
| 7 | TC_FAULT: is the MAX31856 FAULT pin push-pull or open-drain? | D | D | yes | yes | no |  |
| 8 | Flashing over USB is impossible with the STM32F103 (no USB DFU in ROM) | E | A | yes | yes | yes |  |
| 9 | F411 swap: VCAP_1 capacitor missing and R82 D+ pull-up now redundant | E | D | yes | yes | yes |  |
| 10 | J1 power connector is placed facing the board centre | E | E | yes | yes | no |  |
| 11 | Board outline (Mechanical 1) plotted into every Gerber layer | F | F | yes | yes | no |  |
| 12 | CPL rotations disagree with the JLC 3D models (29 alerts) | F | F | yes | yes | no |  |

**deterministic caught 12/12, engine caught 11/12, earlier than reality 7**

## Evals

- qa: score 0.89 over 25
- behaviour: score 0.54 over 13

## History

- 2026-10-11 17:25 07c515c deterministic: deterministic caught 0/12, engine not run, earlier than reality 0
- 2026-10-11 17:43 07c515c+I1 engine:claude_code (baseline copy): engine caught 7/12 (8-12 not run: usage limit), earlier 5
- 2026-10-11 18:13 07c515c+I1 engine:antigravity (baseline copy, no skip flag): engine caught 2/12, earlier 1, qa 0.63, behaviour 0.23
- 2026-10-13 21:17 e1777a8 deterministic: deterministic caught 0/12, engine not run, earlier than reality 0
- 2026-10-13 21:24 e1777a8 deterministic: deterministic caught 12/12, engine not run, earlier than reality 7
- 2026-10-13 21:37 e1777a8 deterministic: deterministic caught 12/12, engine not run, earlier than reality 7
- 2026-10-13 21:57 bd68c2e engine:claude_code: deterministic caught 12/12, engine caught 12/12, earlier than reality 7
- 2026-10-13 22:10 bd68c2e engine:claude_code: deterministic caught 0/0, engine caught 0/0, earlier than reality 0
- 2026-10-13 22:22 bd68c2e engine:claude_code: deterministic caught 12/12, engine caught 12/12, earlier than reality 7
- 2026-10-13 22:36 bd68c2e engine:claude_code: deterministic caught 12/12, engine caught 11/12, earlier than reality 7
  - note (Claude Code): evals of the three Claude Code runs: qa 0.73 -> 0.84 -> 0.89, behaviour 0.08 -> 0.31 -> 0.54.
    Changes between them: a word limit in AGENTS.md; 13 scripts AGENTS.md names were not in Claude Code's
    allowed list (jlc.py stock lookups were blocked), added. Grader fixes after the last run (no new engine
    call): keywords ignore Markdown emphasis (incident 1's answer said "A7670**C**" -> caught, 12/12), stock
    tool pattern accepts jlc.py, package names (SOT-23-6, TO-252, PT100) are not MPNs. Regraded behaviour
    from the saved answers: 7/13; left: answers over the word limit (5), unflagged MPNs (2), a script run not
    listed in the tools block (1). The 22:10 "0/0" row was an evals-only run (`--only 0`).
