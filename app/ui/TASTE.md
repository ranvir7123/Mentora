# Taste brief, banned list and the screenshot checklist

Every screen is judged against this page. The brief and the banned list are copied word for word from the
design (`docs/superpowers/specs/2026-10-29-tutorial-to-practice-design.md`, sections 6.3 and 6.4).

## Taste brief (spec 6.3)

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

## Banned list (spec 6.4)

Purple or blue gradients and gradient text; Inter, Roboto, Arial or Segoe as the look; rows of identical
rounded cards with one soft shadow; emoji as icons; an icon in a coloured circle on every card; a centred
hero with a big number; all-caps spaced-out labels, "A · B · C" strings, arrows on buttons; fade-and-slide on
everything and hover effects on everything; confetti or sound on routine clicks; guilt or urgency copy;
animations over 500 ms or ones that block input.

## The scales (from `qml/Theme/Theme.qml`)

- The look is "Highlighter": a student's desk at night. Warm graphite surfaces, and colour only where a
  highlighter would go: on progress, on the one thing to press, on the few words that matter.
- Colours: base `bg` #1C1B19; surfaces `surface1` #262522, `surface2` #312F2B; `border` #433F39; yellow
  `accent` #F5E15A (progress, the main button, the "you are here" mark); orange `reward` #FFB05C (points,
  streaks, celebrations); green `right` #8EE88B; pink `notYet` #FF8FB1; `text` #F2EFE8; `muted` #ABA69C.
  Words on any highlighter colour are `onColour` (the base graphite). The mascot keeps its own coral
  `mascot` #FF7A45, and the ring round the cell it points at is the same coral (`ring`), so on a white
  sheet they read as one character.
- Courses each have a highlighter of their own: Excel blue #9BD7FF, Python lilac #C9B6FF, Meta peach
  #F2C9A0.
- The mark (`components/Mark.qml`): dark words on a block of colour, as if run over with a marker. Only
  for a few words that matter (a course's name, "Lesson done!", "Not yet"), never for running text.
- Type: Archivo for everything, including every number (its digits are equal width); its wide cut,
  Archivo Expanded ExtraBold, only for the few big words (the greeting, the lesson to carry on, a course's
  name, "Lesson done!"), set 0.5 px tight. Sizes 12/14/16/20/24/32/48. Weights: 400 for text, 700 for
  buttons and labels, 800 for headings.
- Spacing 4/8/12/16/24/32/48. The panel keeps 16 px side margins.
- Corners: `radiusSmall` 2, `radiusMedium` 4, `radiusLarge` 8: cut paper and keycaps, not pills. Progress
  marks are tick boxes, not circles; only the mascot, the daily ring and spinners are round.
- Durations: `durFast` 150, `durNormal` 220, `durPanel` 300. Nothing over 500 ms.

## Checklist for every screenshot (go line by line; fix every failure, then shoot again)

- [ ] Tokens only: no colour written anywhere in QML except `Theme.qml`.
- [ ] Every size, gap and margin is on the scales above; panel side margins are 16 px.
- [ ] No more than three corner sizes on screen.
- [ ] Yellow appears only on progress, the main button and the "you are here" mark; coral only on the
      mascot and its ring; orange only on points, streaks and celebrations.
- [ ] Text contrast is at least 4.5:1 on its surface (muted on `surface2` included).
- [ ] Nothing is clipped, cut mid-letter or overlapping; long text wraps or ends in "…" cleanly.
- [ ] Digits are equal width (numbers in Archivo).
- [ ] Words are plain, second person, sentence case; instructions under 12 words; no "simply" or "just";
      buttons name their action.
- [ ] Nothing from the banned list: no gradients, no emoji icons, no icon-in-a-circle on every card, no
      all-caps labels, no "A · B · C", no arrows on buttons, no rows of identical cards with one shadow.
- [ ] Depth comes from the surface steps; any shadow is rare and two-layered.
- [ ] The state reads at a glance: what happened, and what to do next.
