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

Each part below is built and tested on its own. Joining them into one program is the next step, and no
lesson is proven yet.

- The screens ([app/ui/](app/ui/)): the home screen, the lesson panel and the flying mascot pointer. See
  them with sample data: `python -m app.ui.app --demo first_run`.
- The Excel plug-in ([app/excel/](app/excel/)): opens its own copy of Excel, reads the sheet after every
  change, checks each step with fixed rules, and finds cells and ribbon buttons on the screen.
- The lesson factory ([app/factory/](app/factory/)): `python -m app.factory make <video link>` downloads a
  tutorial, has Meta's models write the lesson, proves each step's check is false before the step and true
  after it, and has Meta's computer-use agent play the lesson as a learner. It has not run against Meta's
  live service yet. The agent tests Excel lessons only: in VS Code it could reach the terminal, so it never
  tests VS Code lessons.
- The VS Code plug-in ([app/vscode/](app/vscode/)) with its add-on inside VS Code
  ([extensions/vscode/](extensions/vscode/)).
- Three hand-written lessons ([lessons/](lessons/)): a monthly budget in Excel, and two beginner
  Python lessons in VS Code.
- A guard that refuses any commit or push holding an API key or a `.env` file
  ([tools/secret_scan.py](tools/secret_scan.py), wired in by `git config core.hooksPath tools/hooks`).
- The Meta key is read from the `META_API_KEY` environment variable, or from the user's saved Windows
  settings when the program was started before the key was saved ([app/meta/key.py](app/meta/key.py)).

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
