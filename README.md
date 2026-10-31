# Mentora

Mentora turns a YouTube tutorial into a hands-on lesson inside the real app (Excel first, then VS Code):
a mascot points at the real cell or button, and fixed checks that read the app itself, not the AI, decide
when each step is done.

Built for the Meta Global AI Developer Hackathon. **This is a work in progress, built during the hackathon
(27 Oct - 4 Nov 2026).** This README only describes what the code already does; each section grows as the
parts land. The design is in
[docs/superpowers/specs/2026-10-29-tutorial-to-practice-design.md](docs/superpowers/specs/2026-10-29-tutorial-to-practice-design.md)
and the build plans are in [docs/superpowers/plans/](docs/superpowers/plans/).

## What works so far

Each part below is built and tested, and the program now joins them. In real Excel, clicking the budget
lesson on the home screen opens it with Excel in front, the lesson panel docked beside it, and the
mascot on empty cells beside the first step's cells. One lesson is proven so far: "Your first Python
program", in VS Code.

- The program ([app/main.py](app/main.py), [app/integration/](app/integration/)): `python -m app` opens
  the home screen with your streak, points and courses. Opening a lesson hides home, docks the lesson
  panel on the right and puts the app beside it. Your progress stays on your computer, in
  `%LOCALAPPDATA%\mentora\`. Only lessons that passed their proof and test are on the shelf (a VS Code
  lesson skips the test, so its proof is enough), so today the shelf holds only "Your first Python
  program" unless the developer switch `MENTORA_SHOW_UNPROVEN=1` is set, which shows the others marked
  "not proven yet". For a cell step, the mascot and its words stay on the sheet's empty cells,
  off Excel's ribbon, formula bar and Name Box, so the button a step needs stays in view; only when the
  visible sheet has no room for them do they go elsewhere on the screen. Tried in real Excel on the
  budget lesson's first step; its other steps are checked by tests only.
- The screens ([app/ui/](app/ui/)): the home screen, the lesson panel and the flying mascot pointer. See
  them with sample data: `python -m app.ui.app --demo first_run`.
- The Excel plug-in ([app/excel/](app/excel/)): opens its own copy of Excel, reads the sheet after every
  change, checks each step with fixed rules, and finds cells and ribbon buttons on the screen. Macros are
  forced off in every Excel it opens, so no lesson file can run one (checked by tests; the check in real
  Excel is still to run). When a Meta key is saved, Muse Spark can point at a ribbon button that Windows
  UI Automation can't find, and the arrow uses that answer only if UI Automation then finds a button of
  that name there. That has not run against Meta's live service yet.
- A shortlist of 18 Creative Commons Excel tutorials on YouTube, 8 of them approved for the library
  ([docs/video-shortlist.md](docs/video-shortlist.md)). No lesson has been made from them yet.
- The lesson factory ([app/factory/](app/factory/)): `python -m app.factory make <video link>` downloads a
  tutorial, has Meta's models write the lesson, proves each step's check is false before the step and true
  after it, and has Meta's computer-use agent play the lesson as a learner. It has not run against Meta's
  live service yet. The agent tests Excel lessons only: in VS Code it could reach the terminal, so it never
  tests VS Code lessons.
- The VS Code plug-in ([app/vscode/](app/vscode/)) with its add-on inside VS Code
  ([extensions/vscode/](extensions/vscode/)). Tried in real VS Code on 31 Oct 2026: clicking "Your first
  Python program" on the home screen opens VS Code beside the lesson panel. Until the lesson's folder is
  trusted (VS Code asks once per folder), the mascot points at VS Code's "Trust Folder & Continue" button;
  after that, on step 1, at the Explorer's New File button. Steps 1 to 5 ticked, and a wrong file name
  showed its "Not yet", when a script did each step through the add-on. Not yet tried in real VS Code:
  the run step (6) with the folder trusted, steps done by hand, and "Your first app with Meta's AI",
  which needs a Meta key.
- Three hand-written lessons ([lessons/](lessons/)): a monthly budget in Excel, and two beginner
  Python lessons in VS Code.
- A guard that refuses any commit or push holding an API key or a `.env` file
  ([tools/secret_scan.py](tools/secret_scan.py), wired in by `git config core.hooksPath tools/hooks`).
- The Meta key is read from the `META_API_KEY` environment variable, or from the user's saved Windows
  settings when the program was started before the key was saved ([app/meta/key.py](app/meta/key.py)).
- A switch for showing Mentora without a Meta key ([app/ai.py](app/ai.py), [app/claude/](app/claude/)):
  with `MENTORA_AI=claude`, the Ask box, the tips and the pointing fallback ask Claude (Opus 5.5) instead of
  Muse Spark, using the `ANTHROPIC_API_KEY` key, with its own call log and a $20 spending stop. Meta stays
  the default, and the lesson factory always uses Meta. One real Ask box question has been answered by
  Claude (in 4.4 s); the pointing fallback on Claude has run only in tests.

## Built during the hackathon (27 Oct - 4 Nov 2026)

Everything in this repository, except the pieces listed in the next section. The commit history is the
record: this repository was started on 29 Oct 2026.

## Brought in from before the hackathon

Some plain helpers (reading Excel without freezing it, finding buttons with Windows UI Automation, window
and screen helpers) are adapted from my earlier private project, Project X. Each one was reshaped to fit
here and landed in its own commit whose message starts with `Adapted from Project X :`.

| Piece here | Adapted from (old path) | Commit |
|---|---|---|
| `app/excel/busy.py`: Excel's busy signals | `sidecar/checks/excel_reader.py` (`is_busy`, `RETRYABLE_HRESULTS`) | 357f98b |
| `app/excel/formula.py`: formula reading | `sidecar/checks/formula.py` | ea0dc53 |
| `app/excel/com_thread.py`: the COM thread's sleeping message pump | `sidecar/adapters/excel.py` (`_pump`, `submit`, `_drain_work`) | dde4410 |

## Which Meta model does which job

(Filled in once the parts are joined and have run against Meta's live service.)

## Running it

Windows 11 with Microsoft Excel (desktop) and Python 3.12.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
git config core.hooksPath tools/hooks
```

Save your Meta key once, in your own PowerShell window:

```powershell
[Environment]::SetEnvironmentVariable("META_API_KEY", "<your key>", "User")
```

Start Mentora:

```powershell
.venv\Scripts\python -m app
```

To have Claude answer the Ask box and tips instead of Meta, save `ANTHROPIC_API_KEY` the same way, then:

```powershell
$env:MENTORA_AI = "claude"; .venv\Scripts\python -m app
```
