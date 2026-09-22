# pcb-advisor

A design-considerations tool for students. You describe what you want to build;
it sketches a block diagram and asks whether that's what you meant; then it walks
you down a decision cascade. Every choice you make appends the constraints that
choice just locked in — each one labelled with **how we know it**.

```bash
pip install -r requirements.txt
python3 pcb.py init                  # folders + config.json + a first project
python3 pcb.py serve                 # opens http://localhost:8931
```

One entry point for everything:

```bash
python3 pcb.py new "usb sensor board"   # start a design from the template
python3 pcb.py list                     # what is in the workspace
python3 pcb.py show usb-sensor-board    # where it stands
python3 pcb.py engines                  # which LLM engine is wired up
python3 pcb.py tools                    # what that engine may touch on your machine
python3 pcb.py config user.language he  # read or set any setting
python3 pcb.py chats                    # conversations and their memory
python3 pcb.py check                    # validate the corpus and its citations
python3 pcb.py trace 1.5                # IPC-2221 trace width
```

## Two stages

**Sketch.** Free text in. The agent proposes a block diagram — its interpretation —
and asks you to confirm or correct it. This is where intent gets *agreed* rather
than inferred, and it is also what selects which cascades load: each block `kind`
maps to a domain.

**Cascade.** One question at a time, with its rationale. Answer in the chat or by
clicking. Constraints accumulate; the graph grows; the schematic sharpens.

## How we know things — the provenance contract

| badge | meaning | what it must carry |
|---|---|---|
| 📐 computed | a script produced it | the `calculation` itself |
| 📘 standard | a published standard says it | document + locator |
| 📄 datasheet | a **specific, fetchable** document says it | document + locator + url; cached file + verbatim quote to count as verified |
| 🔎 check your part | depends on the part you chose | where in that datasheet to look |
| ⚠ convention | craft, no citable source | must say so out loud |

`check your part` exists because most of what looked like citations here were
not. Eleven rules cited "regulator datasheet", "ADC datasheet", "P-FET
datasheet" — documents that cannot exist, that no student can fetch and no
script can check, passing validation as silently as a real reference. They were
never citations. They are instructions to go and read whichever part you
actually chose, which is a good thing for a rule to say and a bad thing to
disguise. Naming the class made the real debt visible: **three** datasheet
citations, not thirteen.

Two scripts enforce this, and both run in CI:

- `validate_cascade.py` — a rule must declare its provenance and carry what that
  class requires. A `datasheet` rule with no url is rejected; so is a `computed`
  rule with no arithmetic, and a `check your part` rule that cites a document.
- `verify_sources.py` — every quote marked verified must be findable, **verbatim**,
  in the cached document. Fabricate a quote and it fails.

A fresh clone prints this, because the vendor PDFs are not redistributed here:

```
$ python3 scripts/verify_sources.py
  todo  sw.hotloop: cites 'TI SLYT614', no quote pulled yet
  FAIL  sw.keepaway: slyt614.pdf is not in the cache
  FAIL  sw.cin: slyt614.pdf is not in the cache

0 quotes verified, 2 failed, 1 citation still to check
nothing to verify in: check_your_part=10  computed=2  convention=17  standard=3

The cited documents are not in git - they are vendor PDFs.
Run:  python3 scripts/sources.py restore
```

Do that once and the two FAILs become `ok`. The `todo` stays until someone opens
the document and pulls the quote — that line is the corpus being honest about
its own state, and it is meant to be visible.

## The one rule

```
decisions.jsonl   ─┐
threads.jsonl      ├─► design-model.json ─┬─► blocks.svg
chats/<id>.jsonl   │                      ├─► the graph
sketch.json       ─┘                      └─► the decisions table
```

Only those four feed the model, and three of them are append-only. `project.json`
and `notes.md` are yours to edit; everything else is derived and gets overwritten.
Anchors point at the model, never at the picture, which is why a question pinned
to `U_REG` survives a redraw.

## One workspace folder

```
pcb-advisor/                 <- the whole workspace, portable, git-friendly
  pcb.py                     <- the one entry point
  config/defaults.json       <- shipped settings, tracked
  config.json                <- yours, local, gitignored. Only what you changed.
  projects/<name>/           <- one folder per design, self-contained
  shared/datasheets/         <- fetched once, sha256'd, reused by every project
  cascade/*.yaml             <- the knowledge graphs
  reference/*.md             <- the same knowledge for a human
  templates/project/         <- what `pcb.py new` copies
  scripts/  ui/  docs/
  .claude/skills/            <- the orchestrating skill
```

Nothing is hardcoded: every path, the port, the default project and the LLM
engine come from the config. `PCB_ADVISOR_HOME` moves your work somewhere else
entirely — your projects follow, the corpus stays with the install. See
[docs/configuration.md](docs/configuration.md).

Projects are listed and switched in the right-hand nav; `+ New project` starts an
empty one. The project is a query parameter (`?project=name`), so two tabs can hold
two designs at once.

## The protocol is the folder

```
projects/<name>/
  project.json      title, status, and THIS board's settings (layers, copper, dT)
  sketch.json       the agreed block diagram
  decisions.jsonl   {ts, node, value, by}       shared by every conversation
  threads.jsonl     {ts, anchor, role, text}    anchored on a node OR a constraint
  chats/
    index.json      the conversations
    <id>.jsonl      one conversation
    <id>.memory.md  what that conversation would otherwise forget
  notes.md          yours; nothing reads it
  sources/          copies of the documents this project actually cited
  design-model.json derived
  artifacts/        derived
shared/datasheets/  shared library: fetched once, sha256'd, reused by every project
```

