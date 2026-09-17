# pcb-advisor

A design-considerations tool for students. You describe what you want to build;
it sketches a block diagram and asks whether that's what you meant; then it walks
you down a decision cascade. Every choice you make appends the constraints that
choice just locked in — each one labelled with **how we know it**.

```bash
python3 scripts/serve.py demo 8931          # then open http://localhost:8931
python3 scripts/serve.py demo 8931 external # drive it from your own agent instead
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
| 📐 computed | a script produced it | the calculation |
| 📘 standard | a published standard says it | document + locator |
| 📄 datasheet | a specific document says it | document + locator; **url + verbatim quote** to count as verified |
| ⚠ convention | craft, no citable source | must say so out loud |

Two scripts enforce this, and both belong in CI:

- `validate_cascade.py` — a constraint must declare its provenance and carry what
  that class requires. A bare `source: practice` string no longer passes as a citation.
- `verify_sources.py` — every quote marked verified must be findable, **verbatim**,
  in the cached document. Fabricate a quote and it fails.

```
$ python3 scripts/verify_sources.py
  ok    sw.keepaway  <- slyt614.pdf
  ok    sw.cin       <- slyt614.pdf
  2 verified, 0 failed, 31 unverified (citation claimed, quote not pulled yet)
```

That last number is the corpus being honest about its own state. Those 31 were
written from memory and are shown in the UI as `unverified` until someone pulls
the real quote.

## The one rule

```
decisions.jsonl ─┐
threads.jsonl    ├─► design-model.json ─┬─► blocks.svg
chat.jsonl       │                      ├─► the graph
sketch.json     ─┘                      └─► the decisions table
```

Only those four are writable, and three are append-only. Everything else is derived
and gets overwritten. Anchors point at the model, never at the picture, which is why
a question pinned to `U_REG` survives a redraw.

## One workspace folder

```
pcb-advisor/                 <- the whole workspace, portable, git-friendly
  projects/<name>/           <- one folder per design, self-contained
  shared/datasheets/         <- fetched once, sha256'd, reused by every project
  cascade/*.yaml             <- the knowledge graphs
  reference/*.md             <- the same knowledge for a human
  .claude/skills/            <- the orchestrating skill
  scripts/  ui/
```

Projects are listed and switched in the right-hand nav; `+ New project` starts an
empty one. The project is a query parameter (`?project=name`), so two tabs can hold
two designs at once.

## The protocol is the folder

```
projects/<name>/
  sketch.json       the agreed block diagram
  decisions.jsonl   {ts, node, value, by}
  threads.jsonl     {ts, anchor, role, text}   anchored on a node OR a constraint
  chat.jsonl        the conversation
  sources/          copies of the documents this project actually cited
  design-model.json derived
  artifacts/        derived
sources/cache/      shared library: fetched once, sha256'd, reused by every project
```

Any agent can drive this. A human can too — open the folder, read the questions,
write answers. That is why the corpus is YAML and Markdown, not prompts.

## The agent is a pure function

`agent.py` gets `(state, message)` and returns `{reply, actions}`. It has no file
access and no tools; the **server** applies the actions. One writer, and any model
or runtime drops in behind that interface. Backends: `claude` (spawns `claude -p`)
and `external` (an agent elsewhere is driving the folder).

## Layout

| path | what |
|---|---|
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

## Not built

- `stock-check`
- RF cascade (mcu and analog are thin — power is the worked one)
- schematic detail past block level
- pulling the remaining 31 quotes
