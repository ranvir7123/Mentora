"""Which AI answers the Ask box, writes tips and helps point: Meta's Muse Spark by default, or Claude when
MENTORA_AI=claude is set. The lesson maker always uses Meta.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from app.meta.key import NAME as META_KEY_NAME

SWITCH = "MENTORA_AI"


def ai_name(environ: Mapping[str, str] = os.environ) -> str:
    """ "claude" when the switch says so, else "meta"."""
    return "claude" if environ.get(SWITCH, "").strip().lower() == "claude" else "meta"


def key_name(environ: Mapping[str, str] = os.environ) -> str:
    """The name of the key the chosen AI needs."""
    if ai_name(environ) == "claude":
        from app.claude.client import KEY_NAME
        return KEY_NAME
    return META_KEY_NAME


def make_client(*, timeout_s: float, environ: Mapping[str, str] = os.environ) -> Any:
    """A client with respond(), for the chosen AI."""
    if ai_name(environ) == "claude":
        from app.claude.client import ClaudeClient
        return ClaudeClient(timeout_s=timeout_s)
    from app.meta.client import MetaClient
    return MetaClient(timeout_s=timeout_s)
