"""Starting VS Code on a lesson's folder, with the Mentora add-on installed first.

VS Code's `code.cmd` only sets two variables and runs `Code.exe cli.js <args>`. Running a .cmd file
from Python goes through cmd.exe, which mangles paths holding characters such as & or %, so the
program reads the two paths out of code.cmd and runs them itself, the same way code.cmd does.

The add-on is installed from the .vsix built in extensions/vscode (`npm run package`) when VS Code
does not have this version yet. It only wakes up in lesson folders, so the learner's own projects
never see it.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

ADDON = "mentora.mentora"
ADDON_VERSION = "0.1.0"          # extensions/vscode/package.json's version; a test keeps them in step
INSTALL_TIMEOUT_S = 120.0
NOT_INSTALLED = "VS Code isn't installed. Get it from code.visualstudio.com, then open the lesson again."

_REPO = Path(__file__).resolve().parents[2]
_INSTALL_FOLDERS = (("LOCALAPPDATA", "Programs/Microsoft VS Code"), ("ProgramFiles", "Microsoft VS Code"),
                    ("ProgramFiles(x86)", "Microsoft VS Code"))
_CLI_LINE = re.compile(r'"%~dp0([^"]+\.exe)"\s+"%~dp0([^"]+\.js)"', re.IGNORECASE)


class LaunchError(Exception):
    """VS Code could not be started; the message says why in plain words."""


def parse_code_cmd(text: str, bin_dir: Path) -> tuple[Path, Path] | None:
    """Code.exe and cli.js named in code.cmd, made absolute against the folder code.cmd is in."""
    found = _CLI_LINE.search(text)
    if found is None:
        return None
    return (Path(os.path.normpath(bin_dir / found.group(1))),
            Path(os.path.normpath(bin_dir / found.group(2))))


def find_code_cmd() -> Path | None:
    on_path = shutil.which("code.cmd")
    if on_path:
        return Path(on_path)
    for variable, folder in _INSTALL_FOLDERS:
        root = os.environ.get(variable)
        if root and (Path(root) / folder / "bin" / "code.cmd").is_file():
            return Path(root) / folder / "bin" / "code.cmd"
    return None


def cli_command() -> tuple[list[str], dict[str, str]]:
    """How to run VS Code's command line: the words to start it with, and the environment to use."""
    code_cmd = find_code_cmd()
    if code_cmd is None:
        raise LaunchError(NOT_INSTALLED)
    env = {k: v for k, v in os.environ.items() if k.upper() != "VSCODE_DEV"}
    parsed = parse_code_cmd(code_cmd.read_text(encoding="utf-8", errors="replace"), code_cmd.parent)
    if parsed is not None and parsed[0].is_file() and parsed[1].is_file():
        env["ELECTRON_RUN_AS_NODE"] = "1"
        return [str(parsed[0]), str(parsed[1])], env
    return [str(code_cmd)], env         # a code.cmd this program can't read: let cmd.exe run it


def vsix_path() -> Path:
    return _REPO / "extensions" / "vscode" / f"mentora-{ADDON_VERSION}.vsix"


def addon_installed(extensions_dir: Path | None = None) -> bool:
    folder = extensions_dir or Path(os.environ.get("USERPROFILE", "")) / ".vscode" / "extensions"
    return (folder / f"{ADDON}-{ADDON_VERSION}" / "package.json").is_file()


def _run_quietly(argv: list[str], env: dict[str, str], **kwargs) -> subprocess.CompletedProcess:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(argv, env=env, creationflags=flags, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, **kwargs)


def install_addon() -> None:
    vsix = vsix_path()
    if not vsix.is_file():
        raise LaunchError("The Mentora add-on for VS Code hasn't been built. In extensions/vscode, run "
                          "npm install, then npm run package.")
    start, env = cli_command()
    try:
        done = _run_quietly(start + ["--install-extension", str(vsix), "--force"], env, timeout=INSTALL_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LaunchError(f"VS Code could not install the Mentora add-on ({exc}).") from exc
    if done.returncode != 0 or not addon_installed():
        said = (done.stderr or done.stdout or "").strip().splitlines()
        raise LaunchError("VS Code could not install the Mentora add-on"
                          + (f" ({said[-1]})." if said else "."))


def start_vscode(folder: Path, open_file: Path | None, extra_env: dict[str, str]) -> None:
    """Open `folder` (and `open_file` in it) in a new VS Code window. Returns once VS Code was asked."""
    if not addon_installed():
        install_addon()
    start, env = cli_command()
    env.update(extra_env)
    argv = start + ["--new-window", str(folder)] + ([str(open_file)] if open_file is not None else [])
    try:
        subprocess.Popen(argv, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
    except OSError as exc:
        raise LaunchError(f"VS Code could not be started ({exc}).") from exc
