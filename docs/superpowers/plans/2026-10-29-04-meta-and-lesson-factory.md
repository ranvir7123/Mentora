# Meta and lesson factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Paste a YouTube link, get a proven and tested lesson: download, read with Muse Spark, write the
lesson, prove every check in the real app, hunt predicted mistakes, let Meta's computer-use agent play the
learner, publish. Plus AI tips and the Ask box.

**Architecture:** One Meta client (`app/meta/client.py`) for every call: it logs cost, enforces the $100
stop, and in tests replays saved answers instead of calling Meta. The factory (`app/factory/`) is a chain
of stages, each a plain function over the core `AppPlugin` interface, so every stage is tested on the
core's `FakePlugin` and saved answers; live runs use `ExcelPlugin`. `LessonFactory` implements the core
`LessonMaker`; `app/coach/` implements the core `Coach`.

**Tech Stack:** openai client (pointed at `https://api.meta.ai/v1`), yt-dlp, imageio-ffmpeg, pywin32
(`SendInput`), Qt's `QScreen.grabWindow` for screenshots (PNG), pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-tutorial-to-practice-design.md` (sections 4, 5.3, 5.4, 7)

## Global Constraints

See `2026-10-29-00-overview.md`, "Global Constraints". Also, from the spec and the research notes
(`C:\dev\meta-hackathon-notes\research notes\meta_models_and_tools.md`, read sections 1–3 first):
- Model ids: `muse-spark-1.3` (writing, mistakes, tips, Ask, pointing fallback), `muse-wonder-1.0`
  (computer-use default), `muse-voice-transcribe-1.0` (`POST /v1/asr/transcribe`). Never a `-contributor` id:
  the client refuses any model id ending in `-contributor`.
- Prices per 1M tokens: Muse Spark input $1.25, cached $0.15, output $4.25; Muse Wonder input $4.00,
  cached $0.20, output $20.00; Voice Transcribe $0.18 per audio hour. Re-check these on the pricing page
  during the go/no-go task and update `app/meta/prices.py` if they changed.
- Video input: `video/mp4` only; upload through `POST /v1/files` (`purpose: "user_data"`) and reference by
  `file_id`, or an `input_video` block with a base64 data URL. Images: at most 50 per request.
- Computer use: Responses API only, tool `{"type": "computer"}`, coordinates are pixels in the last
  screenshot sent; keep the screenshot size fixed in a run; `pending_safety_checks` are a decision point:
  stop the run and log them, never auto-acknowledge.
- Every call is appended to `%LOCALAPPDATA%\projectx\meta_calls.jsonl` (model, label, tokens, cost, time,
  ok). At $100 total the client raises `SpendLimitReached` and the session tells Ranvir.
- The key only from `app.meta.key.require_key()`. Never print, log or save it; logs keep request labels,
  not bodies containing it.
- Videos and frames live in `recordings/` (ignored by git). Prefer Creative Commons videos.
- The tester moves the real mouse: run it only after Ranvir says he is away. Clicks outside the app's
  window are refused and logged; keyboard routes a learner could use are allowed.

## Review Focus

1. Muse Spark returns broken JSON, an off-menu check, a 20-word instruction or refuses the video → the
   lesson shows "not ready" with the reason; nothing crashes (Task 4 tests on saved bad answers).
2. A video longer than 15 minutes, private, removed or with no captions → a plain reason, or Voice
   Transcribe for the captions (Task 3 `test_long_video_is_refused_with_the_reason`,
   `test_no_captions_falls_back_to_transcribe`).
3. A check that cannot fail (true before its step) or a predicted mistake the check accepts → the check is
   sent back once, then the step is dropped and the remaining steps are re-proven without it (Task 5
   `test_dropping_a_step_reproves_the_rest_without_it`).
4. The agent tries to click outside the app (the taskbar, the panel, another window) → refused, logged,
   the run continues (Task 6 `test_clicks_outside_the_app_window_are_refused`).
5. Meta is unreachable or the key is missing mid-lesson → tips say so calmly; lessons still work; the Ask
   box says it can't answer right now (Task 8 `test_coach_failures_become_plain_messages`).

---

## File structure

