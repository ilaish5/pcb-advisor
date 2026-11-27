# Acceptance oracle

The checks behind [ACCEPTANCE.md](../../docs/e2e-2026-11-27/ACCEPTANCE.md). They decide whether a 27/11 finding is fixed.
Frozen by the owner at git tag `acceptance-v1`; a fix branch reads this folder, never edits it (A3, `gate.py frozen`).

## Run
```
.venv/Scripts/python.exe -I tests/acceptance/run.py --controls          # red proof: every artifact metric FAILS on 27/11, every control PASSES
.venv/Scripts/python.exe -I tests/acceptance/gate.py all                 # A2 imports, A3 frozen, A9 special-casing
```
`-I` matters: the oracle must run with no product code on the path. The frozen fixture is local only
(`local/acceptance-fixtures/final-e2e-4l-1127/`, verified against its manifest before and after every run).
This folder is not a pytest suite: no file is named `test_*`, and the normal suite never collects it.

## Layout
- `lib.py`: `@metric` registry, `Ctx` (fixture paths, seeded RNG, `writable_copy`), `Result`.
- `run.py`: runner, manifest check, red proof, results to `local/acceptance-runs/`.
- `gate.py`: A2 / A3 / A9 gates.
- `thresholds.py`: every number with its source (A7).
- `oracle/`: independent readers (PcbDoc via raw `olefile`, Gerber/Excellon, CSV, project JSON). Never `scripts/altium/ole.py`, `pcbdoc.py`, `gerber_check.py`, `outputs_check.py`, `order_check.py`.
- `metrics/`: one module per area; each `@metric` = one catalogue id (or one lettered part, e.g. `F-I(b)`).
- `canaries/`: injectors that change a writable copy at a seeded random place (A5).
- `live/`: behaviour metrics: drive a running server (HTTP + browser DOM) at a given commit.

## Contract for a metric
1. `id` = the ACCEPTANCE.md id; lettered parts as `W32(a)`. One measured value (`measured`), one pass condition (`expected`, A14).
2. Reads artifacts only (A1). The product's own logs or status flags may be printed as corroboration, never decide the status.
3. `evidence`: every file read, with sha256 (`ctx.ev(path, what)`).
4. Artifact metrics: FAIL on the 27/11 fixture, and a `control=` that builds a corrected or synthetic copy (`ctx.writable_copy`) on which the same check PASSES. No control = the metric is not accepted.
5. Where the metric says "canary": the control/canary location comes from `ctx.rng` (seeded, printed), never a fixed designator.
6. No fixture name, refdes, net name or coordinate is hard-coded in a check's logic. Find objects by rule (e.g. "every IC supply pin"), so the check works on a hidden board (A6, A9).
7. A value the metric needs that has no source in `thresholds.py`: stop and report; do not invent it.
8. Hidden halves (A15) and hidden boards (A6) are owner-held, outside the repo; checks must accept any board folder via `--root`.
