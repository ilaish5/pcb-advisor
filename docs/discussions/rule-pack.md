# Open discussion: the rule pack

**Status:** open, paused by the user on 2026-09-22. No code was written for it.
**Last repo state when it paused:** `b8f738f`, 109 tests passing, corpus validates.

This file exists so the conversation can be picked up cold. It records what was
measured, what the user decided, what is still undecided, and what would be built
first. It is a working note, not product documentation.

## The question

Where do the design rules come from, who writes them, and on what authority?

It started from a plain question about the shipped corpus — "what are these 35
constraints?" — and turned into a distinction the user drew:

- rules that are **always** true (a return path runs under its outgoing trace; a
  circuit must close), and
- rules that are true **for this project only** (this sensor must survive 85 °C,
  because we decided the box lives on a roof).

The corpus does not distinguish them. Everything is one flat list.

## The user's position

> צריכה להיות חבילת כללים שבאה עם הריפו לכל פרויקט חדש, שרק הכללים נכתבים תוך כדי

Two layers:

| | the shipped pack | the project's own rules |
|---|---|---|
| lives | with the repo, `cascade/` | local, under `projects/<name>/` |
| written by | whoever maintains the pack, in advance | the student or the instructor, during the design |
| changes | when the pack is versioned | mid-design |
| if it is wrong | that is a bug in the tool | that is a decision we changed our mind about |

Earlier in the same discussion the user was explicit that project-specific
material has no business in the repo — it belongs on the local machine.

## What is already true in the code

The *shipping* half is built and tested. `scripts/workspace.py:153`:

```python
_REPO_DIRS = {"cascade_dir", "reference_dir", "templates_dir", "ui_dir"}
```

The corpus stays with the installation; `projects/` and `shared/` follow
`PCB_ADVISOR_HOME`. `tests/test_workspace.py` asserts it
(`test_your_work_follows_the_home_and_the_corpus_stays_with_the_install`).

So the pack already travels with the repo and already applies to every new
project. What does not exist is the **authoring path**: who adds a rule, on what
basis, and with what record.

## What was measured

Re-derive any of this with:

```bash
python3 scripts/validate_cascade.py          # counts by provenance class
git log --reverse --format='%h %ad %an' --date=short   # when the corpus arrived
```

As of `b8f738f`, across `cascade/*.yaml`: **16 nodes, 35 constraints (`locks`).**

| provenance | count |
|---|---|
| `convention` ⚠ | 17 |
| `check_your_part` 🔎 | 10 |
| `standard` 📘 | 3 |
| `datasheet` 📄 | 3 |
| `computed` 📐 | 2 |

Three findings:

1. **A constraint has no author field.** The keys a rule may carry are
   `id, text, source, provenance, calculation, needs_block, verified`. There is
   no `author`, `by`, `reviewed`, `added`, `date` or `approved` — checked against
   `scripts/validate_cascade.py` and the corpus itself. For a `convention` rule
   there is no document, so the source *is* the author's judgement — and the
   corpus records no author. A certificate with no signature.
2. **There is no class for "follows from physics."** The layout rules are all
   `convention` or `check_your_part`. "A return current flows under its outgoing
   trace" is not a convention and not a part property; it follows from mutual
   inductance and can be stated. Neither label fits, so the honest one
   (`convention`) understates it and the student cannot tell it apart from a
   house style.
3. **The whole corpus arrived in the repository's first commit**, authored by
   the repo owner, before any of the work in these sessions. It is marked
   `corpus.status: "demonstration"` in `config/defaults.json` and must not be
   treated as a reviewed baseline.

## The proposal on the table

Three steps, in order. All three are **mechanism, not content** — none of them
depends on the undecided question of who writes the real corpus.

1. **Give a rule a signature.** Add `author`, `basis` and `reviewed` to the rule
   schema, enforced per provenance class in `scripts/validate_cascade.py`, and
   add a `derivation` provenance class for rules that follow from stateable
   physics rather than from a citation. Without this, "official pack" means
   nothing.
2. **Add the project rule layer.** `projects/<name>/rules.jsonl`, append-only,
   server-written (the server stays the only writer), same rule schema,
   `provenance: project`. Rendered separately in the UI, because a failing
   project rule says something different from a failing universal one.
3. **Version the pack.** One field, recorded into a project when it is created,
   so a design can say which pack it was checked against.

Caveat, stated to the user: all 35 current rules would fail step 1 — none has an
author. That is acceptable; they are demonstration material. It is also the point
— step 1 is what separates a rule pack from a list.

## Still undecided (the user has not answered these)

- **Who writes the real corpus, and at what scope** — a full corpus, one narrow
  topic done properly, or leave it as demonstration material.
- **Whether to build the fact model** (rules that check facts about the board
  rather than restating a decision) — full, smallest slice, or not at all.
- **Whether to start at step 1** above. The user's last word was "we'll continue
  another time."

## Standing constraints (do not relitigate)

- The agent may never write to `cascade/`.
- The append-only logs are never edited; the server is the only writer.
- Do not invest in authoring corpus content.
- No markdown renderer in the chat surface — `esc()` is the only XSS guard there.

## Where to pick up

Ask the user whether to start at step 1, and build it. Steps 2 and 3 are only
worth building after 1, because both of them lean on a rule being attributable.
