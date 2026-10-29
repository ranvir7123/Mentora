# Look and feel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build every screen the learner sees — home, the 360 px lesson panel, the flying mascot and ring
over the real app — polished, in every state, driven by a demo backend so no real Excel is needed.

**Architecture:** Qt Quick (QML) for all drawing and animation; Python only for the bridge. `Bridge`
wraps any `ScreenBackend` (from `app/core/screen.py`) as one Qt object with `home`, `lesson` and `pointer`
properties and one slot per action. A `DemoBackend` produces every state on demand for screenshots and
for the QML load test. Three windows: home, panel, overlay.

**Tech Stack:** PySide6 6.12 (Qt Quick, Qt Quick Shapes, Qt Multimedia), pywin32 for window styles.

**Spec:** `docs/superpowers/specs/2026-10-29-tutorial-to-practice-design.md` (sections 2.1–2.3, 6)

## Global Constraints

See `2026-10-29-00-overview.md`, "Global Constraints". Also, from the spec, verbatim where it fixes values:
- Tokens: base #151A2E; surfaces #1E2440, #282F52; border #363E66; accent coral #FF7A45 (progress, main
  button, ring, mascot body only); reward gold #FFC53D (points, streaks, celebrations only); right mint
  #3DDC97; not yet rose #FF6B81; text #EEF1FA; muted #9AA3C0.
- Type: Fredoka (headings), Nunito (text), bundled; equal-width digits for numbers. Sizes 12/14/16/20/24/32/48;
  weights paired far apart (400 with 700+).
- Spacing 4/8/12/16/24/32/48; panel side margins 16 px; at most three corner sizes.
- Buttons: chunky, rounded, a 4 px darker bottom edge; pressed moves down and scales to 0.97.
- The taste brief (spec 6.3) and the banned list (spec 6.4) apply to every task; Task 1 copies them into
  `app/ui/TASTE.md` with a checklist.
- Dark only. Never "simply" or "just". Loading shown only after 200 ms.

## Review Focus

1. A title, instruction or "Not yet" line far longer than planned (a 60-character lesson title, a German
   creator name) → text wraps or elides cleanly, nothing overlaps (Task 9 state `long_text`).
2. The target sits at the screen's edge or under the panel (cell in column A, a button in the top-left
   corner) → the mascot lands on the side with room and never covers the target (Task 5
   `test_landing_spot_never_covers_the_target`).
3. Clicks while the mascot is flying or a banner is sliding (the learner is fast) → the click reaches Excel
   and the animation does not block anything (Task 5 probe step: click-through check).
4. The panel's buttons pressed while the learner is typing in Excel → focus returns to Excel; typing never
   lands in the panel (Task 5 `test_panel_never_takes_focus_except_the_ask_box`).
5. Updates arriving from another thread in a burst (Excel reads at 20 per second) → the screens stay smooth
   and show the latest state (Task 1 `test_updates_from_other_threads_arrive_in_order`).

---

## File structure

| File | Job |
|---|---|
| `app/ui/TASTE.md` | taste brief, banned list, per-screenshot checklist |
| `app/ui/fonts/` | Fredoka and Nunito `.ttf` files and their `OFL.txt` |
| `app/ui/sounds/` | `click.wav`, `right.wav`, `not_yet.wav`, `complete.wav`, `hop.wav` (made by `probes/ui_make_sounds.py`) |
| `app/ui/bridge.py` | `Bridge(QObject)` around a `ScreenBackend` |
| `app/ui/demo_backend.py` | `DemoBackend`: every state, by name |
| `app/ui/winstyle.py` | Windows extended styles: click-through overlay, panel that does not take focus |
| `app/ui/app.py` | `run_screens(backend) -> int`: fonts, engine, three windows |
| `app/ui/qml/Theme/Theme.qml` + `qmldir` | singleton tokens |
| `app/ui/qml/components/*.qml` | ChunkyButton, ProgressBar, Banner, Card, StreakFlame, DailyRing, HintList, ClipPlayer, AskBox, StageList, PathNode, Confetti, Sfx |
| `app/ui/qml/mascot/Mascot.qml` | the mascot, five states |
| `app/ui/qml/HomeWindow.qml`, `PanelWindow.qml`, `OverlayWindow.qml` | the three windows |
| `app/ui/qml/home/*.qml`, `app/ui/qml/panel/*.qml` | screen sections |
| `probes/ui_shot.py` | screenshot of any window in any demo state at 200% |
| `probes/ui_mascot_smoothness.py` | frame timing of a flying shape at 200% |
| `probes/ui_make_sounds.py` | makes the sound files |
| `tests/ui/` | bridge, demo backend, QML load, landing maths, window styles |

