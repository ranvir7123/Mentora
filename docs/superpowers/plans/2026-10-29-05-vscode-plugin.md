# VS Code plug-in Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second app through the same plug-in shape: VS Code with Python, with a "Your first Python
program" lesson and a "Build your first app with Meta's AI" lesson, proving the engine works for any
software, not just Excel.

**Architecture:** A small VS Code extension (TypeScript) reports the editor's state to the Python program
over a local socket and carries out replay operations. On the Python side `VsCodeSession` turns those
reports into snapshots; checks are pure functions over them (Python's `ast` for code facts). Editor lines
are located from the extension's visible range plus UI Automation's editor rectangle.

**Tech Stack:** TypeScript + VS Code extension API (VS Code 1.143 is installed), Node 24, `@vscode/vsce`
for packaging; Python sockets (`socketserver` on a thread); comtypes UI Automation through
`app/win/uia.py`, which plan 03 owns: import it after that stream is merged, and until then test
`locate` only through its pure parts (never copy the file).

**Spec:** `docs/superpowers/specs/2026-10-29-tutorial-to-practice-design.md` (sections 3 goal 5, 5.2, 5.3)

## Global Constraints

See `2026-10-29-00-overview.md`, "Global Constraints". Also:
- The socket listens on 127.0.0.1 only, on a random free port; the port and a random one-time token are
  written to `%LOCALAPPDATA%\projectx\vscode.json`; the extension sends the token first; anything else is
  dropped.
- The learner's work folder is `%LOCALAPPDATA%\projectx\work\<lesson id>\`; the extension never reads or
  writes outside the opened folder.
- The Meta AI lesson's program reads the key from `META_API_KEY` in the terminal's environment. The lesson
  never shows, prints or asks the learner to paste the key into a file; a check fails any file that
  contains a string looking like a key.
- The agent tester is pointed at VS Code only after it passes in Excel (plan 04 Task 6, then plan 06).

## Review Focus

1. The learner's program crashes, waits for input forever or prints a lot → the run check reads the exit
   code and the first 4 KB of output; a hung run is reported after 20 s without freezing anything
   (Task 3 `test_a_hanging_run_is_reported`).
2. The learner writes the right code a different way (`def greet(name):` with a docstring, single vs
   double quotes, an f-string vs `+`) → `ast`-based checks accept it (Task 2: three right, three wrong
   ways per check).
3. The learner has a syntax error mid-typing → checks wait quietly until the file parses; the problems
   list is not shown as "Not yet" until the learner saves (Task 2 `test_unsaved_syntax_errors_are_not_mistakes`).
4. VS Code is closed or the extension never connects → the panel says VS Code was closed / couldn't start,
   with a reopen button (Task 3 `test_no_hello_in_time_is_reported`).
5. The learner pastes their API key into the code → a check refuses it with "Not yet: keep your key out of
   the code. Use the META_API_KEY setting." (Task 2 `test_a_key_in_the_code_is_refused`).

---

## File structure

| File | Job |
|---|---|
| `extensions/vscode/package.json`, `tsconfig.json`, `src/extension.ts`, `src/protocol.ts` | the extension |
| `app/vscode/protocol.py` | message shapes, shared with `protocol.ts` (kept in step by a test) |
| `app/vscode/bridge.py` | the socket server and the connection |
| `app/vscode/snapshot.py` | `VsSnapshot` |
| `app/vscode/checks.py`, `app/vscode/ops.py` | the menus |
| `app/vscode/session.py`, `app/vscode/plugin.py` | `VsCodeSession`, `VsCodePlugin` |
| `lessons/vscode-first-program/`, `lessons/vscode-meta-ai-app/` | the two lessons |
| `probes/vscode_*.py`, `tests/vscode/` | live checks and tests |

---

### Task 1: The extension and the bridge

**Files:**
- Create: everything under `extensions/vscode/`, `app/vscode/__init__.py`, `protocol.py`, `bridge.py`
- Test: `tests/vscode/test_bridge.py`, `tests/vscode/test_protocol_in_step.py`; Probe: `probes/vscode_hello.py`

**Interfaces:**
- Messages are JSON lines. Extension → program: `hello{token, version}`, `state{files: {path: {text, saved: bool}},
  active: {path, line, column, visible_from, visible_to} | null, problems: [{path, line, severity, message}],
  run: {command, exit_code: int | null, output: str (first 4096 chars), finished: bool} | null}` (sent after
  any edit, save, cursor move, diagnostics change or terminal run event, at most every 100 ms),
  `done{id, ok, error}`. Program → extension: `do{id, op: {kind, args}}`, `ping{}`.
- Terminal runs come from `window.onDidStartTerminalShellExecution` / `onDidEndTerminalShellExecution`
  (shell integration) with `execution.read()` for output.
- `Bridge(on_state: Callable[[dict], None], on_closed: Callable[[], None])` with `start() -> int` (port),
  `send_op(op: Call) -> Future`, `connected: bool`, `stop()`.
- `test_protocol_in_step.py` reads `src/protocol.ts` and checks every message kind and field name in
  `protocol.py` appears there.

- [ ] **Step 1: Write the failing tests** (a fake extension client in Python)

```python
def test_wrong_token_is_dropped(): ...
def test_state_messages_reach_on_state(): ...
def test_ops_resolve_when_done_arrives(): ...
def test_disconnect_calls_on_closed_once(): ...
def test_protocol_names_match_the_extension(): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement the bridge and the extension**; build with `npm install` and `npx tsc -p .`
  inside `extensions/vscode`; package with `npx @vscode/vsce package` → `projectx-<version>.vsix`
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Live probe** (memory check first) — `<py> probes\vscode_hello.py`: installs the `.vsix`
  (`code --install-extension`), opens a scratch folder, prints the hello and the first state; types a line
  through the extension's `write_file` op and prints the next state. Paste it.
- [ ] **Step 6: Commit** — `git commit -m "Add the VS Code extension and its local link: the editor's files, problems and terminal runs reach the program"`

### Task 2: Snapshot, checks and operations

**Files:**
- Create: `app/vscode/snapshot.py`, `checks.py`, `ops.py`
- Test: `tests/vscode/test_checks.py`

**Interfaces:**
- `VsSnapshot(files: Mapping[str, FileState], active: Active | None, problems: tuple[Problem, ...],
  run: Run | None)` (frozen dataclasses mirroring the `state` message).
- Checks (`CHECKS`), all over saved file text unless said:
  | kind | params | right when [attempted when] |
  |---|---|---|
  | `file_exists` | path | the file exists [always] |
  | `defines_function` | path, name, params? (int) | `ast` finds `def name` with that many params [file parses] |
  | `calls` | path, name | a call to `name` (or `x.name`) anywhere [file parses] |
  | `imports` | path, module | `import module` or `from module import …` [file parses] |
  | `assigns` | path, name, value? (value) | a top-level assignment to `name` (with that literal) [file parses] |
  | `uses_text` | path, text | the text appears outside comments [file not empty] |
  | `run_ok` | path? | the last finished run of that file exited 0 [a run finished] |
  | `run_output` | contains | the last finished run printed that text (case-insensitive) [a run finished] |
  | `no_problems` | path | no error-level problems in the saved file [file saved] |
  | `no_key_in_code` | path | no string in the file looks like a key (`[A-Za-z0-9_\-]{32,}` inside quotes) [file not empty] |
  Unsaved files with syntax errors are waiting, never "Not yet".
- Ops (`OPS`): `write_file{path, text}`, `append_line{path, text}`, `open_file{path}`, `save_file{path}`,
  `run_file{path}` (in VS Code's terminal, `python <path>`), `clear_terminal{}`.

- [ ] **Step 1: Write the failing tests** — three right and three wrong ways per check, plus:
  `test_unsaved_syntax_errors_are_not_mistakes`, `test_a_key_in_the_code_is_refused`
- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Commit** — `git commit -m "Add VS Code checks that read the code's structure, so every right way of writing it passes"`

### Task 3: Session and plug-in

**Files:**
- Create: `app/vscode/session.py`, `app/vscode/plugin.py`
- Test: `tests/vscode/test_session.py`; Probe: `probes/vscode_session.py`

**Interfaces:**
- `VsCodePlugin()` implements `AppPlugin`: `app_id="vscode"`, `title="VS Code"`, `target_kinds={"editor_line",
  "explorer_item", "run_button", "terminal"}`; starter data `{"files": {path: text}, "open": path}`;
  `validate_starter` (relative paths only, ≤ 20 files).
- `VsCodeSession` implements `AppSession`: `open` writes the starter files to the work folder (with
  `resume`, keeps the files already there), starts the
  bridge, launches `code --new-window <folder> <open file>` with `PROJECTX_VSCODE` pointing at the port
  file, waits up to 30 s for `hello` (else `on_closed` with reason "VS Code didn't start"); `perform` sends
  `do` and waits for `done`; `run_file` resolves when the run finishes or after 20 s (then reports a hang);
  `reset` rewrites the starter files and clears the terminal; `locate` uses UI Automation for the editor's
  text area, explorer items, the Run button and the terminal, and the extension's visible range plus the
  editor's line height for `editor_line`; `watch` as in the core; `place` moves the VS Code window.

- [ ] **Step 1: Write the failing tests** (fake bridge, fake launcher)

```python
def test_open_writes_the_starter_and_waits_for_hello(tmp_path): ...
def test_no_hello_in_time_is_reported(tmp_path): ...
def test_a_hanging_run_is_reported(tmp_path): ...
def test_editor_line_rect_from_visible_range(): ...
```

- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Live probe** — `<py> probes\vscode_session.py`: opens a two-step scratch lesson, performs both
  replays, prints the runner's events and the located rect of line 3. Paste it.
- [ ] **Step 6: Commit** — `git commit -m "Add the VS Code plug-in: open the lesson's files, read every change, run the learner's program, point at lines"`

### Task 4: The two lessons

**Files:**
- Create: `lessons/vscode-first-program/lesson.json`, `lessons/vscode-meta-ai-app/lesson.json`
- Test: `tests/vscode/test_lessons.py`

- "Your first Python program": made by the factory from an approved short Creative Commons video if plan 04
  is merged by Sun 1 Nov; otherwise hand-written (`made_by: "hand"`) with these steps: make `hello.py`;
  print a greeting; store your name in a variable; print a greeting with it (f-string); ask for the name
  with `input`; run it. Each with three hints and one or two predicted mistakes.
- "Build your first app with Meta's AI" (hand-written; `source` points to Meta's own docs page as the
  credited source): starter `ask.py` empty and a `README.txt` saying the key is already in the terminal's
  environment. Steps: import `OpenAI` from `openai`; make a client with `base_url="https://api.meta.ai/v1"`
  and the key from `os.environ["META_API_KEY"]`; ask `muse-spark-1.3` a question with
  `client.responses.create`; print `response.output_text`; run it; keep the key out of the code. Checks:
  `imports`, `uses_text` (the base URL), `calls` (`create`), `calls` (`print`), `run_ok`, `no_key_in_code`.
  The run step's check is `run_ok` plus non-empty output, never the answer's wording.

- [ ] **Step 1: Write the failing tests** — both lessons load and `validate(lesson, VsCodePlugin()) == []`
- [ ] **Step 2: Run them to see them fail**
- [ ] **Step 3: Write the lessons**
- [ ] **Step 4: Run them to see them pass**
- [ ] **Step 5: Live proof** (needs plan 04's prover merged): `<py> -m app.factory prove lessons/vscode-meta-ai-app`
  → paste it.
- [ ] **Step 6: Commit** — `git commit -m "Add two VS Code lessons: your first Python program, and your first app with Meta's AI"`

Final report for the merge: test output, probe outputs, the `.vsix` build command, anything the
integration needs (for example how the panel docks beside VS Code).
