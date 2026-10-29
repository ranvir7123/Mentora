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

- Colours: base `bg` #151A2E; surfaces `surface1` #1E2440, `surface2` #282F52; `border` #363E66; coral
  `accent` #FF7A45 (progress, the main button, the ring, the mascot's body); gold `reward` #FFC53D (points,
  streaks, celebrations); mint `right` #3DDC97; rose `notYet` #FF6B81; `text` #EEF1FA; `muted` #9AA3C0.
  Words on coral, gold, mint or rose are `onColour` (the base navy): near-white on coral is only 2.2:1.
- Type: Fredoka for headings, Nunito for text and for every number (Nunito's digits are equal width;
  Fredoka's are not). Sizes 12/14/16/20/24/32/48. Weights paired far apart: 400 with 700 or 800.
- Spacing 4/8/12/16/24/32/48. The panel keeps 16 px side margins.
- Corners: `radiusSmall` 6, `radiusMedium` 12, `radiusLarge` 20. Circles are circles.
- Durations: `durFast` 150, `durNormal` 220, `durPanel` 300. Nothing over 500 ms.

## Checklist for every screenshot (go line by line; fix every failure, then shoot again)

- [ ] Tokens only: no colour written anywhere in QML except `Theme.qml`.
- [ ] Every size, gap and margin is on the scales above; panel side margins are 16 px.
- [ ] No more than three corner sizes on screen.
- [ ] Coral appears only on progress, the main button, the ring and the mascot; gold only on points,
      streaks and celebrations.
- [ ] Text contrast is at least 4.5:1 on its surface (muted on `surface2` included).
- [ ] Nothing is clipped, cut mid-letter or overlapping; long text wraps or ends in "…" cleanly.
- [ ] Digits are equal width (numbers in Nunito).
- [ ] Words are plain, second person, sentence case; instructions under 12 words; no "simply" or "just";
      buttons name their action.
- [ ] Nothing from the banned list: no gradients, no emoji icons, no icon-in-a-circle on every card, no
      all-caps labels, no "A · B · C", no arrows on buttons, no rows of identical cards with one shadow.
- [ ] Depth comes from the surface steps; any shadow is rare and two-layered.
- [ ] The state reads at a glance: what happened, and what to do next.