## How every component task ends (the screenshot loop)

After the code step of any task that draws something:
1. Run `<py> probes\ui_shot.py <window> --state <state> --out runs\shots\<window>-<state>.png` for each
   state the task lists. (`<window>` is `home`, `panel` or `overlay`; the probe sets `QT_SCALE_FACTOR=2`
   when the screen is not already at 200%, waits for animations to settle, and saves `grabWindow()`.)
2. Open each PNG with the Read tool and go through `app/ui/TASTE.md`'s checklist line by line; write the
   failures down, fix them, shoot again. Move on only when the checklist passes.
3. `runs/` is ignored by git; nothing from it is committed.

---

### Task 1: Shell, tokens, bridge and demo states

**Files:**
- Create: `app/ui/__init__.py`, `TASTE.md`, `fonts/`, `bridge.py`, `demo_backend.py`, `app.py`,
  `qml/Theme/Theme.qml`, `qml/Theme/qmldir`, `qml/HomeWindow.qml`, `qml/PanelWindow.qml`,
  `qml/OverlayWindow.qml` (empty shells), `probes/ui_shot.py`
- Test: `tests/ui/test_bridge.py`, `tests/ui/test_qml_loads.py`

**Interfaces:**
- Consumes: `app.core.screen` (`ScreenBackend`, state shapes, `EMPTY_HOME`, `CLOSED_LESSON`,
  `HIDDEN_POINTER`, `CUES`).
- Produces:
  - `Bridge(backend: ScreenBackend, parent=None)`: properties `home`, `lesson`, `pointer` (`QVariantMap`,
    notify `homeChanged`, `lessonChanged`, `pointerChanged`), `muted` (bool); signal `cue(str)`;
    slots `openLesson(str)`, `continueLesson()`, `showMe()`, `nextHint()`, `watchClip()`, `ask(str)`,
    `closeLesson()`, `nextLesson()`, `goHome()`, `makeLesson(str)`, `setMuted(bool)`, `reopenApp()`.
    Listener calls from any thread go through a queued signal to the GUI thread.
  - `DemoBackend(state: str = "first_run")` implementing `ScreenBackend`, `STATES: tuple[str, ...]`:
    `first_run`, `home_progress`, `home_long_text`, `home_no_key`, `home_offline`, `course_empty`,
    `factory_running`, `factory_not_ready`, `lesson_goal`, `lesson_step`, `lesson_right`, `lesson_not_yet`,
    `lesson_hints`, `lesson_changed`, `lesson_clip`, `lesson_clip_missing`, `lesson_ask`,
    `lesson_app_closed`, `lesson_complete`, `pointer_flying`, `pointer_watching`, `pointer_right`,
    `long_text`. `set_state(name)` switches and notifies. `walkthrough()` plays the budget lesson
    (`lessons/monthly-budget`) step by step on a 2 s timer with one planted "Not yet".
  - `run_screens(backend: ScreenBackend, *, show: Iterable[str] = ("home",)) -> int`, and from the
    command line `<py> -m app.ui.app --demo <state or walkthrough> --show home,panel,overlay`
  - Theme token names: `bg`, `surface1`, `surface2`, `border`, `accent`, `accentEdge`, `reward`,
    `rewardEdge`, `right`, `rightEdge`, `notYet`, `notYetEdge`, `text`, `muted`, `courseExcel`,
    `coursePython`, `courseMeta`; `fontHeading`, `fontBody`; `size12`…`size48`; `space4`…`space48`;
    `radiusSmall`, `radiusMedium`, `radiusLarge`; `durFast` 150, `durNormal` 220, `durPanel` 300.
    Course colours: solid, distinct from accent, reward, right and not-yet, readable on `surface1`.

