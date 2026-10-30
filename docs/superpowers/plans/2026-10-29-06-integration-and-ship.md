# Integration and ship Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Join the streams into one program a learner starts with `python -m app`, fill the shelf with
proven and tested lessons, and ship the README, the 3-minute video and the submission on time.

**Architecture:** `app/integration/backend.py` is the real `ScreenBackend`: it owns the library, the
progress store, the open `AppSession` and its `LessonRun`, and turns runner events into the screen states
the UI draws. Nothing in it draws or touches Excel directly. `app/main.py` starts Qt, the backend and the
three windows, and docks the panel beside the app.

**Tech Stack:** everything above; no new packages.

**Spec:** `docs/superpowers/specs/2026-10-29-tutorial-to-practice-design.md` (sections 2, 3, 4, 5.5, 8)

## Global Constraints

See `2026-10-29-00-overview.md`, "Global Constraints". Also:
- Progress lives only in `%LOCALAPPDATA%\mentora\` (`progress.json`, `attempts.jsonl`, `work\`).
- A lesson is on the shelf only when `shelf_badge(lesson)` is not None. A developer switch
  `MENTORA_SHOW_UNPROVEN=1` shows unproven lessons marked "not proven yet"; it is never on in recordings.
- No guilt copy: a broken streak resets quietly; nothing is ever taken away for a mistake.
- Merges into `main` only when Ranvir says so; the full suite runs after each merge (paste it).
- Ranvir records his voice, posts on X, fills in the submission form and asks the Discord questions.
  Claude never posts, sends or submits.

## Review Focus

1. The learner closes Excel mid-lesson → the panel shows "Excel was closed" with Reopen; reopening resumes
   at the same step (Task 4 `test_app_closed_shows_reopen_and_reopen_resumes`).
2. The learner comes back tomorrow → Continue reopens their saved copy and the done steps tick quietly,
   with no banners or sounds (Task 4 `test_resuming_ticks_done_steps_quietly`).
3. `progress.json` is broken or half-written (power cut) → it is set aside as `progress.broken-<time>.json`
   and the learner starts with an empty record; nothing crashes (Task 2 `test_a_broken_progress_file_is_set_aside`).
4. A day is skipped → the streak quietly restarts at 1 next time, with no message about losing it
   (Task 2 `test_streak_counts_days_in_a_row_without_guilt`).
5. Continue is clicked twice, or a lesson is opened while one is open → one app, one session
   (Task 4 `test_opening_twice_opens_one_app`).

---

### Task 1: The video shortlist (this session, Thu 29 – Fri 30)

**Files:**
- Create: `docs/video-shortlist.md`

- [ ] **Step 1:** Find at least 12 candidate Excel tutorials and 3 Python-beginner ones: under 15 minutes,
  one task each, Creative Commons first (YouTube's licence filter), a sheet that fits 920 px, and tasks the
  Excel check menu covers (plan 03 Task 4). For each: title, creator, channel link, video link, licence,
  length, what the learner makes, the check kinds it needs, and any risk (fast talking, a sheet too wide,
  a feature outside the menu).
- [ ] **Step 2:** Rank them; mark the top 8 for the library and 2 for the demo (the demo pair must be
  Creative Commons).
- [ ] **Step 3: Commit** — `git commit -m "Add the shortlist of tutorial videos for Ranvir to approve"`
- [ ] **Step 4:** Ask Ranvir to approve or strike lines. Record his answer in the file.

### Task 2: The progress store

**Files:**
- Create: `app/core/progress.py`
- Test: `tests/integration/test_progress.py`

**Interfaces:**
- `Progress(root: Path, *, today: Callable[[], date] = date.today)` with `name: str`, `daily_goal: int = 30`,
  `streak() -> int`, `points_today() -> int`, `lesson_state(lesson_id) -> LessonProgress`
  (`LessonProgress(step: int, done: bool, best_seconds: float | None)`),
  `step_passed(lesson_id, index, points)`, `lesson_done(lesson_id, done: LessonDone)`,
  `log_attempt(lesson_id, record: StepRecord)`, `attempts() -> list[StepRecord]`, `save()`.
- `progress.json` is written atomically (temp file then replace). Streak: days in a row with at least one
  step passed, counted up to today or yesterday; otherwise 0, shown as nothing (no "lost" message).

- [ ] **Step 1: Write the failing tests**

```python
def test_points_and_steps_survive_a_restart(tmp_path): ...
def test_streak_counts_days_in_a_row_without_guilt(tmp_path): ...   # 3 days -> 3; skip a day -> 0 -> next step 1
def test_a_broken_progress_file_is_set_aside(tmp_path): ...
def test_attempts_are_kept_in_order(tmp_path): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Commit** — `git commit -m "Keep the learner's progress, points, streak and attempts on the laptop, safe from half-written files"`

### Task 3: The library

**Files:**
- Create: `app/core/library.py`, `lessons/courses.json`
- Test: `tests/integration/test_library.py`

