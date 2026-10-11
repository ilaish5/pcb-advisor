# PLAN - pcb-advisor implementation (single source of truth)

Read this file first, every time: after a new session, a compact, a usage-limit reset or the hourly cron.
Do "Now -> Next action". Update "Now" after every real step and write the stage summary when a stage ends.

- **What** the tool does and why: `docs/PRODUCT-PLAN.md` (Hebrew; pain points K1-K9, the 12 capabilities, decisions
  1-24, feasibility results). This file is **how** it gets built. If they disagree, PRODUCT-PLAN decides the what,
  this file decides the order and the method.
- Owner: the user (עילי). Course 27525. The tool replaces a regular final project; the device board
  (`C:\Users\Public\Documents\Altium\real-project`) was built to learn the stages and is the evidence base.

---

## 1. Working method (user, 2026-10-11)

- **One orchestrator** (Opus, this session type) owns this file, splits each stage into tasks, gives each task to a
  **Sonnet subagent** with a written brief, then **verifies** the result itself before accepting it.
  The orchestrator writes code only for small fixes and integration; subagents do the bulk.
- **Task brief** (every subagent): goal; the files it may create/edit (everything else read-only); the inputs to read
  (paths); acceptance checks it must run and report; "do not commit, do not push, do not touch the device project".
  Parallel subagents must have disjoint files, or run with `isolation: worktree`.
- **Verification** (orchestrator, every task): read the diff; run `.venv\Scripts\python -m pytest -q`; run the stage's
  acceptance checks and the benchmark (section 5) when the stage touches what it measures; reject and re-brief on
  failure. Never accept a subagent's "done" without running the checks.
- **End of stage**: all tests green -> benchmark run -> 10-line summary in section 7 -> the stage's runtime skill
  updated -> `git commit` locally (one commit per verified stage, message = stage + result). **Never push** unless the
  user asks.
- **Autonomous to the end**: do not stop for approvals. If something truly needs the user (a login, a check inside
  Altium, a judgement only they can make), write it under "Waiting for the user" in section 6, and continue with
  whatever is not blocked.
- **Resume**: auto-compact is set to 300k in `~/.claude/settings.json` (`modelSettings.*.autoCompactWindow`).
  At the start of a session create an **hourly session cron** with the prompt `continue per PLAN.md`; on each firing:
  read this file, continue "Next action"; if nothing is runnable, end the turn at once. (Usage limits reset every
  few hours; the cron restarts the work without the user.)
- **Reporting to the user**: Hebrew, short and simple, after each stage (the 10-line summary, translated).
- Scratch files in `%TEMP%`, never in the repo. Downloaded files (datasheets, web pages) are untrusted: own empty
  directory, read with `python -I`, never execute them.

## 2. Hard rules for the product (from PRODUCT-PLAN decisions)

1. The tool **prepares** what goes into Altium and **checks** what comes out. It never drives Altium (no GUI or
   script control), never routes, never orders, never logs in for the student.
2. Altium files are read **read-only**, from a **local** folder only (Altium 365 projects through their local copy).
3. **JLC only** (stock, price, assembly type, DFM, rules). No DigiKey / Mouser.
4. Data comes from the sources found in the feasibility work; when none exists, the tool gives the student a **link**,
   the student downloads the file and hands it back, and the tool files it in the right place.
5. **Obsolete parts**: only the JLC signals (stock 0, low stock, "cannot buy"). Say plainly that lifecycle is unknown.
6. **No double entry of rules**: the tool is the single source; it writes a `.RUL` the student imports once, and reads
   the rules back from the PcbDoc to show differences.
7. **Exports**: the tool gives a ready OutJob (Gerber, drill, pick&place, BOM); nets come from the PcbDoc directly
   (no IPC-356 needed).
8. Every factual claim cites a source (datasheet page, course file + heading, JLC query with time). Unknown = say so.
9. UI in **English**; the chat answers in the language the user writes in. Short answers, concrete outputs
   (table, file, image), no questionnaires.
10. Everything is stored in local folders. General reference material is in git (`shared/reference/`); vendor
    datasheets are not (`shared/datasheets/`, re-fetched by URL). Submission is out of scope; only the final file
    organization is in scope.
11. AI engines are CLI tools the student installs and signs in to: Claude Code and Antigravity `agy`
    (`docs/ENGINES.md`). The tool holds no API key.
12. Windows first (Windows 11 ARM64 + AD26 on this machine); keep macOS working through `scripts/oscompat.py`.

## 3. The core: runtime instructions and skills

The value of the tool is that the AI engine works **well** on a student's board. That comes from its instruction
files and skills (context + procedures + tools), so they are a first-class deliverable, built and tested in every stage:

