# Excel plug-in Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Excel plugs into the core: it opens a lesson's starter workbook, reports every change as a
snapshot without ever freezing Excel, judges steps with a fixed menu of checks, performs a matching menu
of operations for proofs, and says where on screen any cell or ribbon button is.

**Architecture:** Everything that touches Excel runs on one COM thread (`app/excel/com_thread.py`).
Events only mark "something changed"; the read scheduler (`reads.py`) reads a snapshot
(`snapshot.py`) soon after. Checks are pure functions over snapshots. Screen positions come from Excel's
own point-to-pixel conversion for cells and from Windows UI Automation for buttons. `ExcelPlugin`
implements `AppPlugin` from `app/core/plugin.py`.

**Tech Stack:** pywin32 (COM, win32gui), comtypes (UI Automation), openpyxl (starter files), pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-tutorial-to-practice-design.md` (sections 2.2, 2.4, 5.2, 5.3)

## Global Constraints

See `2026-10-29-00-overview.md`, "Global Constraints". Also:
- Excel COM calls only on the COM thread; event handlers never call Excel; never activate a sheet to read it.
- Busy HRESULTs (-2147417846, -2147418111, -2146777998) are retried by `busy.next_delay`, never surfaced.
- Teardown order: sink close → release → `Close(SaveChanges=save)` → gc → `Quit` → gc. Only the program's
  own work copy is ever saved (`close(save=True)`, for resuming); lesson workbooks live in
  `%LOCALAPPDATA%\projectx\work\<lesson id>\`.
- Every starter fits the columns visible at 920 px wide (logical) at 100% zoom.
- Reference only (lift a few small helpers at a time, each in its own "Adapted from Project X :" commit
  plus a README row): `C:\dev\ProjectX\sidecar\adapters\excel.py` (events, teardown),
  `sidecar\pointer\winapi.py` (DPI, window placement), `sidecar\pointer\uia.py` (finding controls,
  hit-test agreement), `sidecar\pointer\targets.py` (Office names with zero-width spaces),
  `sidecar\pointer\watch.py` (window-move hooks), `sidecar\checks\` (check ideas).

## Review Focus

1. The learner is still typing in a cell when a read is due → Excel never freezes; the read lands once they
   leave the cell (Task 3 `test_busy_read_is_retried_until_the_cell_is_left`).
2. A step done a different right way (`=B2+B3+B4+B5+B6` for `=SUM(B2:B6)`; `$B$8` vs `B$8`; a chart made
   from A1:B6 vs B2:B6) → ticks; wrong ways get "Not yet" naming the one difference (Task 4: three right
   ways and three wrong ways per check kind).
3. The learner closes Excel or the workbook mid-lesson → `on_closed` fires once, nothing hangs
   (Task 2 `test_closed_workbook_is_reported`).
4. Excel moved, resized, scrolled, zoomed or with frozen panes while pointing → the spot follows within
   2 px (Task 6 pure tests + the 100/150/200% zoom probe).
5. A ribbon button folded into a drop-down at 920 px → the pointer goes to the drop-down first with
   "open this first", then to the button (Task 6 `test_folded_group_points_at_the_dropdown_first`).

---

## File structure

| File | Job |
|---|---|
| `app/excel/starter.py` | build a starter `.xlsx` from lesson data; `fits_width` |
| `app/excel/session.py` | `ExcelSession`: open, events, reads, idle re-read, perform, place, close |
| `app/excel/checks.py` | the check menu (pure) |
| `app/excel/ops.py` | the operation menu and how each is done through COM |
| `app/excel/locate.py` | cell rectangles (pure maths + COM inputs), ribbon controls via UI Automation |
| `app/win/uia.py`, `app/win/windows.py` | UI Automation helpers; window rects, DPI, placement, move hooks |
| `app/excel/plugin.py` | `ExcelPlugin` |
| `probes/excel_*.py` | live checks, run on purpose |
| `tests/excel/` | tests for all of the above |

---

### Task 1: Starter workbooks

**Files:**
- Create: `app/excel/starter.py`
- Test: `tests/excel/test_starter.py`

**Interfaces:**
- Starter data (the lesson's `starter` field): `{"sheets": [{"name": str, "cells": {addr: value | "=formula"},
  "bold": [range], "formats": {range: format string}, "widths": {column letter: chars}}], "active": str}`
- `validate_starter(data: Mapping) -> list[str]` — sheet names unique and ≤ 31 chars, addresses valid,
  `active` exists, `fits_width(data)`.
- `fits_width(data, width_px: int = 920) -> bool` — for every sheet: row header 30 px + scroll bar 18 px +
  the sum of column widths (`chars * 7 + 5` px; default 8.43 chars) of columns up to the right-most used
  column ≤ `width_px`.
- `build_starter(data, path: Path) -> Path` — writes with openpyxl; returns `path`.

- [ ] **Step 1: Write the failing tests**

```python
def test_budget_starter_builds_and_reads_back(tmp_path):
    data = load_lesson(Path("lessons/monthly-budget")).starter
    p = build_starter(data, tmp_path / "b.xlsx")
    ws = openpyxl.load_workbook(p)["Budget"]
    assert ws["B2"].value == 12000 and ws["A8"].value == "Total"
