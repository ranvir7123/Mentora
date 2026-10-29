# Design: tutorials you do for real (29 Oct 2026)

This replaces the expert-recording design in `docs/plan.md`. Working name: Project X (the public name and
the mascot's name are Ranvir's to pick; until then the code says `projectx` and the mascot is "the guide").

## 1. Intent

People watch a YouTube tutorial, nod along, open Excel, and are stuck. Udemy-style courses are the same:
video you watch, not work you do. This app takes a popular tutorial and turns it into a lesson you do
**inside the real software**: a small mascot flies to the real cell or button, you do the step yourself,
and fixed rules reading the app's real state tick it. Meta's models make the lessons (from the video),
prove them, test them, and coach the learner. The AI never decides that a step is done.

Pitch line: "Clicky shows you. We prove you did it." Positioning: a library that can grow as fast as
YouTube does, because a lesson is generated, proven and tested by machines in minutes.

It is our entry to the Meta Global AI Developer Hackathon (Indie track, "Build for Your World").

## 2. Who uses it and what they see

**The learner** watched tutorials and still can't do the task alone. They want to make a real thing
(a monthly budget, a grade sheet, a first Python app) in their own copy of the real app, and be able to do
it again without help.

**The lesson maker** is us for now (later, creators). They paste a YouTube link and want a lesson that works,
without writing anything.

### 2.1 Home screen (the app's main window)
- Top: the learner's name, a streak flame, today's points, a daily-goal ring.
- A big Continue card: the lesson in progress ("Monthly budget · step 4 of 9") and one button.
- Course shelf: Excel; Python in VS Code; Build with Meta's AI. Each card: its colour, a progress bar, the
  creator credit of its source videos. Not-yet-ready courses are shown as "Coming soon", never as fake content.
- Course path: opening a course shows a winding path of lesson circles: done (ticked), current (glowing,
  the mascot sitting on it), locked.
- AI tips card: two or three plain sentences written by Muse Spark from the learner's real attempt log
  (tries per step, hints used, time). Example: "Formulas: fast. Charts took 3 tries. Try the chart review."
- Make a lesson from a video: paste a YouTube link; the screen shows each stage live (getting the video →
  reading it → writing the steps → proving every check in Excel → Meta's agent testing it → ready or
  not ready, with the reason). A ready lesson lands on the shelf with the creator credited.
- States that must be designed: first run (no progress yet), no lessons in a course, a lesson that failed
  its tests, Meta unreachable / no key, very long titles.

### 2.2 Lesson panel (360 px, right edge; the real app fills the rest of the screen)
- Top: close, a thick rounded progress bar, "3 of 9".
- Goal card first: a picture of the finished result and one sentence on what you'll make and why.
- Each step: one instruction of at most 12 words; the "why" in a smaller, quieter line.
- Pointing: the mascot flies in a curve from the panel to the real target, lands beside it (never on it)
  with a tiny bubble ("this one!"), and a soft ring pulses around the target. Clicks pass through to the app.
- Check passes: the ring turns green, a banner slides up ("Nailed it!", wording varies), a short rising
  two-note sound, +10 points, the mascot does a small happy hop. Then the next step.
