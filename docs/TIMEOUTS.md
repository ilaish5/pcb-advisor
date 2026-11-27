# Timeouts: a valid operation never fails on a clock

The rule: **a wall-clock cap is never the reason a valid operation fails.** What may end an operation early is a *stall* (a whole
period with no progress), a hard ceiling far above the normal time (a runaway), or a result (an error box, an answer). Whatever
ends it says which, and what was done so far is kept.

## Routing (`scripts/altium/route.py`, `negotiate.py`)

- `Clock(seconds, ceiling, progress)`: `seconds` is one **segment** (`route.SEGMENT_S` = 120 s); the longest total time is
  `route.SECONDS_MAX` = 1200 s. A segment that ends while nets are still closing is renewed ("Still routing, segment 2: 9 nets
  left of 45"). Progress is a net closed, or (negotiated engine) fewer overlaps.
- It stops only when a whole segment brought no progress (`stats.stopped = "stall"`) or the ceiling is reached (`"ceiling"`).
  The routed nets are kept; each open net says why ("ran out of time: no net was closed in the last 120 s" / "longest routing
  time, 1200 s, reached while still making progress").
- Progress reaches the step's line: `plan_routes(progress=fn)` calls `fn(snapshot)` at once and at least every 2 s (a heartbeat
  thread covers the stretches where no search asks the clock); `bridge.progress_to` hands it to `serve._run_progress`, the UI polls
  `/api/altium/step-status` (1.5 s) and `previews.js` rewrites the `.pv-detail` text in place.
- A caller that names `seconds` (and no `max_seconds`) still gets a plain cap, as before.

## The bridge to Altium (`scripts/altium/bridge.py`)

- `total_timeout` of a batch is what the batch is expected to take. A script that **keeps logging** is alive: it is cut off only by
  `stall_timeout` (no log line), an open error box, or `LONG_RUN_FACTOR` (4) times `total_timeout` (a runaway). While it runs, the
  step's line says "Altium is working: <last log line>" every 2 s.
- A launch that leaves a **second X2.EXE** alive (beyond the one a cold start makes) is a failure, whatever that Altium answered.
- Last resort, logged (`altium-restart` in the run log): when the start flag is older than the stall limit, the log did not move
  and the proven release (OK on the box, RunMacro) did not help, X2.EXE is closed only if the batch names nothing but copies
  (temp or `acc-scratch` folders). The error then says so in one line. Anything else is left alone and the refusal is logged.

## Audit of the other timeouts

| Where | What | Decision |
|---|---|---|
| `bridge._run_commands` `total_timeout` | wall cap on a script that is still logging | **changed** (stall detector + 4x runaway cap + progress) |
| `route_on` / `time_budget` | wall cap 80-120 s | **changed** (segments, stall/ceiling, progress); `time_budget` removed |
| tests: `PLACE_BUDGET_S`, `ROUTE_BUDGET_S`, CPU guards (`test_altium_route`, `decap_xtal`, `test_live_stm32_*`) | failed on a slow runner | **changed**: result asserted; speed guards are expansion counts or a large hang guard |
| tests: `wait_for`, `idle`, `wait_idle` | short limits on a real condition | **changed**: 30 s (returns the moment the condition holds) |
| `bridge` `start_timeout` (45 s, x8 cold) | the script never started | left: it is the stall detector of the start |
| `bridge` `stall_timeout` (60-180 s) | no log line | left: it is the stall detector |
| agent `agent.timeout_seconds` (900 s) | wall cap on one agent turn | left: explicit error with Retry; `agent.idle_timeout_seconds` (180 s) is already the stall detector; configurable |
| gateway `stream.run` total/idle | same | left: same |
| `urlopen(..., timeout=)` in jlc / doctor probes | socket read timeout | left: per read, i.e. a stall detector by nature; probes are diagnostics |
