# Joining up, in parallel parts (30 Oct 2026)

Plan 06 ([2026-10-29-06-integration-and-ship.md](2026-10-29-06-integration-and-ship.md)) split into parts that
run at the same time, each in its own session and its own copy of the project. A part joins `main` only when
Ranvir says so, and the full suite runs after each join. Plan 06's Global Constraints apply to every part.

## Who this is for

The learner, today, can only see each piece on its own: the screens on sample data, Excel and VS Code driven
by tests. When these parts are done, they start one program, see their home screen with their streak and
courses, pick the monthly budget, and the panel docks on the right while Excel fills the rest. The mascot
points at the real cell, steps tick when Excel really changes, and closing and reopening carries on where
they were. Lessons on the shelf are proven ones only.

## The handover notes

Each building session wrote what the joined program must do. Read the "plan 06" section of each:

- `C:\Users\RANVIR\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\side-session-notes\local_77794069-fabf-4bab-bddd-533b9caacfa1\ui-screens-handover.md`
- `...\excel-handover.md`, `...\factory-handover.md`, `...\vscode-handover.md` (same folder)

## Part A: the program (new session)

Plan 06 Tasks 2, 3, 4 and 5: the progress store, the library, the real backend, and starting with
`python -m app` with the panel docked. Also every backend need in the four handover notes, among them:
`not_yet` on every wrong try, YouTube-only `videoUrl`, a go-to-step action, a dismiss action for the
factory, made lessons appearing in `courses`, re-checking the key after `copyKeySetup`, the overlay warm-up,
closing an app off the screens' thread (Excel can take 5 s), and showing VS Code's `close_reason`.

- Owns: `app/core/progress.py`, `app/core/library.py`, `lessons/courses.json`, `app/integration/`,
  `app/main.py`, `app/__main__.py`, `tests/integration/`. May change `app/ui/` only to add the actions and
  lesson fields the backend needs.
- Never changes: `app/excel/`, `app/vscode/`, `app/factory/`, `app/meta/`, `app/coach/`, `extensions/`.
  Something needed there goes in its handover note for the joining session.
- The vision fallback is not this part's job: the Excel plug-in wires its own (Part C), so the backend
  needs nothing for it.
- Task 5's live probe opens real Excel: only after Ranvir says go, with the memory check first (at least
  3 GB free) and the list of sessions to close.

## Part B: the video shortlist (new session)

Plan 06 Task 1, for Excel only: VS Code lessons are written by hand and never made from videos (decision of
29 Oct). At least 12 Excel tutorials, ranked, the top 8 for the library and a Creative Commons pair for the
demo, each checked against what the Excel checks and the factory's everyday-formula list allow.

- Owns: `docs/video-shortlist.md`. Changes nothing else.
- Ends by asking Ranvir to approve or strike lines, and records his answer in the file.

## Part C: Excel's macro guard and vision fallback (the Excel session, as a follow-up)

- Every Excel the plug-in opens has macros forced off (`Application.AutomationSecurity = 3` before any
  workbook opens), with a test; and a check that the macro editor's window is not owned by Excel's main
  window, so the tester's clicks there stay refused (factory handover, "Excel requests").
- Plan 06 Task 6 Step 2, the vision fallback: Muse Spark on a screenshot of the window through `MetaClient`
  (label `point_fallback`), its answer on the 0 to 1000 grid turned into pixels, used only when the plug-in's
  UI Automation agreement rule accepts it. `ExcelPlugin` wires it into each session itself when a Meta key is
  found, and leaves it off when there is none, so the core interface does not change. Tested with a fake
  Meta client; the live call waits for Ranvir's key.
- Owns: `app/excel/`, `tests/excel/`. Reads `app/meta/` and does not change it.

## Here (the joining session)

- Join the VS Code session's last fix (`8bacfbe`, real VS Code runs) when Ranvir says.
- If Ranvir confirms the program itself is called Mentora: rename it everywhere a learner sees it, after
  that join.
- Join each part as it finishes, run the full suite, push `main` with the secret scan.

## Waiting on Ranvir

- The Meta key: plan 06 Tasks 7 and 8 (the shelf from videos, tips and Ask) and every live Meta call.
- Go for live runs in real Excel (memory check first).
- Approving the video shortlist.