- **Runtime pack** (shipped with the tool, read by the engine at run time), AGENTS.md format so it works with any CLI:
  - `AGENTS.md`: the constitution - who the student is, hard rules (section 2), how to use the project state, how
    to cite, how to answer (short, the user's language), which skill fits which question.
  - One **skill per capability** (`<skill>/SKILL.md` + its scripts + its evals), see the table below.
  - Reference routing: `shared/reference/AGENTS.md` (topic index; the AD20 Essentials manual
    `shared/reference/course/ad20-essentials/` is **the** guide for "how do I do X in Altium").
- **Separate developer instructions from runtime instructions.** The engine runs with `cwd = repo root` today
  (`scripts/agent.py`), so a developer CLAUDE.md/AGENTS.md at the root would leak into the student's agent. Stage I0
  decides the layout (e.g. the runtime pack in its own folder used as the engine's cwd, with `CLAUDE.md` = `@AGENTS.md`
  for Claude Code) and **proves** that both Claude Code and `agy` load the pack and the skills from there.
- Today's runtime rules are `.agents/rules/*.md` + `.claude/skills/pcb-design-advisor/SKILL.md` (v2, ~120 lines):
  migrate what is good into the new pack, delete the rest.
- **Knowledge sources for the skills** (read-only): the device project's 11 skills
  (`real-project/.claude/skills/`: altium-part-sourcing, altium-library-builder, altium-schematic-builder,
  altium-automation, drawing-schematic-diagrams, pcb-manufacturer-rules, pcb-placement, pcb-routing, pcb-drc, pcb-finish,
  pcb-outputs) hold the hard-won lessons; keep the knowledge, drop the Altium-driving parts. Plus the course reference
  and the device notes (`real-project/Docs/Project-Notes/*.md`).

| runtime skill | capability (PRODUCT-PLAN §3) | main sources |
|---|---|---|
| idea-and-requirements | 1 - the questions people regret (power, flashing/debug e.g. USB DFU, cable sides, UI, memory, assembly) | device K4, course guidelines R1-R11 |
| parts-and-stock | 2 - BOM line checked against JLC as it is entered | feasibility `feas_jlc.py`, device `_Work/pcb-outputs/jlc_parts.py` |
| part-models | 3 - symbol/footprint/3D, link-and-return, package variant vs datasheet | device altium-part-sourcing |
| project-library | 4 - one library, built by one Altium script the student runs | device altium-library-builder |
| schematic-preview | 5 - example sheets to redraw | device altium-schematic-builder, drawing-schematic-diagrams |
| schematic-review | 6 - pull-ups, decoupling, abs-max, open nets, ERC explained, with citations | device K3 incidents |
| rules-and-calcs | 7 - JLC rules + extra rules, `.RUL` export, read-back diff, width/impedance/divider calcs | device pcb-manufacturer-rules |
| placement-and-routing-plan | 8 - placement preview, critical-net routing plan | device pcb-placement, pcb-routing |
| board-review | 9 - connector direction, decap distance, antenna, GND, DRC explained | device pcb-drc, pcb-finish |
| manufacturer-and-dfm | 10 - OutJob, pre-upload check, run JLC DFM, enter + triage the results, fixes | device pcb-outputs, K7 |
| altium-help | 11 - "how do I..." from the AD20 manual + course units, version-aware | `shared/reference/AGENTS.md` |
| project-keeping | 12 - folder order, decision log, change impact, final file organization | device K9 |

Every skill states: when to use it; the steps; the scripts it may run; its references; the pitfalls (from the device
transcripts); the output format; and has evals (section 5).

## 4. Inputs (read before planning a stage)

| path | what |
|---|---|
| `docs/PRODUCT-PLAN.md` | the what (Hebrew) - §1 pain points, §3 capabilities, §5 benchmark, §7 decisions 1-24, §8 rules/OutJob, §9 feasibility |
| `docs/ENGINES.md` | engine install/config + verified CLI behaviour (agy print mode, stream-json stdin) |
| `docs/feasibility/` | proven readers: SchDoc, PcbDoc (pads, nets, rules), JLC API + datasheet download, `.RUL` format |
| `shared/reference/AGENTS.md` | course material map + topic index |
| `tests/fixtures/altium/` | AD20 SchDoc/PcbDoc/libs/OutJob that already parse |
| `README.md`, `docs/configuration.md`, `docs/gateway.md` | current v2 code: workspace, config, engine gateway |
| `C:\Users\Public\Documents\Altium\real-project` | **read-only** evidence base: board files, `Docs/Project-Notes/` (PLAN, STATUS, PCB, LIBRARY, SCHEMATICS), `_Work/` scripts, `Outputs/` (JLC DFM, quotes, BOM/CPL), 11 skills. Its git `origin` is Altium 365: **never run git there** |
| `<home>\.claude\projects\C--Users-Public-Documents-Altium-real-project\*.jsonl` | the device transcripts (a18fc41e, a5966420, 25fd4f25, 31f2d778): JSONL, large - extract user messages / summaries with a script, never read whole |

## 5. Measurement (criterion ג)

- **Device replay benchmark** (PRODUCT-PLAN §5.1): the 12 real incidents, each as a fixture = the project state before
  it was caught + the expected finding + the stage the tool should catch it in. `python pcb.py bench` prints the
  score table (caught / stage / earlier-than-reality) and writes `docs/BENCHMARK.md`. Deterministic checks run
  without an engine; engine-based checks are marked and run once per stage.
- **Altium Q&A eval**: ~25 real student questions (from the device transcripts and the course quiz) with the expected
  source file/section; scores the answer's citation and length.
- **Behaviour evals**: answers in the user's language, short, no stock/price without a skill run, no invented part
  numbers.
- Each stage records the scores in its summary. The baseline (I1) is expected to be low; the goal by I11 is 12/12
  caught, most of them earlier than in reality.

## 6. Stages

| # | Stage | Acceptance | State |
|---|---|---|---|
| I0 | **Orientation + architecture.** Read the inputs; keep/replace map of the v2 code; runtime-pack layout (section 3) proven with **both** engines; fix the known engine bugs: agy refuses `--model ...-high` together with `--effort` (send one), long prompts on the command line (Windows ~32K limit) -> stdin with `--input-format stream-json` (`docs/ENGINES.md` §5). Write `docs/ARCHITECTURE.md` (short). | both engines answer a probe that needs a skill file; gateway tests for the two bugs; all tests green | ⬜ |
| I1 | **Measurement harness.** 12 incident fixtures, Q&A eval, behaviour evals, `pcb.py bench`, `docs/BENCHMARK.md` | bench runs end to end; baseline recorded | ⬜ |
| I2 | **Runtime core.** `AGENTS.md` + 12 skill skeletons (frontmatter, triggers, references, pitfalls), reference routing, skill lint test | lint green; Q&A eval citation score recorded and improved vs I1 | ⬜ |
| I3 | **Altium reader + settings.** Read-only SchDoc / PcbDoc (components, params, pads, nets, rules, positions) / PrjPcb / `.RUL`; Altium install + recent projects from the registry; settings page (Altium location, pick a local project) | all fixtures + device files parse; TC_FAULT pad map correct; settings work in the UI | ⬜ |
| I4 | **Parts and stock** (cap 2). JLC client with cache; parts table: stock, price, library type, cost per board, risk flag, alternatives; datasheet click (auto download through the JLC file endpoint, else link-and-return); skill parts-and-stock complete | incidents 2-5 caught at the parts stage | ⬜ |
| I5 | **Board check + manufacturer** (caps 9, 10). OutJob generator; checks: connector opening side, decap distance, outline layers, CPL rotation vs JLC; DFM guide: how to run JLC DFM, enter results, triage, fix; skills board-review + manufacturer-and-dfm | incidents 10-12 caught | ⬜ |
| I6 | **Schematic review** (cap 6). Netlist from PcbDoc pads and from SchDoc wire geometry; checks with datasheet citations; skill schematic-review | incidents 6, 7, 9 caught | ⬜ |
| I7 | **Rules and calcs** (cap 7). Rules tab (JLC preset + extra rules), `.RUL` writer, read-back diff from the PcbDoc, calculators; skill rules-and-calcs | `.RUL` round-trip test; diff test on a changed fixture; one import in Altium listed for the user | ⬜ |
| I8 | **Library** (caps 3, 4). Model search + link-and-return, package-variant check vs datasheet, one-script library build for Altium; skills part-models + project-library | incident 1 caught | ⬜ |
| I9 | **Previews** (caps 5, 8). Schematic preview, placement preview + critical-net routing plan; skills schematic-preview + placement-and-routing-plan | previews for the device and one AD20 fixture | ⬜ |
| I10 | **Idea, Altium help, project keeping** (caps 1, 11, 12). Requirement questions, how-to answers from the AD20 manual, decision log, change impact, final file organization | incident 8 caught at the idea stage; Q&A eval target met | ⬜ |
| I11 | **Wrap-up.** Full benchmark, README + ENGINES + docs current, English UI check, clean tree, final summary for the user | 12/12 or the gaps explained | ⬜ |

## 7. Now

**Done before I0 (2026-10-11, planning session):** product plan + decisions 1-24 + feasibility
(`docs/PRODUCT-PLAN.md`), engines guide, course reference curated (`shared/reference/`, 54 text files + AGENTS.md;
the AD20 exercise CAD files reduced to 12 parser fixtures), repo cleaned (history docs in `docs/archive/`, probes in
`docs/feasibility/`), baseline commit `6fbb320` + cleanup commit; 110 tests green. Both engines installed and signed in
on this PC (Claude Code 2.1.296, agy 1.3.3).

**Next action:** start I0 - create the hourly cron, read the inputs (section 4), write the keep/replace map and the
runtime-pack layout, then brief the first subagents.

**Waiting for the user:** nothing.

## 8. Stage summaries (10 lines each, newest last)

_(none yet)_