- [ ] **Step 1: Write the failing tests**

```python
def test_bridge_exposes_the_backend_state(qapp): ...          # Bridge(DemoBackend("lesson_step")).lesson["stepIndex"] == 1
def test_actions_reach_the_backend(qapp): ...                 # bridge.showMe() -> backend recorded "show_me"
def test_updates_from_other_threads_arrive_in_order(qapp): ...
    # 200 lesson updates from a worker thread; after processEvents the bridge holds the last one and
    # lessonChanged fired at least once; no exception
def test_every_demo_state_has_every_key():
    for s in STATES: d = DemoBackend(s); assert set(d.home()) == set(EMPTY_HOME) ...  # and lesson, pointer
def test_every_window_loads_in_every_state_without_qml_warnings(qapp):
    # for each window in (home, panel, overlay) and each state: load with QQmlApplicationEngine,
    # collect warnings via engine.warnings signal -> assert none
```

`tests/ui/conftest.py` makes one `QGuiApplication` per session (`qapp` fixture) with
`QT_QPA_PLATFORM=offscreen`.

- [ ] **Step 2: Run them to see them fail** — `<py> -m pytest tests/ui` → FAIL (import)
- [ ] **Step 3: Get the fonts** — Fredoka (variable or 400/600/700) and Nunito (400/700/800) `.ttf` from
  the google/fonts GitHub repository (`ofl/fredoka`, `ofl/nunito`), with `OFL.txt`; load them with
  `QFontDatabase.addApplicationFont` in `run_screens`.
- [ ] **Step 4: Write `TASTE.md`** — the spec's 6.3 taste brief and 6.4 banned list word for word, then a
  checklist: tokens only (no stray hex in QML outside `Theme.qml`); sizes and spacing on the scales;
  ≤ 3 corner sizes; coral and gold used only for their jobs; text contrast ≥ 4.5:1 on its surface; nothing
  clipped or overlapping; digits equal-width; words plain, second person, sentence case; nothing from
  the banned list.
- [ ] **Step 5: Implement `Theme.qml`, `bridge.py`, `demo_backend.py`, `app.py`, the three window shells
  and `probes/ui_shot.py`**
- [ ] **Step 6: Run the tests** — `<py> -m pytest tests/ui` → `5 passed`
- [ ] **Step 7: Screenshot loop** for `home` in `first_run` (a background and a heading are enough here)
- [ ] **Step 8: Commit**

```bash
git add app/ui probes/ui_shot.py tests/ui
git commit -m "Add the screens' base: colours and type, the bridge to the program, demo states, and a 200% screenshot tool"
```

### Task 2: Mascot smoothness test (go / no-go before the mascot is built)

**Files:**
- Create: `probes/ui_mascot_smoothness.py`

- [ ] **Step 1: Write the probe** — a full-screen transparent, click-through, always-on-top window (use
  `winstyle.py` from Task 5 early, or inline flags) drawing a 48 px placeholder built from Qt Quick Shapes
  (a circle, two eyes, a shadow) flying 20 arcs between random points, 450 ms each, while timing frames
  with `QQuickWindow.frameSwapped` and `time.perf_counter_ns`.
- [ ] **Step 2: Run it at 200%** (memory check first) — `<py> probes\ui_mascot_smoothness.py`
  Expected output line: `frames=<n> p50=<ms> p95=<ms> p99=<ms> dropped_over_33ms=<n>`. Pass: p95 ≤ 20 ms
  and dropped ≤ 2%. Paste the line.
