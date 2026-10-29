# Project X for the Meta Global AI Developer Hackathon

An expert does a task in Excel once; the app turns that recording into a guided lesson inside the real
Excel, and Excel itself, not the AI, decides when you got it right.

**This is a work in progress, built during the hackathon (27 Oct - 4 Nov 2026).** This README only
describes what the code already does; each section grows as the parts land. The plan is in
[docs/plan.md](docs/plan.md).

## What works so far

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

(Filled in as each job lands.)

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
