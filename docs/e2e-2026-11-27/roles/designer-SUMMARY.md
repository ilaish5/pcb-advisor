# Designer SUMMARY - UI/UX over all stages (0-7), Final-E2E-4L overnight run

Scope as agreed: only what the student sees in the browser. Board engineering and the student's choices are not scored. Detail and screenshot evidence are in `designer-S1.md` ... `designer-S7.md`.

## Overall UI/UX score: 5.4 / 10

| Stage | Score | One-line reason |
|---|---|---|
| 0-1 Start, Idea | 6 | Clear flow and Confirm gate; stale description/layers/draft state after chat edits |
| 2 BOM | 5.5 | Agent cards work; silent waits, numbers that change by themselves, qty confusion |
| 3 Library | 5.5 | Good previews; green "Built / nothing to verify" over unverified pins; "tool cannot do this" not stated |
| 4 Schematic | 5 | Blank page start, unreadable preview, 20-minute silent build with no end message |
| 5 Layout | 5.5 | Honest placement cards; "2 vs 4 layers" mismatch; board hard to judge |
| 6 Rules / Route / DRC | 5 | 6-minute silent route, dead-end rejection, green over 421, every fix manual |
| 7 Outputs | 5 | No readiness summary, deliverables below the fold, no README, green dot with risks open |

What is good and should be kept: one-click Altium step buttons with Stop and "cannot be cut short" text; Replace / Keep it two-button consent; Revoke on checked/accepted pins; DFM split "Checked by you" vs "Accepted risks"; toast with Download after export; cards in chat that can be approved in one click; the app admitting limits honestly (placement distance table, "I can't change layers").

What drags the score: the product is honest in words but the colors, counts and Next buttons often say something else, and long steps give no sign of life.

## Top 10 fixes, ranked (generic, each with ui/ files)

1. **Named phases and honest estimates for every long wait, for both engines and Altium steps; survive reload; always end with a message.** The biggest recurring pain (15 entries: 20-minute silent build, 6-minute routes, "Working... N s"). Show phase + typical time + "you can leave this page"; a build that ends without a message is a defect. Files: `ui/js/views/previews.js` (PV_STEPS :330-340 `busy`, :575-600), `ui/js/views/bom.js` (:151 `libBusy`), `ui/js/chat.js` (waiting row), `ui/js/kit.js` (progress component).
2. **Tone comes from findings, never from "the step ran".** Green only when nothing is open: no check mark over 421 DRC, no "Pins: nothing to verify" fall-through, no green Outputs dot with U1 unchecked, "applied" with skipped rules is a warning. Files: `ui/js/views/previews.js` (:351-367, :587), `ui/js/views/pages.js` (:70-78), `ui/js/shell.js` (:101-104), `ui/js/chat.js` (:451, :522-545).
3. **Findings panel with a per-item state: Tool can fix (button) / You fix in Altium (numbered steps + "Done, check again") / Accept with reason.** Replaces "fix it in Altium" text everywhere (DRC groups, pin checks, "tool cannot do this" answers, library edits). The sidebar badge counts only blocking items. Reuse the DFM "Accepted risks" component. Files: `ui/js/views/previews.js` (:481-484, :536), `ui/js/views/rules.js` (:85), `ui/js/views/pins.js`, `ui/js/views/pages.js` (DFM), `ui/js/shell.js` (badge).
4. **One source of truth on screen: page, chat and numbers must agree or say they are stale.** Idea description/layers/frame title after chat edits, "confirmed" after Save, header totals that change while reading, "2 vs 4 copper layers", BOM "Accepted risk" vs DFM "Checked by you", Rules "Drawn" vs "Wanted", chat engine label per message. After any agent change: re-render everything from the saved draft and mark what is not yet saved. Files: `ui/js/views/idea.js` (:132-171, :221-240), `ui/js/views/bom.js` (:54-81, :456-472), `ui/js/views/rules.js`, `ui/js/chat.js` (:855).
5. **"Next" and chips follow the page and the state, not the stage order.** Layout says "Next: Rules" after rules were applied; Outputs shows Layout chips; chip "Review this sheet" sits idle during a 5-minute review. Add a "Before you order" card (Files / Parts / Board, one next action each) at the top of Outputs. Files: `ui/js/chat.js` (:588, :608-617), `ui/js/shell.js` (:109-116 `stageNextBtn`), `ui/js/views/outputs.js` (:250-317).
6. **Chat is for short answers and one-click decisions.** Long tables and 40-line answers move to a page with a link; agent questions get Yes / No quick-reply buttons that run the action (consent mismatch: button vs typed "yes" - C105/C98); internal text never shown ("bom.propose", "student_said", "chat.ask", file names like rules.py); stacked orange paragraphs of warnings are not pasted into the chat. Files: `ui/js/chat.js` (:451, :522-545, :588), `ui/styles/chat.css`.
7. **Previews a student can judge:** readable schematic (net names, zoom to a net), pin-1 / pad names / courtyard legend on footprints, DRC markers on the board with "Show problems", highlight of the part when the chat names it. Files: `ui/js/views/modelpreview.js` (:150, :159), `ui/js/views/previews.js` (pcb/sch renderers, Layers menu :515), `ui/js/viewer.js`.
8. **Decision ledger the agent must carry over.** Contradictions and lost decisions between answers (D1 "short", disable the 10 mil rule, keep-outs, risks missing from notes.md, qty lost after Approve) cost the most trust. Show "Decisions so far" (from the Idea draft) in the page and chat footer; the agent edits that list, not free text. Files: `ui/js/views/idea.js` (requirements list), `ui/js/chat.js`, plus agent prompt (server).
9. **Deliverables are findable and complete:** Outputs files table first, full path + Open folder + Copy path, one "Download JLC package", Export menu grouped by purpose, previewable Order note (README) row. Files: `ui/js/views/outputs.js` (:132-163, :250-261, :285), `ui/js/viewer.js`.
10. **First minutes:** "New project" visible without scrolling 30 old projects, no 45-second freeze after click, a clear first step on empty pages (Schematic starts blank with only "Main.SchDoc"), and the black "not linked to an Altium project" banner fixed so it does not show on a linked project. Files: `ui/js/shell.js` (:164 menu), `ui/js/views/pages.js` (:363), `ui/js/views/previews.js` (empty schematic state).

