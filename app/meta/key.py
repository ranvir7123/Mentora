"""Where the program finds the Meta API key.

The key is never written in code or committed. It is read from the program's own
environment first; if it is missing there, from the user's saved Windows settings
(HKEY_CURRENT_USER\\Environment), which is where
[Environment]::SetEnvironmentVariable("META_API_KEY", "...", "User") puts it.
That second place means a program started before the key was saved (the Claude app,
an open terminal) still finds it without a restart.
"""
from __future__ import annotations

import os
import sys

NAME = "META_API_KEY"


def _from_user_settings(name: str) -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            value, _kind = winreg.QueryValueEx(k, name)
    except OSError:
        return None
    return value if isinstance(value, str) else None


def find_key(name: str = NAME) -> tuple[str | None, str]:
    """Return (key, where it came from). The key is None when it is nowhere."""
    value = os.environ.get(name, "").strip()
    if value:
        return value, "environment"
    value = (_from_user_settings(name) or "").strip()
    if value:
        return value, "saved user settings"
    return None, "missing"


def require_key(name: str = NAME) -> str:
    key, _where = find_key(name)
    if key is None:
        raise RuntimeError(
            f"{name} is not set. Save it in PowerShell with "
            f'[Environment]::SetEnvironmentVariable("{name}", "<your key>", "User")'
        )
    return key
