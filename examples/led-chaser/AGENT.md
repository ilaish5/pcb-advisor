# PCB-Advisor project

You are working on a PCB Advisor project in this directory. To understand where it stands:
- `idea.json`: the goal, the agreed items, the block diagram, the checklist
- `bom.json`: the BOM (DERIVED from `bom-log.jsonl`, `supply-log.jsonl` and `library-log.jsonl`; never edit)
- `proposals.jsonl`: what was proposed, and what the student decided
- `netlist/<sheet>.json`: the schematic sheets
- `chats/`: the conversations
- `notes.md`: freeform notes
Changes go through the action channel (see `runtime/AGENTS.md` in the install); the server is the only writer.
