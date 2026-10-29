"""The plain-code parts of reaching the real VS Code: choosing its parts from UI Automation's list,
knowing the lesson's window by its title, and reading how code.cmd starts VS Code."""
from __future__ import annotations

import json
from pathlib import Path

from app.core.types import Rect
from app.vscode.launch import ADDON_VERSION, addon_installed, parse_code_cmd
from app.vscode.uia import Element, pick
from app.vscode.window import is_lesson_title

REPO = Path(__file__).resolve().parents[2]

EXPLORER = Element("tree", "Files Explorer", "monaco-list", Rect(0, 100, 300, 800))
ELEMENTS = [
    EXPLORER,
    Element("tree_item", "notes", "monaco-list-row", Rect(0, 100, 300, 44)),
    Element("tree_item", "hello.py", "monaco-list-row", Rect(0, 144, 300, 44)),
    Element("tree_item", "hello.py", "monaco-list-row", Rect(0, 1400, 300, 44)),          # outside the tree
    Element("tree_item", "ask.py", "monaco-list-row", Rect(400, 200, 300, 44)),           # another tree
    Element("group", "", "monaco-editor no-user-select vs-dark focused", Rect(320, 160, 1200, 700)),
    Element("group", "", "monaco-editor vs-dark", Rect(20, 60, 260, 30)),                 # the search box
    Element("group", "", "terminal xterm", Rect(320, 900, 1200, 300)),
    Element("button", "Run Python File (Ctrl+F5)", "action-label", Rect(1480, 120, 32, 32)),
    Element("group", "", "monaco-editor", Rect(320, 160, 0, 0)),                          # hidden: no size
]


def test_the_editor_is_the_biggest_monaco_editor():
    assert pick(ELEMENTS, "editor", "hello.py") == Rect(320, 160, 1200, 700)


def test_an_explorer_row_is_found_by_its_name_inside_the_files_explorer():
    assert pick(ELEMENTS, "explorer_item", "hello.py") == Rect(0, 144, 300, 44)
    assert pick(ELEMENTS, "explorer_item", "HELLO.PY") == Rect(0, 144, 300, 44)
    assert pick(ELEMENTS, "explorer_item", "ask.py") is None


def test_a_file_in_a_shut_folder_points_at_the_folder():
    assert pick(ELEMENTS, "explorer_item", "notes/readme.txt") == Rect(0, 100, 300, 44)
    assert pick(ELEMENTS, "explorer_item", "other/readme.txt") is None


def test_the_terminal_and_the_run_button():
    assert pick(ELEMENTS, "terminal", "") == Rect(320, 900, 1200, 300)
    assert pick(ELEMENTS, "run_button", "") == Rect(1480, 120, 32, 32)
    assert pick([e for e in ELEMENTS if e.control != "button"], "run_button", "") is None


def test_hidden_parts_with_no_size_are_skipped():
    hidden_row = Element("tree_item", "hello.py", "monaco-list-row", Rect(0, 120, 0, 0))
    assert pick([EXPLORER, hidden_row, *ELEMENTS[1:]], "explorer_item", "hello.py") == Rect(0, 144, 300, 44)
    assert pick([Element("group", "", "monaco-editor", Rect(320, 160, 0, 0))], "editor", "hello.py") is None


def test_nothing_is_found_in_an_empty_list():
    for kind in ("editor", "explorer_item", "terminal", "run_button", "cell"):
        assert pick([], kind, "hello.py") is None


def test_the_lesson_window_is_known_by_its_folder_in_the_title():
    assert is_lesson_title("hello.py - vscode-first-program - Visual Studio Code", "vscode-first-program")
    assert is_lesson_title("● hello.py - Work - Visual Studio Code", "work")
    assert is_lesson_title("work - Visual Studio Code", "work")
    assert not is_lesson_title("hello.py - my-project - Visual Studio Code", "work")
    assert not is_lesson_title("work - Notepad", "work")
    assert not is_lesson_title("homework - Visual Studio Code", "work")
    assert not is_lesson_title("work - Visual Studio Code", "")


CODE_CMD = """@echo off
setlocal
set VSCODE_DEV=
set ELECTRON_RUN_AS_NODE=1
"%~dp0..\\Code.exe" "%~dp0..\\e646868227\\resources\\app\\out\\cli.js" %*
IF %ERRORLEVEL% NEQ 0 EXIT /b %ERRORLEVEL%
endlocal
"""


def test_code_cmd_names_code_exe_and_its_command_line_script():
    bin_dir = Path(r"C:\Users\x\AppData\Local\Programs\Microsoft VS Code\bin")
    exe, cli = parse_code_cmd(CODE_CMD, bin_dir)
    assert exe == Path(r"C:\Users\x\AppData\Local\Programs\Microsoft VS Code\Code.exe")
    assert cli == Path(r"C:\Users\x\AppData\Local\Programs\Microsoft VS Code\e646868227\resources\app\out\cli.js")
    assert parse_code_cmd("@echo off\ncode.exe %*\n", bin_dir) is None


def test_the_add_on_version_matches_the_extension_package():
    package = json.loads((REPO / "extensions" / "vscode" / "package.json").read_text(encoding="utf-8"))
    assert f"{package['publisher']}.{package['name']}" == "projectx.projectx"
    assert package["version"] == ADDON_VERSION


def test_the_add_on_counts_as_installed_only_at_this_version(tmp_path):
    assert not addon_installed(tmp_path)
    (tmp_path / "projectx.projectx-lesson-helper-0.1.1").mkdir()
    (tmp_path / "projectx.projectx-lesson-helper-0.1.1" / "package.json").write_text("{}", encoding="utf-8")
    assert not addon_installed(tmp_path)
    (tmp_path / f"projectx.projectx-{ADDON_VERSION}").mkdir()
    (tmp_path / f"projectx.projectx-{ADDON_VERSION}" / "package.json").write_text("{}", encoding="utf-8")
    assert addon_installed(tmp_path)