def test_formulas_bold_formats_and_widths_are_written(tmp_path): ...
def test_wide_sheet_does_not_fit():
    assert not fits_width({"sheets": [{"name": "S", "cells": {"Z1": 1}}], "active": "S"})
def test_budget_starter_fits(): ...
def test_validate_starter_names_problems(): ...   # duplicate sheet, bad address, missing active -> 3 problems
```

- [ ] **Step 2: Run them to see them fail** — `<py> -m pytest tests/excel/test_starter.py` → FAIL (import)
- [ ] **Step 3: Implement `starter.py`**
- [ ] **Step 4: Run them to see them pass** — `5 passed`
- [ ] **Step 5: Commit** — `git commit -m "Add starter workbooks: built from the lesson's data, checked to fit beside the panel"`

### Task 2: The Excel session

**Files:**
- Create: `app/excel/session.py`, `app/win/__init__.py`, `app/win/windows.py`
- Test: `tests/excel/test_session.py`; Probe: `probes/excel_session.py`

**Interfaces:**
- Consumes: `ComThread`, `ReadScheduler`, `read_snapshot`, `build_starter`, core `AppSession`.
- Produces: `ExcelSession(lesson, workdir, *, visible, resume, on_snapshot, on_closed, excel_factory=None)`
  with every `AppSession` method. `excel_factory` (default: `win32com.client.DispatchEx("Excel.Application")`)
  lets tests pass a fake. Opening: with `resume` and an existing `workdir/<lesson id>.xlsx`, open that;
  otherwise build the starter there, a new Excel instance (never the
  learner's own), open the file, a workbook-level event sink (`SheetChange`, `SheetCalculate`,
  `SheetSelectionChange`, `SheetActivate`, `WindowResize`, `BeforeClose`) whose handlers only call
  `scheduler.changed()`. Closed detection: `BeforeClose` plus a 1 s check of `app.Workbooks.Count` and the
  window handle (catches Excel killed outright) → `on_closed()` once.
- `app/win/windows.py`: `window_rect(hwnd) -> Rect` (visible frame, DWM extended bounds),
  `dpi_scale(hwnd) -> float`, `work_area(hwnd) -> Rect`, `place_window(hwnd, rect: Rect) -> None`
  (restore if maximised, then `SetWindowPos`).

- [ ] **Step 1: Write the failing tests** (fake Excel object graph; no real Excel)

```python
def test_open_builds_the_starter_and_delivers_a_first_snapshot(tmp_path): ...
def test_an_event_is_one_read_and_handlers_never_call_excel(tmp_path): ...
    # fake raises if any COM attribute is touched from the event-handler call