`project.json` is copied from your `engineering_defaults` when the project is
created, and the copy is what the project uses from then on. Changing a default
later never rewrites a board you already started.

Any agent can drive this. A human can too — open the folder, read the questions,
write answers. That is why the corpus is YAML and Markdown, not prompts.

## Two axes: the timeline and the element

A conversation is chronological. A **thread** is spatial: everything ever said
about one constraint or one decision, hanging on that element, in any session.
Ask "why must the hot loop be small?" and the answer lives on `sw.hotloop` — so
it is still there next month when that constraint comes up again, instead of
buried forty messages back.

The agent anchors on its own whenever it explains or challenges a specific
element, and the student can ask from the badge beside any constraint. Anchors
are validated against the corpus: a mistyped id is refused rather than becoming
an orphan nobody ever sees. Both directions of "open" are tracked — a question
*the student* asked and nobody answered is the one that actually gets lost, and
it is sent back to the agent until it is dealt with. Only the student resolves
a thread.

## Conversations split, the design does not

A project is a board; a session is one conversation about it. `decisions.jsonl`
and `threads.jsonl` stay at project level, so you can open a clean conversation
about the layout without dragging 200 messages about the power supply behind
you — and without losing a single decision. That is the opposite of a chat app,
and it is the point.

Each conversation keeps a **memory** file, bounded at 2000 characters and
rewritten by a separate call every ten messages. It deliberately does not
summarise the decisions — those are sent in full on every turn anyway. It holds
what the transcript loses:

```markdown
## The student's situation
- Enclosure fixed at 40x30 mm. Budget ~$15. Due in 5 weeks.
- Owns 0805 resistors; the lab requires through-hole where possible.
## Ruled out, and why
- LDO (5V→3.3V @600mA): ~1 W dissipated, too much for the enclosure.
## Open promises
- Check the connector's current rating once the part is chosen.
## How they work
- Second-year student — keep explanations short.
```

When it outgrows the limit the engine is asked to **compress** it — merge
duplicates, drop what a later message overturned — not to have it cut off. The
server rebuilds the file from the four headings, so any narration around the
document is dropped rather than counted against the limit. It is a plain `.md`
the student can edit, and a tab in the UI.

## The agent is a pure function

`agent.py` gets `(state, message)` and returns `{reply, actions}`. Whatever the
engine does while it thinks, only those actions change the design, and the
**server** applies them. One writer, and any model or runtime drops in behind
that interface.

## Any engine behind one gateway

`scripts/gateway/` routes a turn to whichever LLM you configured. A provider is a
transport and nothing more — text in, text out — so it knows nothing about
cascades, actions or files:

```bash
python3 pcb.py engines
* claude_code    implemented  ready
  external       implemented  ready
  codex          planned      Codex CLI is registered but not implemented yet
  antigravity    planned      Antigravity is registered but not implemented yet
  openai_api     planned      OpenAI-compatible HTTP API is registered but not implemented yet
```

An engine that lives in the workspace — any CLI agent — also gets a map of the
folders and the scripts, so it can open the datasheet it needs and run
`trace_width.py` instead of estimating. An engine without hands does not get
that map, because telling it to go and read a file makes it invent. Each
provider declares which it is. What it may touch is a setting that ships
working — reads and the calculation scripts allowed, Write and Edit refused —
and `pcb.py tools --clear` hands control back to the CLI's own permissions.

Claude Code routes today. The rest are **registered but not implemented**: they
appear in the table and fail with a message naming the file to write, which is
deliberately better than a provider that half-works. Adding one is a class and a
line in the registry — see [docs/gateway.md](docs/gateway.md).

## Layout

| path | what |
|---|---|
| `pcb.py` | the entry point: init, serve, new, list, show, engines, tools, config, check |
| `config/defaults.json` | every setting, with its shipped value |
| `scripts/workspace.py` | config + paths. Nothing else hardcodes a path. |
| `scripts/project.py` | project lifecycle: template, `project.json`, listing, reset |
| `scripts/gateway/` | LLM routing — one door, any engine |
| `cascade/*.yaml` | the decision graphs — power, mcu, analog |
| `reference/*.md` | the same knowledge, written for a human with no agent |
| `scripts/model.py` | cascade + state → model. Deterministic. |
| `scripts/validate_cascade.py` | provenance contract |
| `scripts/verify_sources.py` | quotes must exist in the real document |
| `scripts/sources.py` | fetch, cache, extract, verify |
| `scripts/trace_width.py` | IPC-2221. A script, never a model answer. |
| `scripts/agent.py` | pure-function agent adapter |
| `scripts/serve.py` | renderer and the only writer |
| `scripts/reset.py` | wipe a project's state |
| `ui/index.html` | the five surfaces |
| `tests/` | the defects that reached a student once |

## Not built

- `stock-check`
- RF cascade (mcu and analog are thin — power is the worked one)
- schematic detail past block level
- pulling the one remaining quote, and authoring a corpus worth citing
- gateway providers other than Claude Code (the slots are registered and documented)
