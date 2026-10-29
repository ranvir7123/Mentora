"""Excel's "not now" signals.

Excel refuses calls from other programs while someone is typing in a cell or a dialog is open.
That is back-pressure, not an error: the read is simply tried again a moment later. Anything
else that goes wrong is a real error and is raised.

The three codes were measured on this laptop in the earlier project:
    0x8001010A  RPC_E_SERVERCALL_RETRYLATER
    0x80010001  RPC_E_CALL_REJECTED
    0x800AC472  VBA_E_IGNORE  (a cell in edit mode, or a modal dialog open)
"""
from __future__ import annotations

RETRYABLE_HRESULTS = frozenset({-2147417846, -2147418111, -2146777998})


class ExcelBusy(RuntimeError):
    """Excel said "not now". The caller tries again later; it is never shown to the learner."""


def is_busy(exc: BaseException) -> bool:
    """True when this COM failure means "try again in a moment" rather than "this is wrong"."""
    if isinstance(exc, ExcelBusy):
        return True
    for attr in ("hresult", "args"):
        value = getattr(exc, attr, None)
        if attr == "args":
            value = value[0] if value else None
        if isinstance(value, int) and value in RETRYABLE_HRESULTS:
            return True
    return False


def next_delay(previous_s: float, *, first_s: float = 0.02, cap_s: float = 0.25) -> float:
    """The pause before the next try: doubling from 20 ms, never more than 250 ms.

    There is no last try. A read that Excel keeps refusing is retried until it succeeds or the
    session ends, so a change can never go unread; the cap keeps a learner who leaves a cell
    from waiting more than a quarter of a second for their tick.
    """
    if previous_s <= 0:
        return first_s
    return min(previous_s * 2, cap_s)