- [ ] **Step 3: If it fails** — try in order: `QSG_RHI_BACKEND=d3d11`, `layer.enabled` on the mascot,
  fewer shape paths, an `Image` of the mascot rendered once at 2× for flight only. Rerun after each; record
  which one passed in the commit message. If none passes, stop and tell Ranvir with the numbers.
- [ ] **Step 4: Commit**

```bash
git add probes/ui_mascot_smoothness.py
git commit -m "Add the mascot smoothness test: <paste the result line>"
```

### Task 3: Core components

**Files:**
- Create: `app/ui/qml/components/ChunkyButton.qml`, `ProgressBar.qml`, `Banner.qml`, `Card.qml`,
  `StreakFlame.qml`, `DailyRing.qml`, `HintList.qml`, `PathNode.qml`, `StageList.qml`, `Sfx.qml`
- Create: `probes/ui_make_sounds.py`, `app/ui/sounds/*.wav`
- Test: extend `test_qml_loads.py` with a gallery file `app/ui/qml/Gallery.qml` showing every component
  in every variant (add `gallery` as a window name in `ui_shot.py`)

**Interfaces:**
- `ChunkyButton { text; kind: "main"|"quiet"|"right"; enabled; signal clicked }` — main uses accent with a
  4 px `accentEdge` bottom edge; pressed: y+4 px, edge 0, scale 0.97, `durFast`; disabled: surface2, muted.
- `ProgressBar { value: 0..1; label }` — thick (12 px), rounded, accent fill, animates width over
  `durNormal` OutCubic; label like "3 of 9" with equal-width digits.
- `Banner { kind: "right"|"not_yet"|"changed"|"app_closed"|"error"; text; actionText; signal action }` —
  slides up from the panel bottom (`durNormal`), right = mint, not yet = rose (gentle, no shake), changed
  = surface2 with a coral link.
- `StreakFlame { days }`, `DailyRing { done; goal }` (gold), `HintList { hints; hintsLeft; signal more }`,
  `PathNode { state: "done"|"current"|"locked"; title }`, `StageList { stages }` (the factory's live
  stages, each with its state and detail line).
- `Sfx { muted; function play(name) }` — `QSoundEffect` per cue name in `CUES`.
- Sounds (made by the probe with the standard library `wave` module, 44.1 kHz mono, soft attack and
  release, one related family): `click` < 120 ms; `right` two rising notes < 300 ms; `not_yet` one soft
  low note < 250 ms, never harsh; `hop` < 150 ms; `complete` rising chime < 500 ms.

- [ ] **Step 1:** Add the gallery to the QML load test → run → FAIL (missing files)
- [ ] **Step 2:** Implement the components and `Gallery.qml`; run `probes/ui_make_sounds.py`
- [ ] **Step 3:** `<py> -m pytest tests/ui` → all pass
- [ ] **Step 4: Screenshot loop** for `gallery`
- [ ] **Step 5: Commit**

```bash
git add app/ui/qml/components app/ui/qml/Gallery.qml app/ui/sounds probes/ui_make_sounds.py tests/ui
git commit -m "Add the building blocks: chunky buttons, progress bar, banners, streak, daily ring, hints, path circles, stage list and the sound family"
```

### Task 4: The mascot

**Files:**
- Create: `app/ui/qml/mascot/Mascot.qml` (+ `qmldir` if needed); add it to `Gallery.qml`

**Interfaces:**
- `Mascot { state: "resting"|"flying"|"watching"|"thinking"|"cheering"; size: real (default 48);
  lookAt: point (scene coordinates the eyes follow); signal landed }`