**Interfaces:**
- `lessons/courses.json`: `[{"id": "excel", "title": "Excel", "app": "excel", "colour": "courseExcel"},
  {"id": "python", "title": "Python in VS Code", "app": "vscode", "colour": "coursePython"},
  {"id": "meta-ai", "title": "Build with Meta's AI", "app": "vscode", "colour": "courseMeta"}]`
- `Library(root: Path, *, show_unproven: bool = False)`: `courses() -> list[CourseInfo]`,
  `lessons(course_id) -> list[Lesson]` (shelf only, in `courses.json` order then title),
  `lesson(lesson_id) -> Lesson`, `reload()`. A lesson folder that fails to load or validate is skipped and
  its problem kept in `problems` (shown in the log, never on screen).

- [ ] **Step 1: Write the failing tests**

```python
def test_only_proven_lessons_are_on_the_shelf(tmp_path): ...
def test_a_broken_lesson_folder_is_skipped_and_noted(tmp_path): ...
def test_a_course_with_no_ready_lessons_is_coming_soon(tmp_path): ...
```

- [ ] **Step 2–4:** fail, implement, pass
- [ ] **Step 5: Commit** — `git commit -m "Add the library: courses and the lessons that passed their proof and test"`

### Task 4: The real backend

**Files:**
- Create: `app/integration/__init__.py`, `app/integration/backend.py`
- Test: `tests/integration/test_backend.py` (with `FakePlugin`, fake coach and fake maker)

**Interfaces:**
- `Backend(library, progress, plugins: Mapping[str, AppPlugin], coach: Coach | None, maker: LessonMaker | None,
  *, workdir: Path, layout: Callable[[], tuple[Rect, Rect]])` implements `ScreenBackend`. `layout()` gives
  (app rect, panel rect) in physical px from `main.py`.
- Wiring:
  - `open_lesson(id)`: if a session is open for it, do nothing; else close the open one (saving), open the
    plug-in with `resume` when a work file exists, `place(app rect)`, attach `LessonRun`; snapshots go to
    `on_snapshot` → runner events. Build the `LessonRun` before calling `open`: the first snapshot may
    arrive inside `open` (the fake does this). After a resume, the first snapshot goes to `run.resume(snap)`
    instead, which moves past finished steps with no events, points or records.
  - Events → state: `StepPassed` → banner right, `cue("right")`, points, `progress.step_passed`, pointer
    ring "right", then the next step's pointer; `NotYet` → banner not_yet, `cue("not_yet")`; `StepChanged`
    / `StepFixed` → `changed` list; `LessonDone` → `complete`, `cue("complete")`, `progress.lesson_done`,
    attempts logged.
  - Pointer: on each new step, `session.watch(step.target, on_spot)`; spot → `PointerState` with `bubble`
    from the spot or "this one!"; `show_me()` replays the flight; `set_waiting(True)` while a step waits.
  - `next_hint()` → `run.hint()`; `watch_clip()` → `ClipView` from the lesson's `source.video_file` under
    `recordings/` ("missing" with `videoUrl` when absent); `ask(text)` → `coach.answer` on a worker thread,
    `AskView` thinking → answered or error.
  - `on_closed` → `appState: "closed"` and banner app_closed; `reopen_app()` resumes.
  - `make_lesson(url)` → `maker.make` on a worker thread; `on_stage` → `Factory` state; ready → library
    reload and a highlight.
  - Home: tips refreshed after each finished lesson (`coach.tips(progress.attempts())`) on a worker thread;
    `meta` from `find_key()` and the coach's last failure.
- Every action returns at once; slow work runs on a single worker thread; state updates go out through
  `subscribe` listeners.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_right_step_updates_banner_points_cue_and_pointer(): ...