- Wrong try: a gentle rose banner, "Not yet: that's B3, try C3." Nothing is taken away; no lives, no energy.
- Help row: Show me (the mascot flies there again), Hint (three hints, each giving away more), Watch the clip
  (plays just this step's seconds of the source video inside the panel, from our local copy).
- Ask box: type a question; Muse Spark answers using the current step, the check results and a summary of
  the app's state. It has no way to tick a step.
- Lesson complete: the one big celebration (mascot cheer, a short confetti burst, a rising chime); three
  cards fill in one by one (points, time, right first try); streak +1; Next lesson / Home.
- If an earlier step gets undone (the learner deletes a finished formula), a calm line appears: "Step 3
  changed. Fix it" with a link back. (Claude's call.)

### 2.3 The mascot (also the pointer)
A small round character of our own: not an owl, not Duolingo's green, not Clicky's blue triangle. Five
states: resting, flying to point, watching (while the learner works), thinking (while a check reads), cheering.
Built by hand from Qt Quick shapes so it animates smoothly; no Rive, no Lottie dependency.

### 2.4 Where they get stuck, and what the design does
| Stuck point | Design answer |
|---|---|
| No sense of purpose | Goal card first; the goal stays one tap away |
| Can't find a ribbon button; at 920 px Excel folds it into a drop-down | Target the drop-down first, then the button; Show me on request |
| A formula that is almost right | Checks test what the formula refers to and computes; "Not yet" names the one difference |
| Still typing in a cell (Excel refuses outside calls) | Reads retry quietly until the cell is left; Excel never freezes |
| Moves, resizes or scrolls the app | The ring and mascot follow |
| An action that fires no Excel event (freeze panes, rename a sheet) | A gentle re-read every second while a step waits |
| Wants to see how it was done | Watch the clip, at this step's timestamp |
| The AI invents a check that doesn't hold | The before/after proof throws it out; no lesson reaches the shelf until Meta's agent passes it |

## 3. Goals, non-goals, anti-goals

**Goals.** They are built at the same time by several AI coding sessions (Ranvir asked for parallel
building). The order below is the order in which pieces must become solid and get joined: a later goal
never appears in the demo until the goals above it work every time.
1. The Excel lesson experience end to end (home → lesson in real Excel → complete → home), polished.
2. Make a lesson from a YouTube video: download, Muse Spark writes it, every check proven in real Excel.
3. Meta's computer-use agent tests each lesson as a learner; Muse Spark's predicted mistakes must be rejected.
4. A library: at least 6 Excel lessons from real tutorials, all proven and tested.
5. A second app, VS Code with Python, through the same plug-in shape, including a "Build your first app with
   Meta's AI" lesson. This proves "any software", not just Excel.
6. AI tips on the home screen and the Ask box.
7. Extras only after 1–6 never break: ask by voice (Muse Voice Transcribe), SAM 3.1 outlines on targets,
   a third app.

**Non-goals:** accounts, cloud sync, payments, a web version, Mac, Blender, running models on the laptop,
generating images for courses.

**Anti-goals (a failure even if it works):**
- It looks like generic AI output (see the banned list, section 6.4).
- It reads as an "AI for Education chatbot": no "tutor", "AI teacher" or "chat" in the name or the first
  sentence of the README or video. The Ask box is a side feature.
- The AI ever ticks a step, or a lesson reaches the shelf without passing its proof and its test.
- Guilt-trip streak messages, fake urgency, penalties for mistakes.
- Excel freezes or loses the learner's work.
- A README claim that the code doesn't back up.

## 4. Constraints

- **Deadline:** submit Wed 4 Nov, 6 PM India time (official cutoff Thu 5 Nov, 7:30 AM). Feature freeze
  Mon 2 Nov night. Tue 3: README and final screen recordings. Wed 4: video (3 minutes, finished by 2:55),
  X clip, submission.
- **New work only:** the demo shows only what was built during the event. The old Project X
  (github.com/ranvir7123/project-x, `C:\dev\ProjectX`) is a reference: small helpers may be lifted a few at
  a time, each in its own commit starting "Adapted from Project X :" and listed in the README. Its screen
  design is not used at all.
- **Meta models only** (Muse Spark series, Muse Wonder, Muse Image, Muse Voice Transcribe, SAM 3.1,
  Glimmer / Spark Open, Muse Code agent; never "-contributor" versions). API: https://api.meta.ai/v1,
  OpenAI-compatible. Key from `META_API_KEY` (program environment, then saved user settings). Never commit a
  key; the pre-commit and pre-push guards stay on.
- **YouTube:** videos are downloaded with yt-dlp for the hackathon (Ranvir's choice; it breaks YouTube's
  terms of use). To keep the risk low: prefer Creative Commons videos for everything shown in the demo,
  credit and link every creator in the lesson and the README, and never commit a video (they live under
  `recordings/`, which git ignores). If the project grows, videos are bought from creators.
- **Machine:** Windows 11, screen 1280 px wide at 200% scaling, 15.3 GB memory with little free, 6 GB GPU.
  Excel gets about 920 px beside the 360 px panel, so the ribbon folds; every lesson's sheet fits in the
  columns visible at 920 px.
- **Dark mode only.** Never design, check or mention a light mode.
- **Tests:** keep them short and automatic (seconds). Pure logic gets unit tests; each live piece gets one
  short live check; the five-minute typing test runs once before the freeze, not after every change.
- **Who builds, and on what:** AI coding sessions, all on Ranvir's one laptop, each in its own git
  worktree. Ranvir starts each session himself from a prompt Claude writes. Anything needing real Excel,
  real screenshots at 200% or the tester runs one session at a time; everything else runs against fake
  snapshots and saved Meta answers, so it never needs the real apps. Ranvir approved the plan as a whole;
  he does not approve each screenshot. Before any live run, free memory is checked and Ranvir is told which
  sessions to close. The tester (it moves the real mouse) runs only after Ranvir says he is away.
- **Spending:** every Meta call is logged with its cost in a local file. Tests replay saved Meta answers;
  live calls happen only in pipeline runs and named live checks. At $100 spent, stop and tell Ranvir.
- **Videos:** short (under about 15 minutes), single-task tutorials, hand-picked. Claude proposes a
  shortlist (Creative Commons first, sheets that fit 920 px, tasks the check menu covers); Ranvir approves
  it. Long multi-topic videos are out of scope.
- **Judges:** the submission is the video plus a readable public repository. The README gives setup steps
  for anyone with Windows, desktop Excel and their own Meta key. When a lesson's video isn't on the machine,
  Watch the clip becomes "Get the video". Whether judges install entries stays a Discord question.

## 5. How it is built (decided)

### 5.1 One Python program
Python 3.12, PySide6 (the full package: Qt Quick for all screens, Qt Multimedia for sounds and clips),
pywin32 and comtypes for Excel and Windows UI Automation, the `openai` client pointed at Meta, yt-dlp and
ffmpeg for videos. Screens are Qt Quick (QML), not classic Qt widgets. All animation lives in QML.

Three windows: the home window; the lesson panel (360 px, docked right); a transparent, click-through,
always-on-top overlay covering the screen, which draws the ring and the flying mascot.

### 5.2 App plug-ins
Every app (Excel, VS Code, later others) plugs in through one interface, so a new app is a new folder,
not a rewrite. A plug-in provides:
- **launch / attach**: open the app with the lesson's starter file; give its main window handle.
- **snapshot**: the app's state as plain data (Excel: values, formulas, number formats, bold, charts,
  filters, frozen rows, active sheet, selection). Checks only ever see snapshots.