| File | Job |
|---|---|
| `app/meta/client.py` | `MetaClient`: respond, upload, transcribe; logging; replay; spend stop |
| `app/meta/prices.py` | price table and `cost_of(model, usage)` |
| `app/factory/video.py` | `fetch` (yt-dlp), `prepare` (ffmpeg), captions to transcript |
| `app/factory/writer.py` | Muse Spark fills the lesson form |
| `app/factory/prove.py` | before/after proof and the mistake hunt |
| `app/factory/tester.py` | the computer-use learner |
| `app/factory/pipeline.py` | `LessonFactory` (core `LessonMaker`), CLI `python -m app.factory` |
| `app/coach/coach.py` | `MetaCoach` (core `Coach`): tips and answers |
| `probes/meta_go_nogo.py` | the go/no-go tests |
| `tests/meta/`, `tests/factory/`, `tests/coach/`, `tests/data/meta/` | tests and saved answers |

---

### Task 1: The Meta client

**Files:**
- Create: `app/meta/client.py`, `app/meta/prices.py`
- Test: `tests/meta/test_client.py`

**Interfaces:**
- `MetaClient(*, mode: Literal["live", "replay", "record"] = "live", saved_dir: Path = Path("tests/data/meta"),
  log_path: Path | None = None, limit_usd: float = 100.0)`
- `respond(model: str, input: list, *, label: str, schema: dict | None = None, tools: list | None = None,
  previous_response_id: str | None = None, **extra) -> Answer` — Responses API; `schema` becomes
  structured JSON output.
- `upload(path: Path, *, label: str) -> str` (file id); `transcribe(audio: Path, *, label: str) -> Transcript`
  (`Transcript(text: str, segments: list[tuple[float, float, str]])`).
- `Answer(text: str, data: Any | None, output: list, usage: Usage, response_id: str, cost: float)`
- `spent() -> float`; errors: `SpendLimitReached`, `MetaUnavailable(reason)` (network, 5xx, timeouts
  after 3 tries with backoff and jitter), `NoKey`.
- Replay: answers are saved as `saved_dir/<label>.json` (request summary, response); `replay` mode reads
  them and never touches the network; `record` calls live and saves. Saved files never contain the key.

- [ ] **Step 1: Write the failing tests** (a fake transport; no network)

```python
def test_replay_returns_the_saved_answer_without_network(tmp_path): ...
def test_every_call_is_logged_with_its_cost(tmp_path): ...       # 1000 in / 500 out Spark tokens -> cost 0.003375
def test_spending_stops_at_the_limit(tmp_path): ...              # limit 0.01; calls until SpendLimitReached
def test_contributor_models_are_refused(): ...
def test_the_key_never_reaches_saved_files_or_logs(tmp_path): ...
def test_network_failure_becomes_meta_unavailable(tmp_path): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Commit** — `git commit -m "Add the Meta client: one place for every call, a cost log, a 100 dollar stop and saved answers for tests"`

### Task 2: Go / no-go tests (as soon as the key works)

**Files:**
- Create: `probes/meta_go_nogo.py`, `docs/notes/meta-go-nogo.md`; saved answers in `tests/data/meta/`

- [ ] **Step 1:** Ask Ranvir whether the key is saved (`find_key()` says where, never what). Without it,
  skip to Task 3 and come back.
- [ ] **Step 2:** `models`: list models; confirm the three ids above exist. Print id names only.
- [ ] **Step 3:** `video`: a 30–60 s Excel screen recording (record one with the budget lesson's first two
  steps, or a Creative Commons clip) → small MP4 → `muse-spark-1.3` fills `lesson_json_schema(ExcelPlugin())`
  (or `FakePlugin` if plan 03 is not merged yet: copy the Excel menu names from plan 03 Task 4 into a
  temporary plugin stub inside the probe). Save the answer as `go_nogo_video.json`.
- [ ] **Step 4:** `computer`: (only when Ranvir is away) Excel open at 920 px beside the panel area, a
  screenshot, ask `muse-wonder-1.0` with the computer tool to "click cell C3"; map its click from
  screenshot pixels to screen pixels; check with `locate(cell C3)`. Repeat 5 times. Write in the notes how
  coordinates map at 200% and the hit rate.
- [ ] **Step 5:** `credit`: note the spend so far (from the log) and ask Ranvir for the balance shown in
  the dashboard.
- [ ] **Step 6:** Write `docs/notes/meta-go-nogo.md` with the pasted outputs and the verdict for each
  (go / no-go). Any no-go: stop and tell Ranvir with the saved answers, before building on it.
- [ ] **Step 7: Commit** — `git commit -m "Go/no-go: Muse Spark <go|no-go> on Excel video, computer use <n> of 5 clicks on target at 200%"`

### Task 3: Getting and preparing the video

**Files:**
- Create: `app/factory/__init__.py`, `app/factory/video.py`
- Test: `tests/factory/test_video.py`; Probe: `probes/meta_video.py`

**Interfaces:**
- `VideoInfo(id, url, title, creator, channel_url, licence, length_s: int)`
- `fetch(url: str, dest: Path, *, max_length_s: int = 900) -> Fetched` (`Fetched(info: VideoInfo, video: Path,
  captions: Path | None)`) — yt-dlp Python API: best MP4 ≤ 720p, English captions (manual first, then
  automatic) as VTT; refuses before downloading when `length_s > max_length_s` with
  `VideoRefused("This video is 23 minutes. Pick one under 15.")`; private, removed or region-blocked →
  `VideoRefused` with a plain reason.
- `prepare(fetched, client: MetaClient | None) -> Prepared` (`Prepared(small_mp4: Path, frames: list[tuple[float, Path]],
  transcript: list[tuple[float, float, str]])`) — ffmpeg from `imageio_ffmpeg.get_ffmpeg_exe()`: small MP4
  854 px wide, 2 fps, quiet audio kept; frames at scene changes (`select='gt(scene,0.3)'`, at most 40);
  transcript from the VTT, else `client.transcribe` on the audio.
- Pure helpers: `vtt_to_segments(text) -> list[tuple[float, float, str]]` (merges the rolling duplicate
  lines automatic captions have), `ffmpeg_small_args(src, dst) -> list[str]`, `ffmpeg_frames_args(src, dir)
  -> list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_vtt_rolling_captions_become_clean_segments(): ...