def test_closed_workbook_is_reported(tmp_path): ...       # BeforeClose -> on_closed once; Workbooks.Count 0 -> still once
def test_close_tears_down_in_order(tmp_path): ...          # recorded calls: sink close, Close(SaveChanges=False), Quit
def test_close_with_save_keeps_the_work_copy_and_resume_opens_it(tmp_path): ...
```

- [ ] **Step 2: Run them to see them fail** — FAIL (import)
- [ ] **Step 3: Implement `session.py` and `windows.py`** (lift event and teardown helpers from the old
  `adapters/excel.py` in their own "Adapted from Project X :" commit if you use them)
- [ ] **Step 4: Run them to see them pass** — `4 passed`
- [ ] **Step 5: Live probe** (memory check first) — `<py> probes\excel_session.py`: opens the budget starter
  visibly, types into B8 through `SendInput`, prints each snapshot's B8, closes Excel by hand when asked,
  prints `closed reported`. Paste the output.
- [ ] **Step 6: Commit** — `git commit -m "Add the Excel session: its own Excel, change events that only ask for a read, closing noticed, clean teardown"`

### Task 3: Reads, busy Excel and the idle re-read

**Files:**
- Modify: `app/excel/session.py`
- Test: `tests/excel/test_session_reads.py`

**Interfaces:**
- `set_waiting(True)` starts a 1 s `call_later` loop that calls `scheduler.read_soon()` (catches freeze
  panes and sheet renames, which fire no event); `set_waiting(False)` stops it. `read_now()` returns a
  Future resolved by the next delivered snapshot.

- [ ] **Step 1: Write the failing tests**

```python
def test_busy_read_is_retried_until_the_cell_is_left(): ...
    # fake workbook raises the busy HRESULT for 3 s of fake time (learner in edit mode), then reads;
    # the snapshot is delivered once, Excel was never called from an event handler, nothing raised
def test_idle_reread_runs_every_second_only_while_waiting(): ...   # 3 ticks while waiting, 0 after
def test_read_now_resolves_with_the_next_snapshot(): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass** — `3 passed`
- [ ] **Step 5: Commit** — `git commit -m "Read Excel after every change and once a second while a step waits, retrying quietly while the learner types"`

### Task 4: The check menu

**Files:**
- Create: `app/excel/checks.py`
- Test: `tests/excel/test_checks.py`

**Interfaces:**
- `CHECKS: dict[str, CheckKind]`, each `run(snapshot: Snapshot, args) -> Verdict`. Addresses may carry a
  sheet (`Budget!B8`); without one, the active sheet. "attempted" rules in brackets.

| kind | params | right when | wrong codes and "Not yet" lines |
|---|---|---|---|
| `value_equals` | cell, value | text equal after trim and case-fold; numbers within 1e-9 relative [cell not empty] | `differs` "Not yet: that says X. It should say Y." |
| `formula` | cell, value?, covers? (range), uses? (function), absolute? (cells) | is a formula; refers to every cell of `covers`; uses `uses`; each `absolute` ref is `$C$R`; value within 1e-6 relative [cell not empty] | in this priority: `typed_value` "Not yet: that's a typed number. Start with = instead."; `uses_missing:F` "Not yet: use F here."; `covers_missing:A` "Not yet: your formula skips A."; `refers_extra:A` "Not yet: that's A, try B."; `not_absolute:A` "Not yet: lock A as $A$1 so it stays put."; `value:V` "Not yet: that gives V. Check the cells it uses." |
| `filled_formula` | range, first | every cell's formula, made relative to its own row and column, equals `first`'s [any cell below the first not empty] | `gap:A` "Not yet: fill all the way down to A."; `differs:A` "Not yet: A has a different formula." |
| `number_format` | range, kind (`currency` `percent` `date` `decimal2` `whole`) | every cell's format is that kind (currency = a ₹ $ € £ sign or `[$`) [any cell not General] | `kind:K` "Not yet: that's K. Pick X instead." |
| `bold` | range | every cell bold [any cell bold] | `partial:A` "Not yet: A needs bold too." |
| `chart` | chart_type (`column` `bar` `line` `pie`), over? (range), title? | a chart of that type whose series values include `over` (headers allowed) [any chart] | `type:T` "Not yet: that's a T chart. Pick the X."; `over` "Not yet: the chart uses other cells." |
| `frozen` | rows, cols | frozen rows and columns equal [any freeze] | `frozen:R,C` "Not yet: freeze only the top row." (worded from the numbers) |
| `filter` | range, column?, criteria? | a filter on the range, and on that column with that criterion [any filter] | `column`, `criteria` |
| `sorted` | range, column (letter), order (`asc` `desc`) | the column's values in the range are in that order [sorted the other way or by another column] | `order` "Not yet: that's smallest first. Flip it." |
| `selected` | range | the selection equals the range [always] | `selected:A` "Not yet: that's A, try B." |
| `sheet_named` | name, index? | a sheet with that name exists (at that index) [sheet names changed] | `name:N` |

