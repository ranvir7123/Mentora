"""The computer, as the VS Code session needs it: starting VS Code, its window, and where its parts
are on screen. The session takes any object with these methods, so tests can stand in for it."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol

from app.core.types import Rect
from app.vscode import launch, window
from app.vscode.uia import Finder


class Host(Protocol):
    def launch(self, folder: Path, open_file: Path | None, env: Mapping[str, str]) -> None: ...  # raises LaunchError
    def find_window(self, folder: Path) -> int: ...         # 0 when not found
    def is_window(self, hwnd: int) -> bool: ...
    def scale(self, hwnd: int) -> float: ...                # physical pixels per CSS pixel at zoom 0
    def place(self, hwnd: int, rect: Rect) -> None: ...
    def minimize(self, hwnd: int) -> None: ...
    def find(self, hwnd: int, kind: str, ref: str) -> Rect | None: ...   # editor, explorer_item, new_file, terminal, run_button
    def screen_setup(self) -> None: ...                     # once, on the thread that calls find


class WindowsHost:
    def __init__(self) -> None:
        self._finder = Finder()

    def launch(self, folder: Path, open_file: Path | None, env: Mapping[str, str]) -> None:
        launch.start_vscode(folder, open_file, dict(env))

    def find_window(self, folder: Path) -> int:
        return window.find_lesson_window(folder.name)

    def is_window(self, hwnd: int) -> bool:
        return window.is_window(hwnd)

    def scale(self, hwnd: int) -> float:
        return window.dpi_scale(hwnd)

    def place(self, hwnd: int, rect: Rect) -> None:
        window.place(hwnd, rect)

    def minimize(self, hwnd: int) -> None:
        window.minimize(hwnd)

    def find(self, hwnd: int, kind: str, ref: str) -> Rect | None:
        return self._finder.find(hwnd, kind, ref)

    def screen_setup(self) -> None:
        window.dpi_aware_thread()
        self._finder.init_thread()
