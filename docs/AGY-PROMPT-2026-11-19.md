You are taking over the work on pcb-advisor (a B.Sc. final project, repo at C:\Users\Public\Documents\Altium\pcb-advisor). Read docs/HANDOFF-2026-11-19.md fully before doing anything. Its ground rules are binding.

Goal: bring the replace-consent redesign to main, verified, so the user can do the final manual check.

Steps:
1. Review commit e467505 on branch worktree-agent-a838fcca9483912c4 (diff 4744c1d..e467505; worktree .claude/worktrees/agent-a838fcca9483912c4). Do it read-only first. Focus on scripts/serve.py `_consent`, `_consent_base`, `_replace_consent` and `previous_agent_text`.
   - Probe it with the scripts in logs/handoff-helpers/ (probe*.py, p4.py) plus your own Hebrew and English phrases.
   - It must refuse any negated, hedged, conditional, questioned or stopped replace.
   - It must accept short clear ones such as "כן, תחליף", "yes, replace it", "תשרטט מחדש", "שרטט מחדש את 01 ו-02 באלטיום", and "כן" right after the agent asked about replacing.
   - Draw consent without replace, and the netlist.remove/rename guard, must behave exactly as on 4744c1d.
2. Fix every real finding on that branch, and add a behavioural test for each.
3. Merge into phase0-correctness with `git merge --no-ff`.
4. Run ruff, then the full suite. The full suite takes more than 10 minutes and needs RAM, so run nothing else heavy alongside it. Then fix any failures. Note that runtime/AGENTS.md must stay at 150 lines or fewer.
5. Push with `git push origin phase0-correctness` and `git push origin phase0-correctness:main`.
6. Live check via a second server on port 8940 with headless Chrome (CDP 9444), using logs/handoff-helpers/cdp.py, flow_lib.py and verify-e2e2/.
   - On a project with a drawn sheet, ask in chat to redraw it. The agent must ask a yes/no question. "כן" must then replace the sheet, and a long or hedged message must not.
   - Never restart the 8931 server, never close Altium projects by script, and never accept student decisions.
7. Update docs/STATUS-2026-11-11.md with the 19/11 fixes, then push.
8. Report to the user in short Hebrew, every line starting with a Hebrew word: either that the final manual check can be done, or exactly what is still open.

Rules to keep:
- Commit and push only after the tests pass and the review is done.
- Only generic code goes to GitHub, never project data.
- No JLC orders or uploads.
- Do not run `X2.EXE -REditScript:Stop`.
- If something needs the user, such as Altium being stuck, stop and ask in Hebrew.
