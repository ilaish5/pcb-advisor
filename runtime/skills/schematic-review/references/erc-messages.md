# Altium ERC / compile messages (AD20 wording; newer versions may differ slightly)

Where: Project > Compile, then the Messages panel. What counts as an error is set in Project Options > Error Reporting and the
Connection Matrix (`course/ad20-essentials/m09-compiling.en.md` 9.3-9.4).

| Message | Usual cause | Fix |
|---|---|---|
| Net X has no driving source | Net has only Input/Passive pins; library pin types wrong (passives typed Input) | Fix pin types in the library; or add the real source; No-ERC only when deliberate |
| Floating input pins / Unconnected pin | Pin not wired | Wire it, or follow the datasheet (NC, tie high/low); No-ERC cross if deliberate |
| Net has only one pin | A label that exists once, or a typo in a label name | Search the net name; fix the spelling; same name = same net |
| Duplicate designators | Two parts with one reference | Tools > Annotate (reset duplicates, then annotate) |
| Off grid | Part or label not on the electrical grid | Keep the snap grid on; move or align; check the sheet grid in Document Options |
| Nets with multiple names | Two labels or a port and a label on one wire | Keep one name per wire; delete the extra label |
| Footprint Not Found (at ECO) | Footprint missing from the installed libraries | Add the library to the project or fix the model link |
| Sheet entry / port mismatch | Hierarchy ports differ between sheet symbol and child sheet | Design > Synchronize Sheet Entries and Ports |

- Never suppress a message before you know the cause.
- After a library fix, placed parts update only through Tools > Update From Libraries.
- Messages that mention objects that no longer exist mean a stale compiled model: close and reopen the project, compile again.
- Cite as `{{src:m09-compiling.en.md|9.4 Running the Compiler}}`; menu names are AD20, say so when unsure.
