# __TITLE__

A pcb-advisor project. Everything about this design is in this folder.

| file | writable | what |
|---|---|---|
| `project.json` | yes | name, title, and this board's engineering settings |
| `sketch.json` | yes | the agreed block diagram |
| `decisions.jsonl` | append-only | `{ts, node, value, by}` — shared by every conversation |
| `threads.jsonl` | append-only | `{ts, anchor, role, text}` — anchored on a node or a constraint |
| `chats/<id>.jsonl` | append-only | one conversation per session |
| `chats/<id>.memory.md` | rewritten | what that conversation would otherwise forget |
| `chats/index.json` | yes | the list of conversations |
| `notes.md` | yes | yours; nothing reads it |
| `sources/` | yes | copies of the documents this project actually cited |
| `design-model.json` | **derived** | rewritten on every run — do not edit |
| `artifacts/` | **derived** | rewritten on every run — do not edit |

The server is the only writer. An agent proposes actions; the server applies
them. You can also just edit the writable files by hand.