- **change signal**: tells the core something changed (Excel: workbook events), plus the idle re-read.
- **check kinds**: a fixed menu of pure functions over snapshots (Excel examples: cell value equals,
  formula refers to / uses function, number format is currency, cell is bold, a chart of type X over range Y
  exists, header row frozen, column filtered). The AI may only choose from this menu and fill in arguments.
- **replay operations**: a matching menu of operations the program can perform through the app's own
  automation (set value, set formula, fill down, set format, bold, add chart, freeze, filter, sort), used to
  prove checks and to plant wrong answers. Never shown to the learner.
- **locator**: turns a step's target (a cell or range, a ribbon button by name, the formula bar, an editor
  line) into a screen rectangle. Excel cells: Excel's own cell-to-pixel conversion per pane, scaled by hand
  for DPI. Buttons: Windows UI Automation, with the folded-ribbon route. Fallback: Muse Spark points on a
  screenshot, accepted only when UI Automation agrees.
- **starter builder**: creates the lesson's starting file from the lesson's data, sized to fit 920 px.

The Excel plug-in already has: the COM thread with a sleeping message pump, busy-signal retry, formula
reading, the snapshot reader and the read scheduler (`app/excel/`).

VS Code plug-in: a small VS Code extension reports state (open files and their text, the last terminal
run and its output, problems list) to the Python program over a local socket; checks run on those
snapshots; editor positions come from the extension, buttons from UI Automation.

### 5.3 A lesson (one JSON file per lesson, validated by a schema)
Metadata (title, app, course, source video URL, creator name and channel link, licence, length), the goal
(sentence + picture of the result), the starter data, and steps. Each step: instruction (≤ 12 words), why,
target, check (a check kind + arguments), the replay operation that does it, three hints, predicted
mistakes (each a replay operation + its own "Not yet" line), and the clip's start and end seconds.
A lesson also records its proof results and its test results; only lessons with both passed appear on
the shelf.