def test_not_yet_shows_the_line_and_takes_nothing_away(): ...
def test_app_closed_shows_reopen_and_reopen_resumes(): ...
def test_resuming_ticks_done_steps_quietly(): ...
def test_opening_twice_opens_one_app(): ...
def test_clip_missing_offers_the_video_link(): ...
def test_ask_never_ticks_a_step(): ...                 # coach answers "done!" -> stepIndex unchanged
def test_finished_lesson_refreshes_tips(): ...
```

- [ ] **Step 2–4:** fail, implement, pass
- [ ] **Step 5: Commit** — `git commit -m "Join the pieces: the program's backend turns real app changes into what the screens show"`

### Task 5: Start-up and docking

**Files:**
- Create: `app/main.py`, `app/__main__.py`
- Probe: `probes/app_start.py` (start, open the budget lesson, screenshot, close)

**Interfaces:**
- `python -m app [--demo STATE]`: fonts, `Backend` (or `DemoBackend` with `--demo`), `run_screens`.
- `layout()`: the work area of the screen the home window is on; panel = right 360 logical px × full
  height; app = the rest. Recomputed when the screen changes.
- On lesson open: home hides, panel and overlay show, the app is placed; on close or Home: the reverse.

- [ ] **Step 1:** Run `<py> -m app --demo first_run` → the home window appears (screenshot loop from plan 02)
- [ ] **Step 2:** Implement `main.py` with the real backend
- [ ] **Step 3: Live probe** (memory check first): `<py> probes\app_start.py` → paste its output and look at
  the screenshot: panel flush right, Excel filling the rest, nothing overlapping the taskbar.
- [ ] **Step 4: Commit** — `git commit -m "Start the program with python -m app; the panel docks right and the app fills the rest"`

### Task 6: The budget lesson end to end (Sat 31)

- [ ] **Step 1:** Merge `stream/excel` and `stream/ui` (when Ranvir says), run the full suite, paste it.
- [ ] **Step 2:** Wire the vision fallback: `ExcelSession.set_vision_fallback` → Muse Spark 1.3 on a
  screenshot through `MetaClient` (label `point_fallback`), grounding answer on the 0–1000 grid converted to
  pixels; accepted only by the plug-in's UI Automation agreement rule.
- [ ] **Step 3:** Play the budget lesson by hand from Home to the celebration, then again with one planted
  wrong try per step. Note every glitch (a jump, a wrong word, a lag over 300 ms) and fix it; repeat until a
  clean run.
- [ ] **Step 4:** Save `lessons/monthly-budget/goal.png` (the finished sheet with its chart, cropped).
- [ ] **Step 5:** Run the proof and the tester on it (plan 04), fill its `proof` and `test`.
- [ ] **Step 6: Commit** — `git commit -m "The monthly budget lesson plays start to finish in real Excel with the real screens, proven and tested"`

### Task 7: The library from the approved videos (Sun 1)

- [ ] **Step 1:** For each approved video, in rank order: `<py> -m app.factory make <url>`; paste each
  final stage line. Stop at 6 ready Excel lessons plus the demo pair (or when the list runs out: tell Ranvir).
- [ ] **Step 2:** Read each ready lesson's steps; fix wording by hand where needed (`edited`, re-proven and
  re-tested automatically).
- [ ] **Step 3:** Replace the hand-written budget lesson by the one made from a video when one passes.
- [ ] **Step 4:** Rough cut of the video's first 10 seconds; Ranvir shows it to three people and asks
  "what is this?"; write their answers in `docs/notes/first-10-seconds.md`.
- [ ] **Step 5: Commit** — `git commit -m "Fill the shelf: <n> Excel lessons made from tutorials, each proven and tested"`

### Task 8: Tips, Ask and the VS Code join (Mon 2)

- [ ] **Step 1:** Merge `stream/factory` and `stream/vscode` (when Ranvir says), full suite, paste it.
- [ ] **Step 2:** Tips live after two finished lessons; Ask live on three questions per step type; look at
  each answer; fix the prompts if any answer is long, vague or claims a step is done.
- [ ] **Step 3:** Play the VS Code "first app with Meta's AI" lesson end to end; fix glitches.
- [ ] **Step 4:** Point the tester at the VS Code lessons (only after Ranvir says he is away).
- [ ] **Step 5: Commit** — `git commit -m "Tips, the Ask box and the VS Code lessons work in the real program"`

### Task 9: Feature freeze checks (Mon 2 night)

- [ ] **Step 1:** Ranvir away: run plan 03 Task 8's typing test once; paste the last line.
- [ ] **Step 2:** Fresh-clone check: clone the repo into a scratch folder, follow the README's setup word
  for word with a new virtual environment, start the program, open one lesson. Paste every command and its
  output; fix the README where it was wrong.
- [ ] **Step 3:** Secret scan over the whole history: `<py> tools\secret_scan.py --history`; paste it.
- [ ] **Step 4:** From now on: fixes only. Update STATUS.md.

### Task 10: README (Tue 3)

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** First sentence names what it does without "tutor", "AI teacher" or "chat". Sections:
  what it is (with the pitch line), a 20-second GIF, how a lesson is made (the seven stages), which Meta
  model does what (spec 7), what is proven and what is tested and how the tester's clicks are limited,
  setup (Windows, desktop Excel, VS Code, Python 3.12, your own Meta key), credits for every video and
  creator with licences, "lessons are generated and then reviewed", the reuse table, and what is not done.
- [ ] **Step 2:** Check every claim against the code (`grep` for each named feature; paste where it lives).
- [ ] **Step 3: Commit** — `git commit -m "Write the README: what it does, how lessons are made and proven, setup, credits"`

### Task 11: Recordings, video and submission (Tue 3 – Wed 4)

- [ ] **Step 1:** Before recording: check free memory, tell Ranvir which sessions to close.
- [ ] **Step 2:** Record the spec's demo script (section 8) screen by screen at 1280 px logical; keep each
  take; note the best take per scene in `docs/notes/video-takes.md`.
- [ ] **Step 3:** Draft the voice-over script (plain words, ≤ 2:50 spoken) for Ranvir to record.
- [ ] **Step 4:** Edit to 3:00 by 2:55 PM Wed 4; a 30–45 s X clip.
- [ ] **Step 5:** Submission checklist for Ranvir: public repo link (name approved by Ranvir; pushed with
  the pre-push guard), video link, X post, form fields drafted in `docs/notes/submission.md`. Ranvir
  submits by 6 PM.
