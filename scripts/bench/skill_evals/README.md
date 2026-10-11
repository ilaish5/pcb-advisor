# Skill evals

One file per runtime skill: `<skill-name>.json`. They live here, not in `runtime/`, so the engine never sees them.
`python pcb.py skills lint` checks the format.

    {"skill": "<name>", "cases": [
      {"id": "<name>-01", "lang": "en"|"he", "question": "...", "expect_skill": true,
       "must": [["kw1", "kw1 alt"], ["kw2"]], "must_not": ["..."], "cite": true|false}]}

- At least 3 cases per skill, at least one in Hebrew (`lang: "he"`). Ids are unique. Questions sound like a real student.
- `must`: every group needs one hit (case-insensitive substring). `must_not` (optional): none may appear.
- `expect_skill`: the question should route to this skill. `cite`: the answer must hold a `{{src:...}}` or "Source:".