- [ ] **Step 1: Write the failing tests** — per kind, three right ways and three wrong ways, plus one
  untouched snapshot that is `Verdict.waiting()`. Built with the `Snapshot`, `Sheet`, `Cell`, `Chart`,
  `Filter` dataclasses. For `formula` the right ways are `=SUM(B2:B6)`, `=B2+B3+B4+B5+B6`,
  `=SUM(B2:B4)+SUM(B5:B6)`; the wrong ways are `=SUM(B2:B5)` (`covers_missing:B6`), the typed `23000`
  (`typed_value`) and `=SUM(B3:B7)` (`covers_missing:B2`). For the share step: `=B2/$B$8` and `=B2/B$8`
  is wrong for `absolute: [B8]` (`not_absolute:B8`), `=B2/B8` wrong, `=$B2/$B$8` right.
- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement `checks.py`** using `app/excel/formula.py` (`refs_of`, `functions_of`,
  `absolute_refs_of`) and expanding ranges to cell sets for `covers`
- [ ] **Step 4: Run them to see them pass** — all pass; paste the count
- [ ] **Step 5: Commit** — `git commit -m "Add the Excel check menu: fixed rules that accept every right way and name the one difference in a wrong one"`

### Task 5: The operation menu

**Files:**
- Create: `app/excel/ops.py`; wire `ExcelSession.perform` and `reset`
- Test: `tests/excel/test_ops.py`; Probe: `probes/excel_ops.py`

**Interfaces:**
- `OPS: dict[str, OpKind]` and `do(app, wb, op: Call) -> None` (COM thread only):
  `set_value{cell, value}`, `set_formula{cell, formula}`, `fill_down{source: cell, range}`,
  `set_format{range, kind}` (currency `"₹"#,##0`, percent `0%`, date `dd-mmm-yyyy`, decimal2 `0.00`, whole
  `0`), `set_bold{range, on?}`, `add_chart{chart_type, source: range, title?}`, `freeze{rows, cols}`,
  `filter{range, column, criteria}`, `sort{range, column, order, header}`, `rename_sheet{old, new}`,
  `select{range}`, `clear{range}`. `reset()` closes the workbook without saving, rebuilds the starter and
  reopens it.

- [ ] **Step 1: Write the failing tests** — with a recording fake COM object: each op makes the expected
  calls (for example `freeze{rows: 1, cols: 0}` sets `SplitRow=1`, `SplitColumn=0`, `FreezePanes=True`
  on the window, never activating a sheet other than the op's own); every op name in `OPS` has a `do` branch.
- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Live probe** (memory check first) — `<py> probes\excel_ops.py` runs every budget step's
  replay on an invisible Excel and, before and after each, its check: prints
  `<step id>: before=<ok> after=<ok>` for all nine, expected `before=False after=True` each, then every
  mistake: `<step id> mistake <n>: ok=False code=<code>`. Paste the output. Put the printed codes into the
  budget lesson's `mistakes[].code` only if plan 06 asks (the factory's mistake hunter fills them later).
- [ ] **Step 6: Commit** — `git commit -m "Add the Excel operation menu used to prove checks, with reset to the starter"`

### Task 6: Where things are on screen

**Files:**
- Create: `app/excel/locate.py`, `app/win/uia.py`
- Test: `tests/excel/test_locate.py`; Probe: `probes/excel_locate.py`

**Interfaces:**
- Pure: `cell_rect(pane: PaneInfo, left_pt, top_pt, width_pt, height_pt) -> Rect` where
  `PaneInfo(screen_x0: float, screen_y0: float, scroll_left_pt: float, scroll_top_pt: float, zoom: float,
  px_per_pt: float, visible: Rect)`; `pane_for(cell_row, cell_col, frozen_rows, frozen_cols) -> int`
  (1–4); `clip_to(rect, visible) -> Rect | None` (None when scrolled out of view).
- COM inputs (COM thread): `ActiveWindow.Panes.Item(i)` `PointsToScreenPixelsX/Y`, `ScrollRow`,
  `ScrollColumn`, `Zoom`, the range's `Left/Top/Width/Height`. Whether `PointsToScreenPixels` already
  returns physical pixels at 200% is measured by the probe and written in the module docstring.
