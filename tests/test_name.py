import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Where the program, its add-on and its lessons live. The docs and the README keep the old name only where
# they tell the history (the first plans, and the helpers adapted from the old private project).
PROGRAM = ("app", "extensions/vscode", "probes", "lessons", "tools")
OLD_NAME = re.compile(r"project[\s_-]?x", re.IGNORECASE)


def _program_files() -> list[str]:
    listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", *PROGRAM],
                            cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [name for name in listed.splitlines() if (REPO / name).is_file()]


def test_the_program_is_called_mentora_everywhere():
    found = []
    for name in _program_files():
        text = (REPO / name).read_text(encoding="utf-8", errors="replace")
        found += [f"{name}:{number}" for number, line in enumerate(text.splitlines(), 1) if OLD_NAME.search(line)]
    assert found == []