def test_long_video_is_refused_with_the_reason(): ...       # fake yt-dlp info with duration 1380
def test_no_captions_falls_back_to_transcribe(tmp_path): ...  # client in replay mode
def test_ffmpeg_args(): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Live probe** — `<py> probes\meta_video.py <a short Creative Commons Excel tutorial URL>`:
  prints title, creator, licence, length, number of frames and transcript lines. Paste it.
- [ ] **Step 6: Commit** — `git commit -m "Get a tutorial and prepare it: download with captions, a small copy for Muse Spark, key frames, a transcript"`

### Task 4: Writing the lesson

**Files:**
- Create: `app/factory/writer.py`
- Test: `tests/factory/test_writer.py`; saved answers `tests/data/meta/writer_*.json`

**Interfaces:**
- `write_lesson(prepared, info: VideoInfo, plugin: AppPlugin, client: MetaClient, *, feedback: str = "")
  -> Lesson | NotReady` (`NotReady(reason: str)`)
- The request: the small MP4 (uploaded, `file_id`; on refusal, the frames instead), the transcript with
  timestamps, the plug-in's menus (each kind's name, params and summary), the rules (instructions ≤ 12
  words, plain second person, never "simply"/"just", 3 hints from gentle to the answer, 1–2 predicted
  mistakes per step with their own "Not yet" line, clip start/end from the video, a starter that fits 920
  px and holds the tutorial's starting data), and `lesson_json_schema(plugin)` as the output schema.
  `feedback` carries the prover's reasons on a retry.
- After the answer: `lesson_from_dict` + `validate(lesson, plugin)`; problems → one retry with the problems
  listed; still bad → `NotReady` naming the first three problems in plain words.
- `made_by="generated"`, `source` from `info`, `id` from the title (lowercase, hyphens, unique in `lessons/`).

- [ ] **Step 1: Write the failing tests** (replay mode)

```python
def test_a_good_answer_becomes_a_valid_lesson(): ...
def test_an_off_menu_check_is_retried_once_then_not_ready(): ...
def test_broken_json_is_not_ready_with_a_plain_reason(): ...
def test_a_refused_video_falls_back_to_frames(): ...
def test_long_instructions_are_sent_back_with_the_problem(): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Commit** — `git commit -m "Muse Spark writes a lesson from the video, choosing only from the app's menus; bad answers become a plain not-ready reason"`

### Task 5: The proof and the mistake hunt

**Files:**
- Create: `app/factory/prove.py`
- Test: `tests/factory/test_prove.py`

**Interfaces:**
- `prove(lesson, plugin, workdir: Path, *, fix: Callable[[Lesson, str], Lesson | NotReady] | None = None)
  -> Proved` (`Proved(lesson: Lesson, dropped: list[str], notes: list[str])`; `lesson.proof` filled)
- Algorithm (the proof run is the learner's run):
  1. Open the plug-in invisibly; for each kept step in order: snapshot → its check must be not-ok; perform
     each predicted mistake from this state (then `reset()` and replay the kept steps before it) → the check
     must be not-ok and attempted, and the mistake's `code` is set from the verdict; perform the replay →
     the check must be ok.
  2. On any failure: if `fix` is given and this step has not been retried, call `fix(lesson, reason)` once
     (the writer with `feedback`), and restart from 1 with the new lesson.
  3. Still failing → drop the step, note why, and restart from 1 without it (later steps are re-proven
     without its replay, so a step that needed it is dropped too).
  4. `proof.passed` is true when at least 3 steps remain and none failed.
- Mistake codes go into `Mistake.code` so the runner shows each mistake's own line.

- [ ] **Step 1: Write the failing tests** (`FakePlugin`)

```python
def test_a_good_lesson_is_proven_and_mistake_codes_are_filled(tmp_path): ...
def test_a_check_true_before_its_step_is_sent_back_once(tmp_path): ...
def test_a_mistake_the_check_accepts_is_sent_back_once(tmp_path): ...
def test_dropping_a_step_reproves_the_rest_without_it(tmp_path): ...
def test_fewer_than_three_steps_left_is_not_proven(tmp_path): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Live run** (needs plan 03 merged; memory check first): `<py> -m app.factory prove lessons/monthly-budget`
  prints each step's before/after and each mistake's code; expected all nine proven. Paste it.
- [ ] **Step 6: Commit** — `git commit -m "Prove every lesson in the real app: each check false before and true after its step, and every predicted mistake rejected"`

### Task 6: The computer-use learner

**Files:**
- Create: `app/factory/tester.py`, `app/factory/input.py` (SendInput clicks, keys, typing; screenshots)
- Test: `tests/factory/test_tester.py`

**Interfaces:**
- `test_lesson(lesson, plugin, workdir, client, *, model: str = "muse-wonder-1.0", runs: int = 5,
  mode: Literal["mouse", "keyboard"] = "mouse", max_actions_per_step: int = 25) -> TestResult`
- One run: open the plug-in visibly, place the app window at the lesson layout (920 px beside a 360 px
  strip), attach a `LessonRun`; give the agent the lesson's instructions one step at a time ("You are a
  learner. Do only this step: …"), loop: screenshot → `client.respond(tools=[{"type": "computer"}],
  previous_response_id=…)` → do the `computer_call` action → screenshot back. The step ends when the
  runner says `StepPassed`, or after `max_actions_per_step` (run failed). `pending_safety_checks` end the
  run as failed and are logged.
- Action filter `allowed(action, app_rect: Rect, mode) -> tuple[bool, str]`: clicks, double clicks, drags
  and scrolls only inside `app_rect`; in `keyboard` mode no clicks at all; keypress and typing always
  allowed. A refused action is answered with a screenshot and a note "That is outside the app. Use the
  app's window." and logged.
- Coordinates: screenshot pixels → screen pixels using the rule written down in the go/no-go notes.
- Result: passes ≥ 4 of 5 → `TestResult(passed=True, mode=...)`. The fallback chain (mouse → keyboard →
  `mode="skipped"`, "proven" badge) is decided by the pipeline (Task 7), and Ranvir is told when it switches.

- [ ] **Step 1: Write the failing tests** (scripted model answers on `FakePlugin`; no real input)

```python
def test_clicks_outside_the_app_window_are_refused(): ...
def test_keyboard_mode_refuses_every_click(): ...
def test_a_run_passes_when_the_runner_ticks_every_step(): ...
def test_a_step_that_runs_out_of_actions_fails_the_run(): ...
def test_safety_checks_stop_the_run(): ...
def test_four_of_five_is_a_pass(): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Live run** (only after Ranvir says he is away; memory check first):
  `<py> -m app.factory test lessons/monthly-budget --runs 5` → paste the per-run lines and the result
