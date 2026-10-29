# The plan (agreed 29 Oct 2026)

## Who uses it, and where they get stuck

**The learner** is someone who watched Excel tutorials and still can't do the task alone. They want to make a
real thing (a monthly budget) in their own Excel and be able to do it again without help.

**The lesson maker** is a teacher, trainer or company expert who knows Excel and has no time to write lessons.
They want to do the task once and get a lesson that works.

**What the learner sees:** real Excel on the left, a 360 px dark panel on the right. A goal card first: what
you'll make and why it's useful. At each step an orange ring on the real cell or button with one short line
beside it; the panel says why it matters. Done: the ring turns green, a short done card, the next step. A
wrong try: amber "Not yet" plus the one thing to change. Show me where (only on request), three hints that
give away more each time, and a helper you can ask. Each part ends with a three-choice question; the lesson
ends with what you made and what to learn next.

**What the lesson maker sees:** Record, do the task, Stop. Each step appears with its check flipping red
(before the step) to green (after); checks that don't hold are crossed out. Then Meta's agent plays the
learner while the rules grade it, a planted wrong answer is rejected, and the lesson is Published or Not
published, with the reason.

| Where they get stuck | What the design does |
|---|---|
| No sense of purpose | The goal card comes first; the purpose line stays at the top |
| Can't find a ribbon button; on a narrow screen Excel folds it into a drop-down | The ring goes on the drop-down first, then the button; Show me where on request |
| A formula that is almost right | Checks test what the formula computes; "Not yet" names the one thing ("your total skips row 6") |
| Still typing in a cell, so Excel refuses outside calls | The app reads after they leave the cell; Excel never freezes |
| Moves or resizes Excel | The ring follows |
| The AI invents a check that doesn't hold | The before/after proof throws it out; no learner sees a lesson until Meta's agent passes it |

**The rule for everything:** the AI writes, points, explains and gets tested; fixed rules decide. The AI never
marks a step done.

## How it is built

One Python program reads Excel, finds buttons, calls Meta's models and draws the ring and panel (Qt).

## Build order, each with the check that must pass

**Stage 1, foundations (Thu 29 - Fri 30 Oct).** Meta's first tests jump the queue the moment the key works.
1. Repository with a key-leak guard. Check: a commit holding a fake key is refused.
2. Read Excel safely. Check: an automatic test types into Excel for five minutes while the program reads it
   after every change; Excel's window answers within 200 ms throughout and no read is lost. Reruns after every
   change; one run by hand at the end.
3. Ring exactly on a cell. Check: an automatic picture test measures the ring against the cell's edges: within
   2 px at 100%, 150% and 200% scaling, after moving, resizing and scrolling.
4. Meta's first tests. Check: one saved answer each from Muse Spark 1.3 (screenshot plus lesson form), the
   computer-use tool, SAM 3.1 and a short MP4; the credit before and after. Pointing score on 30-50
   screenshots; SAM outlines on 10.

**Fri 30 checkpoint:** Excel is read reliably, the ring sits exactly on a cell, Muse Spark reads a short MP4 of
Excel, and the computer-use tool clicks the right cell at 200% scaling (with how its click positions map to
the screen). If any fails: stop, show the saved answers and what the lesson writer or tester changes to, and
decide together.

**Stage 2, the learner's lesson (Sat 31).**
5. The checker, a fixed menu of check types. Check: every type passes 3 right ways and fails 3 wrong ways.
6. Ring on ribbon buttons. Check: 12 Home and Insert buttons at full width and at 920 px (folded), each with
   Windows' own hit test agreeing.
7. The panel and the whole monthly budget lesson, dark. Check: a scripted run plays every step right and every
   planted wrong try; a screenshot of each state is reviewed; then Ranvir does it once.
8. The helper (Muse Spark), which sees the checker's results and has no way to mark a step done.

**Stage 3, the lesson writer (Sun 1 Nov).**
9. Record the MP4 plus an Excel snapshot after each action; Muse Spark 1.3 fills the lesson form; every check is
   proven false before its step and true after, or thrown out.

**Stage 4, the tester and mistake hunter (Sun 1 - Mon 2).**
10. Meta's computer-use agent plays the learner, graded by the same checks. Its clicks are allowed only inside
    the Excel window; anything else is refused and logged. If it misses small cells it may use keyboard routes
    a learner could use too (the Name Box, shortcuts). A planted wrong answer must be rejected; a lesson that
    fails is not published.
11. Muse Spark predicts likely mistakes at each step; each must be rejected by the checks and gets its own
    "Not yet" line.

**Stage 5, the library (Mon 2).** 12. At least six more lessons, each from a recording and passed by the tester.
Every lesson's sheet fits in the columns Excel shows at 920 px.

**Stage 6, extras, only if everything above never breaks (Mon 2).** Voice (the expert talks while recording),
SAM outlines (only if the SAM test passed), VS Code. Feature freeze Mon 2 Nov night.

**Stage 7.** Sun 1: a rough video cut, its first 10 seconds shown to three people ("what is this?"). Tue 3:
README and final recordings. Wed 4: the video, the X clip, submitted by 6 PM India time.