A person may edit a generated lesson (wording, hints, starter data). Every edit re-runs the proof and the
test, the lesson records that it was edited by hand, and the README says lessons are generated and then
reviewed. The first monthly-budget lesson is written by hand so the screens can be built against it; it is
replaced by one made from a video once the pipeline works.

VS Code lessons use the same format and the same proof (the extension can write files and run the
learner's code). The agent tester is pointed at VS Code only after it works in Excel.

### 5.4 Making a lesson from a video
1. Get the video: yt-dlp downloads it (and its captions when they exist) into `recordings/`.
2. Prepare: ffmpeg makes a small MP4 for Muse Spark and pulls frames at scene changes. No captions → Muse
   Voice Transcribe writes the transcript.
3. Write: Muse Spark 1.3 reads the MP4 (or frames, if the MP4 is refused) plus the transcript and fills the
   lesson form, choosing only from the plug-in's menus.
4. Prove: the program builds the starter file, then for each step performs its replay operation in real
   Excel; the step's check must be false before and true after. A failing check is sent back to Muse Spark
   once with the reason; if it fails again the step is dropped and the lesson says so.
5. Hunt mistakes: each predicted mistake is performed; the check must reject it, and the mistake keeps its
   own "Not yet" line. A mistake the check accepts means the check is too loose: back to step 3 once.
6. Test: Meta's computer-use agent plays the learner from the lesson's instructions, graded by the same
   checks. It may click only inside the app's window (anything else is refused and logged); it may use
   keyboard routes a learner could use (Name Box, shortcuts), and the README says so. It runs only when
   Ranvir is away from the machine, because it moves the real mouse.
7. Publish to the shelf, or show "not ready" with the reason.

### 5.5 Progress and coaching
Everything stays on the laptop (`%LOCALAPPDATA%\projectx\`): progress, streak, points, the attempt log.
AI tips and the Ask box send Muse Spark a small summary, never the whole workbook.

## 6. Look and feel (decided direction)

### 6.1 References
Duolingo for warmth, chunky friendly controls, the path, the feedback banners and the one big celebration.
Hey Clicky for the flying pointer that lands beside the target and the short, warm, spoken-style words.
Our own brand: no copying either one's colours, characters, fonts or catchphrases.

### 6.2 Starting tokens (Claude's call; the first UI task may refine them, judged by screenshots)
- Base: deep midnight navy (around #151A2E), two surface steps above it (around #1E2440, #282F52) and one
  border (around #363E66). Not a neutral near-black.
- Signature accent, only for progress, the main button, the ring and the mascot's body: warm coral
  (around #FF7A45), with a darker bottom edge for chunky buttons.
- Reward colour, only for points, streaks and celebrations: gold (around #FFC53D).
- Right: mint (around #3DDC97). Not yet: soft rose (around #FF6B81). Text: near-white (#EEF1FA) and muted
  (#9AA3C0).
- Type: Fredoka for headings, Nunito for text, both bundled (free licences); equal-width digits for numbers.
  Sizes 12/14/16/20/24/32/48; weights paired far apart (400 with 700+).
- Spacing 4/8/12/16/24/32/48; the panel has 16 px side margins; at most three corner sizes.
- Buttons: chunky, rounded, a 4 px darker bottom edge; pressing moves them down and shrinks to 0.97.

### 6.3 Taste brief (goes into every UI task)
1. A calm, friendly coach for a student, not a dashboard.
2. Dark only; one deliberate base, two surface steps, one border.
3. One signature accent for progress and the main action; one reward colour for celebrations only.
4. Two typefaces with distinct jobs; sizes and spacing only from the scales above.
5. Depth from surface steps first; shadows rare and two-layered.
6. Motion: ease-out, 150–250 ms for small things, 200–350 ms for the panel; everything can be interrupted;
   only position, scale and opacity animate; frequent actions get no animation.
7. Springs only for things that move (the mascot, the panel), with little bounce.
8. Small wins get a quiet tick; only a finished lesson gets the big celebration.
9. The mascot points beside the real target, waits, then returns; it never covers the target.
10. Every state designed: first run, empty, loading (shown only after 200 ms), error with a fix, long text,
    200% scaling.
11. Words: plain, second person, sentence case, under 12 words for instructions, never "simply" or "just";
    buttons name their action.
12. Sounds: one related family, short (clicks under 150 ms, rewards under 500 ms), rising for success,
    with a mute switch and a visual twin for every sound.

### 6.4 Banned list
Purple or blue gradients and gradient text; Inter, Roboto, Arial or Segoe as the look; rows of identical
rounded cards with one soft shadow; emoji as icons; an icon in a coloured circle on every card; a centred
hero with a big number; all-caps spaced-out labels, "A · B · C" strings, arrows on buttons; fade-and-slide on
everything and hover effects on everything; confetti or sound on routine clicks; guilt or urgency copy;
animations over 500 ms or ones that block input.

### 6.5 How UI gets built
Tokens and the taste brief first, saved in the repo. One component at a time; after each, a screenshot is
taken at 200% scaling and compared against the brief and the banned list, then fixed before moving on. A
separate review pass on each finished screen. A short smoothness test of the mascot at 200% scaling comes
before the mascot is built for real.

## 7. Meta's models: which does what
| Job | Model |
|---|---|
| Write a lesson from a video | Muse Spark 1.3 (video + transcript in, lesson form out) |
| Transcript when a video has no captions; voice questions (extra) | Muse Voice Transcribe |
| Predict likely mistakes | Muse Spark 1.3 |
| Play the learner to test a lesson | Meta's computer-use tool (Responses API, `{"type": "computer"}`), Muse Wonder 1.0 by default, Muse Spark 1.3 to save money |
| Point when UI Automation can't find a button | Muse Spark 1.3 on a screenshot, cross-checked |
| AI tips; Ask box | Muse Spark 1.3 |
| Outlines that hug a target (extra, only if its test passes) | SAM 3.1 |

**Go / no-go tests, in the first hours after the key works** (the old Fri 30 checkpoint, kept): Muse Spark
reads a short Excel MP4 and fills the lesson form; the computer-use tool clicks a named cell in Excel at
200% (and how its click positions map to the screen is written down); the credit left is noted. Saved
answers are kept as test data.

If the computer-use tool can't play the budget lesson in at least 4 of 5 runs, the tester switches to
keyboard routes only (Name Box, shortcuts). If that also fails, a lesson reaches the shelf on its proof
alone, its card shows "proven" instead of "proven and tested", and the README says so. Ranvir is told the
moment either switch happens.

## 8. The demo (3 minutes)
Hook: a YouTube tutorial playing; someone tries it in Excel and is stuck. Paste the link; watch the lesson
being written, proven and tested. Do the lesson: the mascot flies, a tick, a planted wrong try gets "Not
yet", the lesson-complete moment. Home: progress and AI tips. A few seconds of the VS Code "Build your first
app with Meta's AI" lesson. Close on "Clicky shows you. We prove you did it." First 10 seconds shown to three
people on Sun 1 Nov with the question "what is this?".

## 9. Left to the builder
File and module layout beyond `app/excel/`; the exact lesson JSON field names; the QML component split;
the exact easing curves and spring numbers within the brief; the sounds themselves (made or chosen, free
licence); the mascot's exact shape within section 2.3; how the VS Code extension talks to the program.

## 10. Calls Claude made (check these)
- VS Code with Python is the second app, and "Build your first app with Meta's AI" is the Meta-related lesson.
- Screens are built in Qt Quick (QML) inside the one Python program.
- The starting colours, fonts (Fredoka + Nunito) and the coral accent.
- The mascot is also the pointer, built by hand from shapes.
- "Step 3 changed. Fix it" when earlier work gets undone.
- A failed proof gets one retry from Muse Spark, then the step is dropped.
- The typing test runs once before the freeze instead of after every change.
- Hand edits to generated lessons are allowed, re-proven, re-tested and labelled.
- Short, single-task videos only; Claude proposes the shortlist, Ranvir approves it.
- The tester's fallbacks (keyboard only, then "proven" only) and the 4-of-5 bar.
- The $100 stop-and-tell on spending.
- "Get the video" when a lesson's video isn't on the machine.