- [ ] **Step 6: Commit** — `git commit -m "Meta's computer-use agent plays each lesson as a learner, clicking only inside the app: <n> of 5 runs passed"`

### Task 7: The pipeline

**Files:**
- Create: `app/factory/pipeline.py`, `app/factory/__main__.py`
- Test: `tests/factory/test_pipeline.py`

**Interfaces:**
- `LessonFactory(client: MetaClient, lessons_dir: Path = Path("lessons"), recordings: Path = Path("recordings"))`
  implements `LessonMaker.make(url, plugin, on_stage) -> MakeResult`. Stages and `on_stage` calls:
  `download` → `read` (prepare) → `write` → `prove` → `test` → `publish`, each `running` then `done` or
  `failed` with a plain detail ("9 steps written", "8 of 9 steps proven, 1 dropped: chart over the wrong
  cells", "4 of 5 test runs passed").
- Test fallback: mouse fails → keyboard; keyboard fails → `TestResult(mode="skipped")`; each switch is
  announced in the stage detail and in the pipeline's log line for Ranvir.
- Publish: `lessons/<id>/lesson.json`; `goal.png` = the video frame at the last step's clip end (or the
  last scene frame); returns `MakeResult(lesson, "")`; any failure → `MakeResult(None, reason)` and nothing
  written to `lessons/`.