## Student confusion entries grouped by theme (138 entries: C1-C137 plus C55b)

| Theme | Count | Entries |
|---|---|---|
| B Page, chat and numbers disagree (stale or contradicting state) | 19 | C2 C3 C12 C13 C14 C16 C27 C28 C29 C32 C48 C77 C84 C96 C99 C109 C112 C125 C128 |
| A Silent / long waits, no progress or no end message | 15 | C5 C7 C10 C22 C37 C41 C42 C63 C69 C71 C78 C79 C85 C86 C114 |
| D Tool cannot do it; fix is manual in Altium; no tracked state or accept | 14 | C57 C66 C81 C82 C100 C104 C113 C116 C119 C120 C121 C122 C124 C126 |
| F Agent answers contradict earlier ones or drop decisions | 13 | C24 C30 C33 C35 C36 C47 C56 C72 C73 C89 C130 C135 C136 |
| G Previews cannot be inspected or judged by a student | 13 | C51 C52 C53 C54 C55 C55b C59 C60 C61 C65 C70 C80 C102 |
| E Chat format: long answers, tables, internal leaks, consent mismatch | 10 | C9 C18 C19 C20 C31 C34 C67 C98 C105 C108 |
| H Start-up, navigation, first use | 7 | C1 C4 C6 C15 C17 C21 C68 |
| I Rules, route result, numbers that need explaining | 7 | C39 C110 C111 C115 C117 C123 C127 |
| C Green / "done" over unverified, failed or not-gated state | 6 | C50 C90 C118 C131 C132 C137 |
| J Missing output / export features | 2 | C133 C134 |
| K Engineering content, questions answered well, positives (not UI findings) | 32 | C8 C11 C23 C25 C26 C38 C40 C43 C44 C45 C46 C49 C58 C62 C64 C74 C75 C76 C83 C87 C88 C91 C92 C93 C94 C95 C97 C101 C103 C106 C107 C129 |

Reading the table: 106 of 138 entries (77 %) are UI/UX themes A-J; the first five themes (B, A, D, F, G) alone are 74. Each ranked fix above maps to a theme: fix 1 -> A; 2 -> C and I; 3 -> D; 4 -> B; 5 -> B, C, J; 6 -> E; 7 -> G; 8 -> F; 9 -> J; 10 -> H. Theme K entries are mostly the student asking engineering questions or noting that something worked (C83, C87, C106, C129 are explicit positives).

## Out of scope (not scored)
Board engineering (USB 90 ohm pair, thin power tracks, keep-outs landing as copper, mask slivers, decap distance, layer stack, J3 edge), the student's own choices (not doing manual Altium, not confirming U1), and agent text content as engineering. The UI requirement from all of them is the same: a tool limit or an open risk must be visible on the page before the student discovers it by asking.
