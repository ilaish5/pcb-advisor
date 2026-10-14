# Plan: a JLC session the tool can use (not built)

Status: plan only. Nothing here is built. What is built today (scripts/jlc_upload.py, the DFM guide) is the manual path: the
tool makes the Gerber zip, the student signs in and uploads at jlcdfm.com, exports the PDF, and the tool finds it in
Downloads by itself. This plan removes the middle steps for a student who agrees to a session, and keeps the manual path
as the fallback.

## The idea

A browser profile that belongs to the tool, used only for JLC, that the student signs in to once.

- Location: `<workspace home>/jlc-profile/` (never inside the repo, never the student's own Edge or Chrome profile).
- Sign in: a button (Settings, and the DFM guide step 2) opens a visible Edge window on that profile at https://jlcdfm.com.
  The student types their own credentials and closes the window. The tool sees only "is the session live" afterwards.
- Use: the same headless Edge over CDP that `scripts/jlc_live.py` already drives, started on that profile. Cookies stay
  inside the profile folder; tool code never reads them.
- Then "Check at JLC" in the DFM view uploads `exports/<project>_gerbers.zip`, waits for the analysis, exports the report,
  and ingests it exactly like a PDF from Downloads (`dfm.ingest_pdf`, source "jlc-session").
- Sign out = delete the profile folder.

## What to explore first (read only, with the student's session)

From `docs/bench-runs/jlc-live-2026-10-14/report.md` (an anonymous run against the synthetic test board):

1. `getAll` answers the login state (`{"login": false}` without a session). This is the session check; poll it, never retry a login.
2. `pcbDfm/uploadGerber` answers HTTP 500 without a session, then the page redirects to passport.jlcpcb.com. With a session:
   what it returns, and which calls the page makes next to start and read the analysis (record the network traffic of one
   run by hand first). If the result arrives as JSON, the findings can be read as data and the picture-only PDF (one
   tall JPEG, no text layer) is no longer the only source of findings.
3. `pcbDfm/getDfmConfigFile` returns JLC's default rule template (38 checks with thresholds) without a session. Already
   used for the rule comparison; check whether a logged-in call returns the template for the chosen options.
4. The PDF export (toolbar icon): is it built in the page from a canvas (that would explain the single embedded image)
   or fetched from the server? If it is built in the page, reading the result data is better than saving the PDF.
5. Quote page: `file/uploadGerber` then `order/analysisGerber` work without an account ("Detected 2 layer board of
   50x50mm"). A free pre-check that needs no session at all: upload the zip, show what JLC detects (layers, size). Build this
   first if the student only wants a quick sanity check.
6. Assembly: `customer/customerInfo` answers code 460 ("automatically logged out") and the passport login without a
   session. Find the BOM and CPL upload calls and the matching page, behind the session.

## How it would show up (ui-redesign.md section 0: UI and programmatic)

- UI: Settings "JLC session" (Sign in, Signed in as seen by the site, Sign out); DFM guide step 2 and 3 become one button
  "Check at JLC" when a session is live; progress as a quiet line, not a modal.
- HTTP: `GET /api/jlc/session`, `POST /api/jlc/session/login-window`, `DELETE /api/jlc/session`, `POST /api/jlc/check`
  (starts a job, returns an id), `GET /api/jlc/check?id=` (progress and result).
- CLI: `python scripts/dfm.py jlc-check <project>` (the Bash allow-list in config/defaults.json would need the new form).
- Agent actions: `jlc.check` (start, only on the student's request in chat). Results come back as state, like `jlc.pickup`.
- The agent never opens the login window for the student without being asked, and never sees the session.

## Privacy and safety rules (non-negotiable)

1. Dedicated profile only. The tool never reads, copies or lists another browser profile, cookie store or password store.
2. The tool never types, stores, logs or sends credentials. Only the student signs in, in a visible window. No credentials in
   config, logs, transcripts or agent context. The agent is told never to ask for them (the skill already says so).
3. The profile folder is a live session of the student's account: treat it like a password. Outside the repo, git-ignored,
   excluded from exports, packs and backups, never synced. "Sign out" deletes it. Say this on the sign-in screen.
4. Only the project's own files leave the machine: `exports/<project>_gerbers.zip` and the BOM and CPL exports. Only to
   jlcdfm.com and jlcpcb.com (with passport.jlcpcb.com for the login), only on a click or an explicit request in chat, never
   on a timer, a window focus or a poll.
5. Stop before anything that costs money or commits to an order: no cart, no order, no address or payment pages. A
   host and path allow-list in the driver enforces it, not just the instructions.
6. One job at a time, no crawling, no use of other people's data. Read JLC's terms before building; if they forbid
   automation, ship only "assist" mode (open the page, the student does the clicks, the tool picks up the result).
7. An expired session (code 460, redirect to passport) is shown as "Sign in again". Never retried, never worked around.
8. Logs keep host, path and status only, no request bodies. Screenshots are only of the project's own result.
9. Everything offline-testable stays offline: record one real run as a fixture (responses with ids removed), test the
   driver against a local stub server. No test touches the network or a real profile.

## Order of work

1. Walk one real run by hand with the network recorder (point 2 above); write what each call needs and returns.
2. The anonymous pre-check (point 5): no session, smallest risk, useful on its own.
3. Profile and sign-in window, session status (`getAll`), sign out.
4. The DFM upload and report capture (points 2 to 4), then assembly (point 6).
5. UI, API, CLI and agent action together for each step, with tests against the stub.
