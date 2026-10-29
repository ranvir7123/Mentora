"""What each Meta model costs, so every call's price can be logged and the spending stop can count.

Prices are Meta's Standard prices in US dollars (checked on dev.meta.ai/docs/pricing-rate-limits on
29 Oct 2026). A model with no row here cannot be called: an unpriced call would slip past the stop.
"""
from __future__ import annotations

from dataclasses import dataclass

PER_MILLION = 1_000_000


@dataclass(frozen=True)
class Price:
    input: float = 0.0           # dollars per 1M input tokens not served from the cache
    cached: float = 0.0          # dollars per 1M cached input tokens
    output: float = 0.0          # dollars per 1M output tokens (reasoning tokens included)
    audio_hour: float = 0.0      # dollars per hour of audio


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0        # all input tokens, cached ones included
    cached_tokens: int = 0
    output_tokens: int = 0
    audio_seconds: int = 0


_SPARK = Price(input=1.25, cached=0.15, output=4.25)

PRICES: dict[str, Price] = {
    "muse-spark-1.3": _SPARK,
    "muse-spark-1.2": _SPARK,
    "muse-spark-1.1": _SPARK,
    "muse-wonder-1.0": Price(input=4.00, cached=0.20, output=20.00),
    "muse-voice-transcribe-1.0": Price(audio_hour=0.18),
}


def price_of(model: str) -> Price:
    price = PRICES.get(model)
    if price is None:
        raise ValueError(f"there is no price for {model}; add it to app/meta/prices.py before calling it")
    return price


def cost_of(model: str, usage: Usage) -> float:
    p = price_of(model)
    fresh = max(usage.input_tokens - usage.cached_tokens, 0)
    return (fresh * p.input + usage.cached_tokens * p.cached + usage.output_tokens * p.output) / PER_MILLION \
        + usage.audio_seconds * p.audio_hour / 3600
