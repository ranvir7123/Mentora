"""Claude behind the same respond() the coach and the pointing fallback already call on MetaClient.

The request they build is in Meta's format (system and user messages, "input_text" and "input_image"
parts, a JSON schema); it is turned into one Claude Messages call, and the reply comes back as the same
Answer, with Claude's errors turned into the same MetaError kinds, so neither caller changes. The Meta
model name they pass is ignored: every call goes to CLAUDE_MODEL.

Claude takes still pictures, not a video file, so upload() is refused with MetaRefused: the lesson writer
then sends the video's still frames, as it does when Meta refuses a video. There is no transcribe(): a
video without captions is written from its frames alone.

Claude's JSON mode takes only objects whose fields are all named and few of them optional, so an object
of any shape (a lesson's starter workbook) or with optional fields (a check's arguments) is asked for as
JSON text and turned back into an object when the answer comes. Limits the mode does not take (list
lengths, number ranges) go to Claude as words instead; the callers check the answer themselves.

Every call is appended to its own call log (model, label, tokens, cost, time, ok), and at the limit the
next call is refused with SpendLimitReached. The key is read with app.meta.key.find_key, so a key saved
in the user's Windows settings counts without a restart; it is never printed, logged or saved.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import anthropic

from app.meta.client import Answer, MetaError, MetaRefused, MetaUnavailable, NoKey, SpendLimitReached
from app.meta.key import find_key as _find_key
from app.meta.prices import PER_MILLION, Usage

CLAUDE_MODEL = "claude-opus-5-5"
KEY_NAME = "ANTHROPIC_API_KEY"
NAME = "Claude"                  # how the coach's lines name this AI
EFFORT = "low"                   # the Ask box, tips and pointing are short jobs a learner waits on
MAX_TOKENS = 4000
RETRIES = 1
PRICE_INPUT, PRICE_CACHED, PRICE_OUTPUT = 4.00, 0.20, 20.00     # dollars per 1M tokens (Opus 5.5)
_DROP = {"title", "minLength", "maxLength", "multipleOf"}        # schema words Claude's JSON mode does not take
_AS_WORDS = {"minItems": "At least {} items.", "maxItems": "At most {} items.",     # ...said in words instead
             "minimum": "At least {}.", "maximum": "At most {}."}
OPEN_AS_TEXT = "A JSON object, written as text."


def default_log_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "mentora" / "claude_calls.jsonl"


class ClaudeClient:
    name = NAME

    def __init__(self, *, api: Any | None = None, timeout_s: float = 30.0, log_path: Path | None = None,
                 limit_usd: float = 20.0, max_tokens: int = MAX_TOKENS, effort: str = EFFORT, thinking: bool = False,
                 find_key: Callable[[str], tuple[str | None, str]] = _find_key):
        self._api = api
        self.timeout_s, self.max_tokens, self.effort, self.thinking = timeout_s, max_tokens, effort, thinking
        self.log_path = Path(log_path) if log_path is not None else default_log_path()
        self.limit_usd = limit_usd
        self._find_key = find_key
        self._lock = threading.Lock()

    def respond(self, model: str, input: list | str, *, label: str, schema: dict | None = None,
                **_extra: Any) -> Answer:
        """One Claude call for a Meta-style request; `model` names the Meta model the caller wanted."""
        if self.spent() >= self.limit_usd:
            raise SpendLimitReached(f"Claude spending reached the ${self.limit_usd:.0f} limit")
        system, messages = _messages(input)
        output_config: dict[str, Any] = {"effort": self.effort}
        as_text: list[tuple[str, ...]] = []
        if schema is not None:
            strict, as_text = _strict_schema(schema)
            output_config["format"] = {"type": "json_schema", "schema": strict}
        request: dict[str, Any] = {"model": CLAUDE_MODEL, "max_tokens": self.max_tokens, "messages": messages,
                                   "output_config": output_config}
        if self.thinking:
            request["thinking"] = {"type": "adaptive"}
        if system:
            request["system"] = system
        started = time.monotonic()
        try:
            reply = self._client().messages.create(**request)
        except MetaError as error:
            self._log(label, Usage(), 0.0, started, ok=False, error=str(error))
            raise
        except Exception as exc:
            error = _classify(exc)
            self._log(label, Usage(), 0.0, started, ok=False, error=str(error))
            raise error from None
        usage = _usage(reply)
        cost = _cost(reply)
        self._log(label, usage, cost, started, ok=True)
        text = "".join(block.text for block in reply.content if getattr(block, "type", "") == "text").strip()
        refusal = ""
        if reply.stop_reason == "refusal":
            details = getattr(reply, "stop_details", None)
            refusal = (getattr(details, "explanation", None) or "Claude declined this request.")
        data = None
        if schema is not None and text and not refusal:
            try:
                data = json.loads(text)
            except ValueError:
                data = None
            for path in as_text:
                data = _from_text(data, path)
        return Answer(text=text, data=data, output=list(reply.content), usage=usage,
                      response_id=str(getattr(reply, "id", "")), cost=cost, refusal=refusal)

    def upload(self, path: Path, *, label: str) -> str:
        """Refused: Claude takes still pictures, not a video file."""
        raise MetaRefused(400, "Claude takes still pictures, not a video file")

    def spent(self) -> float:
        """Dollars spent so far, from the call log, across every run of the program."""
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0.0
        total = 0.0
        for line in lines:
            try:
                total += float(json.loads(line).get("cost", 0.0))
            except (ValueError, AttributeError, TypeError):
                continue
        return total

    def _client(self) -> Any:
        if self._api is None:
            key, _where = self._find_key(KEY_NAME)
            if not key:
                raise NoKey(f"{KEY_NAME} is not set")
            self._api = anthropic.Anthropic(api_key=key, timeout=self.timeout_s, max_retries=RETRIES)
        return self._api

    def _log(self, label: str, usage: Usage, cost: float, started: float, *, ok: bool, error: str = "") -> None:
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": CLAUDE_MODEL,
                 "label": label, "input_tokens": usage.input_tokens, "cached_tokens": usage.cached_tokens,
                 "output_tokens": usage.output_tokens, "cost": round(cost, 6),
                 "seconds": round(time.monotonic() - started, 2), "ok": ok}
        if error:
            entry["error"] = error
        with self._lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")


def _messages(input: list | str) -> tuple[str, list[dict]]:
    """Meta's input as (Claude's system text, Claude's messages)."""
    if isinstance(input, str):
        return "", [{"role": "user", "content": input}]
    system, messages = [], []
    for item in input:
        role, content = item.get("role"), item.get("content")
        if role == "system":
            system.append(content if isinstance(content, str) else " ".join(
                part.get("text", "") for part in content))
        else:
            messages.append({"role": "assistant" if role == "assistant" else "user", "content": _content(content)})
    return "\n\n".join(system), messages