- Built only from Qt Quick Shapes and Rectangles: a round coral body (`Theme.accent`), a slightly darker
  belly or shade, two eyes with pupils that look toward `lookAt`, one small detail that makes it ours (a
  sprout, a tuft, a tiny antenna: pick one and keep it). Not an owl, not green, not a triangle.
- States: resting (slow breathing scale 1.0↔1.03, 2.4 s, eyes blink every 4–6 s); flying (squash and
  stretch along the direction of travel, ≤ 15%); watching (eyes on `lookAt`, still); thinking (pupils up,
  a small three-dot pulse beside it); cheering (one hop with a spring, arms or tuft up, ≤ 450 ms).
- Only position, scale, rotation and opacity animate.

- [ ] **Step 1:** Add each mascot state to the gallery and the load test → FAIL
- [ ] **Step 2:** Implement `Mascot.qml`
- [ ] **Step 3:** `<py> -m pytest tests/ui` → pass
- [ ] **Step 4: Screenshot loop** for `gallery` (all five states side by side), plus a 3 s screen
  recording is not needed: rerun `ui_mascot_smoothness.py` with the real mascot swapped in and paste its
  line (same pass bar)
- [ ] **Step 5: Commit**

```bash
git add app/ui/qml/mascot app/ui/qml/Gallery.qml probes/ui_mascot_smoothness.py
git commit -m "Add the mascot: our own round character with resting, flying, watching, thinking and cheering"
```

### Task 5: Overlay: the flight, the landing and the ring

**Files:**
- Create: `app/ui/winstyle.py`, `app/ui/landing.py`, fill `app/ui/qml/OverlayWindow.qml`
- Test: `tests/ui/test_landing.py`, `tests/ui/test_winstyle.py`

**Interfaces:**
- `landing.landing_spot(target: Rect, mascot: float, screen: Rect, avoid: Rect) -> tuple[float, float]` —
  top-left of where the mascot lands (all physical px): beside the target with an 8 px gap, preferring
  left, then above, then right, then below; never intersecting `target.inflate(6)`; inside `screen`; never
  inside `avoid` (the panel). Exposed to QML through `Bridge` as slot `landingSpot(x, y, w, h) -> QPointF`
  in logical px.
- `landing.arc_control(start, end) -> tuple[float, float]` — the curve's control point: the middle,
  lifted by 25% of the distance, upward.
- `winstyle.make_click_through(hwnd: int)` (adds `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW |
  WS_EX_NOACTIVATE`), `winstyle.make_no_activate(hwnd: int, on: bool)` (toggles `WS_EX_NOACTIVATE`),
  `winstyle.ex_style(hwnd) -> int`.