- CLI: `python -m app.factory make <url> [--app excel] [--no-test]`, `prove <lesson folder>`,
  `test <lesson folder> [--runs 5]`; prints stages as they happen.

- [ ] **Step 1: Write the failing tests** (replay client, `FakePlugin`, a fake `fetch`)

```python
def test_a_good_video_lands_on_the_shelf_with_its_stages_reported(tmp_path): ...
def test_a_failed_proof_publishes_nothing_and_says_why(tmp_path): ...
def test_test_fallback_goes_keyboard_then_proven_only(tmp_path): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Commit** — `git commit -m "Add the lesson factory: paste a link, watch each stage, and only proven and tested lessons reach the shelf"`

### Task 8: AI tips and the Ask box

**Files:**
- Create: `app/coach/__init__.py`, `app/coach/coach.py`
- Test: `tests/coach/test_coach.py`; saved answers `tests/data/meta/coach_*.json`

**Interfaces:**
- `MetaCoach(client)` implements `Coach`:
  - `tips(log: list[StepRecord]) -> str` — sends a summary per lesson and step kind (tries, hints, seconds),
    never workbook contents; asks for two or three plain sentences, at most 40 words, second person, no
    "simply"/"just", naming one strength and one thing to practise with a lesson from the shelf. Empty log →
    "" (the screen shows its own "Finish a lesson to get tips").
  - `answer(question, context) -> str` — `context`: the step's instruction, why, hints shown, the last
    verdict's text, and a small state summary from the plug-in (for Excel: the target cell's value and
    formula and the selected cell). The answer is at most 60 words and never says the step is done.
  - Failures (`MetaUnavailable`, `NoKey`, `SpendLimitReached`) → raise `CoachUnavailable(message)` with a
    calm line for the screen ("Tips are offline right now. Your lessons still work.").
- Words filter: answers containing "simply" or "just" get those words removed; answers claiming a step is
  done or ticked are replaced by the step's next hint.

- [ ] **Step 1: Write the failing tests**

```python
def test_tips_are_short_plain_and_from_the_log_only(): ...       # request body has no cell values
def test_answers_never_claim_a_step_is_done(): ...
def test_coach_failures_become_plain_messages(): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Commit** — `git commit -m "Add AI tips from the learner's own attempts and answers to questions about the current step"`

### Task 9: Extras (only when plan 06 says goals 1–6 never break)

One task each, same shape (test, implement, live check, commit), in this order: ask by voice (Muse Voice
Transcribe, a hold-to-talk button in the Ask box); SAM 3.1 outlines that hug a ribbon target (accepted only
when the outline's box agrees with UI Automation's within 6 px). Ask Ranvir before starting either.

Final report for the merge: test output, the go/no-go notes, spend so far, any no-go and its fallback.