def _content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    blocks = []
    for part in content:
        kind = part.get("type")
        if kind in ("input_text", "text", "output_text"):
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif kind == "input_image":
            head, _, data = str(part.get("image_url", "")).partition(",")
            media = head.removeprefix("data:").split(";")[0] or "image/png"
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": data}})
    return blocks


def _strict_schema(schema: Any) -> tuple[Any, list[tuple[str, ...]]]:
    """The schema as Claude's JSON mode takes it, and where each object went as JSON text (a path of field
    names, "[]" for a list's items): one of any shape, or one with optional fields, named in its
    description. Limits the mode refuses become words; every other object says it has no other fields."""
    as_text: list[tuple[str, ...]] = []

    def strict(node: Any, path: tuple[str, ...]) -> Any:
        if isinstance(node, list):
            return [strict(v, path) for v in node]
        if not isinstance(node, dict):
            return node
        fields = node.get("properties") or {}
        if node.get("type") == "object" and (not fields or set(fields) - set(node.get("required", []))):
            as_text.append(path)
            named = f" Its fields: {', '.join(fields)}; leave out the ones that do not apply." if fields else ""
            return {"type": "string", "description": OPEN_AS_TEXT + named}
        out: dict[str, Any] = {}
        words = []
        for key, value in node.items():
            if key == "properties":
                out[key] = {name: strict(sub, path + (name,)) for name, sub in value.items()}
            elif key == "items":
                out[key] = strict(value, path + ("[]",))
            elif key == "minItems" and value in (0, 1):
                out[key] = value
            elif key in _AS_WORDS:
                words.append(_AS_WORDS[key].format(value))
            elif key not in _DROP:
                out[key] = strict(value, path)
        if words:
            out["description"] = " ".join(filter(None, [out.get("description"), *words]))
        if "properties" in out:
            out["additionalProperties"] = False
        return out

    return strict(schema, ()), as_text


def _from_text(data: Any, path: tuple[str, ...]) -> Any:
    """`data` with the JSON text at `path` read back into an object; text that is not JSON stays text."""
    if not path:
        if isinstance(data, str):
            try:
                return json.loads(data)
            except ValueError:
                return data
        return data
    head, rest = path[0], path[1:]
    if head == "[]":
        return [_from_text(v, rest) for v in data] if isinstance(data, list) else data
    if isinstance(data, dict) and head in data:
        data[head] = _from_text(data[head], rest)
    return data


def _usage(reply: Any) -> Usage:
    u = reply.usage
    cached = int(getattr(u, "cache_read_input_tokens", 0) or 0)
    written = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    return Usage(input_tokens=int(u.input_tokens or 0) + cached + written, cached_tokens=cached,
                 output_tokens=int(u.output_tokens or 0))


def _cost(reply: Any) -> float:
    usage = _usage(reply)
    fresh = usage.input_tokens - usage.cached_tokens
    return (fresh * PRICE_INPUT + usage.cached_tokens * PRICE_CACHED
            + usage.output_tokens * PRICE_OUTPUT) / PER_MILLION


def _classify(exc: Exception) -> MetaError:
    """Claude's error as the MetaError kind the callers already handle; plain words, never the key."""
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return NoKey("Claude did not accept the key")
    if isinstance(exc, anthropic.APIConnectionError):            # timeouts are connection errors too
        return MetaUnavailable("Claude could not be reached")
    if isinstance(exc, anthropic.RateLimitError):
        return MetaUnavailable("Claude is busy (429)")
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code >= 500:
            return MetaUnavailable(f"Claude is busy ({exc.status_code})")
        said = _said(exc)
        return MetaRefused(exc.status_code, f"Claude refused the request: {said}" if said else
                           "Claude refused the request")
    return MetaUnavailable(f"Claude call failed: {type(exc).__name__}")


def _said(exc: Exception) -> str:
    """Claude's own words for an error, for the log: what was wrong with the request, never the key."""
    body = getattr(exc, "body", None)
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    return " ".join(str(message).split())[:300] if message else ""