- Overlay behaviour (from `pointer`): when `visible` turns on, the mascot leaves its resting place in the
  panel (the bridge's `mascotHome` rect, set by the panel), flies the arc to `landing_spot` in 400–500 ms
  with a low-bounce spring at the end, then the bubble types `bubble` (default "this one!", 18 ms per
  letter) and the ring (3 px accent outline, `radiusSmall`, target inflated by 4 px) pulses softly. After
  3 s the mascot flies home and the ring stays until the step passes. `ring: "right"` turns it mint for
  350 ms then fades. When x, y, w, h change while showing (the learner scrolled), the ring follows at once
  and the mascot re-lands. Every animation can be interrupted by a new pointer state.
- The panel window gets `make_no_activate(hwnd, True)`; the Ask box turns it off while it has focus and
  back on when it loses focus.

- [ ] **Step 1: Write the failing tests**

```python
def test_landing_spot_never_covers_the_target():
    screen = Rect(0, 0, 2560, 1600); panel = Rect(1840, 0, 720, 1600)
    for t in (Rect(0, 300, 128, 40), Rect(1700, 0, 128, 40), Rect(900, 1560, 128, 40), Rect(1000, 700, 128, 40)):
        x, y = landing_spot(t, 96, screen, panel)
        m = Rect(x, y, 96, 96)
        assert not m.intersects(t.inflate(6)) and not m.intersects(panel)
        assert screen.x <= x and x + 96 <= screen.x + screen.w and screen.y <= y and y + 96 <= screen.y + screen.h
def test_landing_prefers_the_left_side(): ...
def test_arc_bends_upward(): ...
def test_click_through_style_bits(qapp): ...        # a real offscreen-free top-level window; bits set
def test_panel_never_takes_focus_except_the_ask_box(qapp): ...   # NOACTIVATE on; off while AskBox focused; on again after
```

- [ ] **Step 2: Run them to see them fail** — FAIL (import)
- [ ] **Step 3: Implement** `landing.py`, `winstyle.py`, `OverlayWindow.qml`, the bridge's `landingSpot`
  and `mascotHome`
- [ ] **Step 4: Run them to see them pass** — `<py> -m pytest tests/ui` → pass
- [ ] **Step 5: Live probe** (memory check first): `<py> -m app.ui.app --demo pointer_flying --show panel,overlay`
  with Notepad open behind; click on Notepad's text area while the mascot flies: the click must land in
  Notepad (type a letter to confirm). Screenshot loop for `overlay` in `pointer_flying`,
  `pointer_watching`, `pointer_right`.
- [ ] **Step 6: Commit**

```bash
git add app/ui/winstyle.py app/ui/landing.py app/ui/qml/OverlayWindow.qml app/ui/bridge.py tests/ui
git commit -m "Add the pointer: the mascot flies in an arc, lands beside the real target, and a soft ring pulses; clicks pass through"
```

### Task 6: The lesson panel

**Files:**
- Fill: `app/ui/qml/PanelWindow.qml`; create `app/ui/qml/panel/TopBar.qml`, `GoalCard.qml`, `StepCard.qml`,
  `HelpRow.qml`, `ClipPlayer.qml` (in components), `AskBox.qml` (in components), `Complete.qml`,
  `components/Confetti.qml`

**Interfaces:**
- Consumes `bridge.lesson` and `bridge.cue`. Layout top to bottom, 360 px wide, 16 px side margins:
  TopBar (close, ProgressBar "3 of 9", mute) → GoalCard (picture + sentence; collapses to a one-line
  "Goal" chip after step 1, one tap to open) → StepCard (instruction `size20` Nunito 700; why `size14`
  muted; a "Step 3 changed. Fix it" line when `changed` is not empty) → HelpRow (Show me, Hint,
  Watch the clip / Get the video) → HintList → AskBox (pinned to the bottom) → Banner (over the bottom
  area). `appState: "closed"` shows a card "Excel was closed" with a main button "Reopen Excel"
  (`reopenApp`). The mascot rests at the panel's top-right of the StepCard and reports that rect as
  `mascotHome`.
- On `cue("right")`: banner right with varied words ("Nailed it!", "That's it!", "Spot on!", "You got it!"),
  `+10` in gold floats up 24 px and fades (≤ 400 ms), mascot hop, `right.wav`. On `cue("not_yet")`: rose
  banner with the line, `not_yet.wav`, nothing removed.
- Complete (`complete` not null): the one big celebration — mascot cheer, Confetti burst (≤ 500 ms, never
  blocks input, coral + gold + mint pieces), `complete.wav`, then three cards fill one by one 250 ms apart:
  points, time (m:ss), right first try "7 of 9"; streak +1 with StreakFlame; buttons Next lesson (main)
  and Home (quiet).
- ClipPlayer: `MediaPlayer` + `VideoOutput` 16:9 inside the panel, plays `file` from `start` to `end`
  then stops; `state: "missing"` shows "Get the video" opening `videoUrl` in the browser.

- [ ] **Step 1:** Run `<py> -m pytest tests/ui` (the load test already covers every lesson state) → FAIL
  until the panel parts exist
- [ ] **Step 2:** Implement the panel
- [ ] **Step 3:** `<py> -m pytest tests/ui` → pass
- [ ] **Step 4: Screenshot loop** for `panel` in `lesson_goal`, `lesson_step`, `lesson_right`,
  `lesson_not_yet`, `lesson_hints`, `lesson_changed`, `lesson_clip`, `lesson_clip_missing`, `lesson_ask`,
  `lesson_app_closed`, `lesson_complete`, `long_text`
- [ ] **Step 5:** Run the walkthrough live: `<py> -m app.ui.app --demo walkthrough --show panel,overlay`
  and watch one full pass; note anything that jumps, flickers or lags, fix it
- [ ] **Step 6: Commit**

```bash
git add app/ui/qml
git commit -m "Add the lesson panel: goal first, one short step at a time, Show me, hints, the clip, the Ask box, gentle Not yet and the one big celebration"
```

### Task 7: The home screen

**Files:**
- Fill: `app/ui/qml/HomeWindow.qml`; create `app/ui/qml/home/Header.qml`, `ContinueCard.qml`,
  `CourseShelf.qml`, `CoursePath.qml`, `TipsCard.qml`, `MakeLesson.qml`

**Interfaces:**
- Consumes `bridge.home`. Window 1120 × 720 logical, centred. Header: name, StreakFlame, today's points
  (gold), DailyRing, mute. A big ContinueCard ("Monthly budget · step 4 of 9" is banned punctuation: write
  "Monthly budget, step 4 of 9") with one main button "Continue". CourseShelf: one card per course with
  its course colour as a solid band or edge (not a gradient, not an icon in a circle), progress bar,
  creator credits ("From videos by …"), and "Coming soon" when `ready` is false. Opening a course shows
  CoursePath: a winding path of PathNodes (done ticked, current glowing with the mascot sitting on it,
  locked dim) with the lesson badge ("proven and tested" / "proven") under each title. TipsCard: two or
  three sentences; `loading` shows a calm placeholder after 200 ms; `none` invites "Finish a lesson to get
  tips"; `error` says Meta is unreachable and that lessons still work. MakeLesson: a link field and
  "Make a lesson" button; while running, StageList; `ready` lands a new card on the shelf with a short
  highlight; `not_ready` shows the reason and "Try another video". `meta: "no_key"` shows one calm line
  with the fix ("Add your Meta key to make lessons and get tips").
- The shelf and path must not be rows of identical rounded cards with one soft shadow: vary size by
  importance (Continue largest), use surface steps for depth, and let the path wind.

- [ ] **Step 1:** `<py> -m pytest tests/ui` → FAIL until the home parts exist
- [ ] **Step 2:** Implement the home screen
- [ ] **Step 3:** `<py> -m pytest tests/ui` → pass
- [ ] **Step 4: Screenshot loop** for `home` in `first_run`, `home_progress`, `home_long_text`,
  `home_no_key`, `home_offline`, `course_empty`, `factory_running`, `factory_not_ready`
- [ ] **Step 5: Commit**

```bash
git add app/ui/qml
git commit -m "Add the home screen: continue card, course shelf and path, AI tips, and making a lesson from a video with its live stages"
```

### Task 8: Review pass

- [ ] **Step 1:** Shoot every window in every state (`ui_shot.py --all` writes them all) and make one contact
  sheet `runs/shots/all.png`.
- [ ] **Step 2:** Dispatch a fresh review (the `design:design-critique` skill, or a `code-reviewer` agent
  given `TASTE.md`, the spec sections 2 and 6, and the PNG paths). Ask it for the five worst problems,
  each with the state and the fix.
- [ ] **Step 3:** Fix each one; reshoot; paste the reviewer's list with "fixed" or the reason it was not.
- [ ] **Step 4:** `<py> -m pytest tests/ui` → pass
- [ ] **Step 5: Commit**

```bash
git commit -am "Polish after the review: <the fixes, in plain words>"
```

Final report for the merge: test output, the smoothness line, the contact sheet path, anything the
integration needs (for example new `Bridge` slots it must call).
