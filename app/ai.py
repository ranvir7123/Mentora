"""Which AI answers the Ask box, writes tips and helps point: Meta's Muse Spark by default, or Claude when
MENTORA_AI=claude is set. The lesson maker follows the same switch: with Claude it writes lessons from the
video's still frames, and only Meta's agent tests lessons, so a lesson Claude makes is proven, not tested.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from app.meta.key import NAME as META_KEY_NAME

SWITCH = "MENTORA_AI"
MAKER_TIMEOUT_S = 600.0          # a whole lesson, thought through, is a long answer
MAKER_MAX_TOKENS = 32000


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


def make_maker_client(environ: Mapping[str, str] = os.environ) -> Any:
    """A client for the lesson maker, for the chosen AI."""
    if ai_name(environ) == "claude":
        from app.claude.client import ClaudeClient
        return ClaudeClient(timeout_s=MAKER_TIMEOUT_S, max_tokens=MAKER_MAX_TOKENS, effort="medium", thinking=True)
    from app.meta.client import MetaClient
    return MetaClient()
