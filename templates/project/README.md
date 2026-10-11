# __TITLE__

A pcb-advisor project. Everything about this design is in this folder.

| file | writable | what |
|---|---|---|
| `project.json` | yes | name, title, and this board's engineering settings |
| `idea.json` | server | goal, agreed items, block diagram, checklist |
| `bom-log.jsonl` | append-only | every applied BOM change `{ts, by, line, changes, before, reason, sources}` |
| `supply-log.jsonl` | append-only | stock and price checks, with supplier and time |
| `proposals.jsonl` | append-only | agent BOM proposals and the student's decisions |
| `library-log.jsonl` | append-only | library parts, model source, verification |
| `bom.json` | **derived** | the BOM, folded from the logs. Do not edit |
| `netlist/<sheet>.json` | server | one schematic sheet, validated against the BOM |
| `chats/<id>.jsonl` | append-only | one conversation per session (`index.json` lists them; an anchor makes it a part conversation) |
| `chats/<id>.memory.md` | rewritten | what that conversation would otherwise forget |
| `notes.md` | yes | yours; nothing reads it |
| `sources/` | yes | documents this project uses (file + `.json` sidecar + `.txt`) |
| `exports/` | derived | BOM exports, the library package |
| `artifacts/`, `design-model.json` | **derived** | rewritten on every run |

The server is the only writer. An agent proposes actions; the server applies them.