- Controls: `find_control(hwnd, path: str) -> Spot | None` for targets like `"Insert > Pie"`: finds the tab,
  then the button by name (Office names may contain zero-width spaces; compare after removing them and
  case-folding). If the button is off screen because its group is folded, return the group's drop-down
  with `bubble="open this first"`; once the drop-down is open, the button. Also `formula_bar`, `name_box`,
  `sheet_tab` targets.
- `ExcelSession.locate(target)` and `watch(target, on_spot)`: while watched, re-locate every 100 ms on the
  COM thread (skipped quietly while Excel is busy) and on window-move events; call `on_spot` when the
  spot changes by 1 px or more, or becomes None.
- Vision fallback hook: `ExcelSession.set_vision_fallback(fn: Callable[[bytes, str], Rect | None])` —
  used only when UI Automation finds nothing; a returned rect is accepted only when the UI Automation
  element at its centre has a name matching the target (wired in plan 06).

- [ ] **Step 1: Write the failing tests**

```python
def test_cell_rect_at_100_and_200_percent_zoom(): ...
def test_scrolled_cell_moves_left_by_the_scroll(): ...
def test_cell_in_frozen_rows_uses_the_top_pane(): ...
def test_cell_scrolled_out_of_view_is_none(): ...
def test_names_with_zero_width_spaces_match(): ...
def test_folded_group_points_at_the_dropdown_first(): ...   # fake UIA tree: button offscreen, group dropdown visible
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Live probe** (memory check first) — `<py> probes\excel_locate.py`: places Excel at 920 px
  beside an empty 360 px strip, then for B8, C2, A1:C1 at zoom 100, 150 and 200, scrolled and not, and with
  row 1 frozen: compares `cell_rect` with the UI Automation bounding box of the same cell and prints the
  largest difference. Pass: ≤ 2 px everywhere. Then `Insert > Pie`, `View > Freeze Panes`,
  `Data > Sort Largest to Smallest`: prints each spot and bubble. Paste the output.
- [ ] **Step 6: Commit** — `git commit -m "Find cells and ribbon buttons on screen, following scrolls, zoom and moves, with the folded-ribbon route"`

### Task 7: The plug-in

**Files:**
- Create: `app/excel/plugin.py`
- Test: `tests/excel/test_plugin.py`; Probe: `probes/excel_budget_replay.py`

**Interfaces:**
- `ExcelPlugin()` implements `AppPlugin`: `app_id="excel"`, `title="Excel"`, `checks=CHECKS`, `ops=OPS`,
  `target_kinds={"cell", "range", "control", "formula_bar", "name_box", "sheet_tab"}`,
  `validate_starter`, `open(...) -> ExcelSession`.

- [ ] **Step 1: Write the failing test**

```python
def test_budget_lesson_is_valid_for_excel():
    assert validate(load_lesson(Path("lessons/monthly-budget")), ExcelPlugin()) == []
def test_schema_offers_only_excel_menus(): ...   # lesson_json_schema(ExcelPlugin()) check enum == sorted(CHECKS)
```

- [ ] **Step 2: Run it to see it fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run it to see it pass**; then `<py> -m pytest` → everything passes
- [ ] **Step 5: Live probe** — `<py> probes\excel_budget_replay.py`: opens the budget lesson visibly with
  `LessonRun` attached, performs each step's replay 1 s apart, prints the runner's events. Expected: nine
  `StepPassed` then `LessonDone`. Paste the output.
- [ ] **Step 6: Commit** — `git commit -m "Add the Excel plug-in: the budget lesson runs start to finish on real Excel"`

### Task 8: The typing test (once, Mon 2 Nov, before the freeze)

**Files:**
- Create: `probes/excel_typing_test.py`

- [ ] **Step 1:** Write the probe: opens the budget lesson with its session and watching on, then for five
  minutes types into cells through `SendInput` at a learner's pace (5–8 keys per second, Enter between
  cells, some edits that stay in edit mode for 3 s), while the session reads, re-reads every second and
  re-locates every 100 ms. At the end it compares every cell it typed with Excel's values.
- [ ] **Step 2:** Run it only after Ranvir says he is away from the machine (it types for real). Expected
  last line: `typed=<n> lost=0 max_lag_ms=<n> busy_retries=<n> errors=0`. Paste it.
- [ ] **Step 3: Commit** — `git commit -m "Add the five-minute typing test: <paste the last line>"`

Final report for the merge: test output, every probe's pasted output, the measured pixel rule from Task 6,
and anything the integration needs.
