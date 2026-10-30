"""The one place every call to Meta's models goes through.

Three modes:
- live: calls Meta at https://api.meta.ai/v1 with the key from `app.meta.key.require_key()`;
- replay: reads saved answers from `saved_dir/<label>.json` and never touches the network (tests);
- record: calls live and saves each answer (or refusal) so a test can replay it later.

Every live call is appended to the call log (model, label, tokens, cost, time, ok). Before each call
the log's total is counted, across every run of the program: at the limit the call is refused with
`SpendLimitReached`, and the session tells Ranvir. The key only travels in the request header: it is
never printed, logged or saved, and any error text that echoes it is scrubbed first.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import threading
import time
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import httpx2
import openai

from app.meta.key import require_key
from app.meta.prices import Usage, cost_of, price_of

BASE_URL = "https://api.meta.ai/v1"
TRANSCRIBE_MODEL = "muse-voice-transcribe-1.0"
TRIES = 3
BACKOFF_S = 1.0
JITTER_S = 0.5
MAX_WAIT_S = 30.0
AUDIO_PART_S = 540               # Meta refuses audio over 10 minutes, so longer audio goes in 9-minute parts

Mode = Literal["live", "replay", "record"]


class MetaError(Exception):
    """Something stopped a call to Meta; the message is plain words, safe to show."""


class NoKey(MetaError):
    """There is no key, or Meta did not accept it."""


class SpendLimitReached(MetaError):
    """The call log has reached the spending limit; no more calls until Ranvir says so."""


class MetaUnavailable(MetaError):
    """Meta could not be reached or was busy, three tries in a row."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class MetaRefused(MetaError):
    """Meta answered and refused the request (a 4xx other than a rate limit)."""

    def __init__(self, status: int, reason: str):
        super().__init__(f"Meta refused the request ({status}): {reason}")
        self.status = status
        self.reason = reason


@dataclass(frozen=True)
class Answer:
    text: str                    # the answer's text, joined
    data: Any | None             # the parsed JSON when a schema was given and the text parses
    output: list                 # the raw output items (computer calls live here)
    usage: Usage
    response_id: str
    cost: float
    refusal: str = ""            # the model's refusal, when it refused


@dataclass(frozen=True)
class Transcript:
    text: str
    segments: list[tuple[float, float, str]]     # (start s, end s, words)


def default_log_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "mentora" / "meta_calls.jsonl"


class MetaClient:
    def __init__(self, *, mode: Mode = "live", saved_dir: Path = Path("tests/data/meta"),
                 log_path: Path | None = None, limit_usd: float = 100.0,
                 http_client: httpx2.Client | None = None, sleep: Callable[[float], None] = time.sleep,
                 timeout_s: float = 600.0):
        if mode not in ("live", "replay", "record"):
            raise ValueError(f"mode should be live, replay or record, not {mode!r}")
        self.mode = mode
        self.saved_dir = Path(saved_dir)
        self.log_path = Path(log_path) if log_path is not None else default_log_path()
        self.limit_usd = limit_usd
        self._http = http_client
        self._sleep = sleep
        self._timeout_s = timeout_s
        self._lock = threading.Lock()
        self._api_client: openai.OpenAI | None = None
        self._api_key_hash = ""
        self._log_read = 0       # bytes of the log already counted
        self._spent = 0.0

    # What the rest of the program calls.

    def respond(self, model: str, input: list | str, *, label: str, schema: dict | None = None,
                tools: list | None = None, previous_response_id: str | None = None, **extra: Any) -> Answer:
        """One Responses API call. `schema` asks for JSON matching it; `extra` goes into the request body."""
        _check_model(model)
        body: dict[str, Any] = {"model": model, "input": input}
        if schema is not None:
            body["text"] = {"format": {"type": "json_schema", "name": _schema_name(label), "schema": schema,
                                       "strict": False}}
        if tools:
            body["tools"] = tools
        if previous_response_id:
            body["previous_response_id"] = previous_response_id
        body.update(extra)
        summary = {"label": label, "kind": "respond", "model": model,
                   "schema": None if schema is None else schema.get("title", "schema"),
                   "tools": [t.get("type") for t in tools or []], "previous_response_id": previous_response_id,
                   "input_items": len(input) if isinstance(input, list) else 1}
        raw = self._run(model, label, summary, lambda api: api.post("/responses", cast_to=httpx2.Response,
                                                                       body=body), _usage)
        return _answer(model, raw, parse=schema is not None)

    def upload(self, path: Path, *, label: str) -> str:
        """Send a file to Meta's Files API (for `input_file` blocks); returns its file id."""
        path = Path(path)

        def send(api: openai.OpenAI) -> httpx2.Response:
            return api.post("/files", cast_to=httpx2.Response, body={"purpose": "user_data"},
                            files=[("file", (path.name, path.read_bytes(), _mime(path)))],
                            options={"headers": {"Content-Type": "multipart/form-data"}})

        summary = {"label": label, "kind": "upload", "file": path.name}
        return self._run(None, label, summary, send, lambda raw: Usage())["id"]

    def transcribe(self, audio: Path, *, label: str) -> Transcript:
        """Muse Voice Transcribe on a mono 16-bit WAV (16 or 24 kHz); long audio goes in parts."""
        parts = _wav_parts(Path(audio), AUDIO_PART_S)
        texts: list[str] = []
        segments: list[tuple[float, float, str]] = []
        for i, (offset, data, seconds) in enumerate(parts):
            part_label = label if len(parts) == 1 else f"{label}_{i + 1}"
            settings = json.dumps({"model": TRANSCRIBE_MODEL, "audioEncoding": "WAV", "mode": "ENDPOINTING"})

            def send(api: openai.OpenAI, data: bytes = data, settings: str = settings) -> httpx2.Response:
                return api.post("/asr/transcribe", cast_to=httpx2.Response, body={},
                                files=[("request", ("request.json", settings.encode(), "application/json")),
                                       ("audio", ("audio.wav", data, "audio/wav"))],
                                options={"headers": {"Content-Type": "multipart/form-data"}})

            summary = {"label": part_label, "kind": "transcribe", "model": TRANSCRIBE_MODEL,
                       "offset_s": offset, "seconds": seconds}
            raw = self._run(TRANSCRIBE_MODEL, part_label, summary, send,
                            lambda raw, seconds=seconds: Usage(audio_seconds=_audio_seconds(raw, seconds)))
            text = str(raw.get("transcript") or "").strip()
            if text:
                texts.append(text)
            duration = raw["audioDurationMs"] / 1000 if raw.get("audioDurationMs") else seconds
            turns = raw.get("turns") or []
            for turn in turns:
                words = str(turn.get("transcript") or "").strip()
                if words:
                    segments.append((round(offset + turn["startMs"] / 1000, 3),
                                     round(offset + turn["endMs"] / 1000, 3), words))
            if not turns and text:
                segments.append((round(offset, 3), round(offset + duration, 3), text))
        return Transcript(" ".join(texts), segments)

    def spent(self) -> float:
        """Dollars spent so far, counted from the call log (every run of the program, not only this one)."""
        with self._lock:
            return self._count_log()

    # The machinery.

    def _run(self, model: str | None, label: str, summary: dict,
             send: Callable[[openai.OpenAI], httpx2.Response], usage_of: Callable[[dict], Usage]) -> dict:
        if self.mode == "replay":
            return self._replayed(label)
        raw = self._live(model, label, summary, send, usage_of)
        if self.mode == "record":
            self._save(label, {"request": summary, "response": raw})
        return raw

    def _live(self, model: str | None, label: str, summary: dict,
              send: Callable[[openai.OpenAI], httpx2.Response], usage_of: Callable[[dict], Usage]) -> dict:
        spent = self.spent()
        if spent >= self.limit_usd:
            raise SpendLimitReached(f"Meta spending has reached ${spent:.2f} of the ${self.limit_usd:.2f} limit. "
                                    "Tell Ranvir before spending more.")
        api, key = self._api()
        started = time.monotonic()
        for attempt in range(TRIES):
            try:
                raw = send(api).json()
                if not isinstance(raw, dict):
                    raise ValueError("not an object")
                break
            except (openai.APIError, ValueError) as exc:
                error, retry, wait = _classify(exc, key)
                if retry and attempt < TRIES - 1:
                    self._sleep(wait if wait is not None else BACKOFF_S * 2 ** attempt + random.uniform(0, JITTER_S))
                    continue
                self._log(model, label, summary["kind"], Usage(), 0.0, started, ok=False, error=str(error))
                if self.mode == "record" and not isinstance(error, NoKey):
                    self._save(label, {"request": summary, "error": _error_dict(error)})
                raise error from None
        usage = usage_of(raw)
        cost = 0.0 if model is None else cost_of(model, usage)
        self._log(model, label, summary["kind"], usage, cost, started, ok=True)
        return raw

    def _api(self) -> tuple[openai.OpenAI, str]:
        try:
            key = require_key()
        except RuntimeError as exc:
            raise NoKey(str(exc)) from None
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        with self._lock:
            if self._api_client is None or self._api_key_hash != key_hash:
                self._api_client = openai.OpenAI(api_key=key, base_url=BASE_URL, max_retries=0,
                                                 timeout=self._timeout_s, http_client=self._http)
                self._api_key_hash = key_hash
            return self._api_client, key

    def _replayed(self, label: str) -> dict:
        path = self.saved_dir / f"{label}.json"
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise LookupError(f"no saved answer for {label}: {path} is missing") from None
        if "error" in saved:
            raise _error_from_dict(saved["error"])
        return saved["response"]

    def _save(self, label: str, record: dict) -> None:
        self.saved_dir.mkdir(parents=True, exist_ok=True)
        path = self.saved_dir / f"{label}.json"
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temp, path)

    def _log(self, model: str | None, label: str, kind: str, usage: Usage, cost: float, started: float, *,
             ok: bool, error: str = "") -> None:
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model, "label": label,
                 "kind": kind, "input_tokens": usage.input_tokens, "cached_tokens": usage.cached_tokens,
                 "output_tokens": usage.output_tokens, "audio_seconds": usage.audio_seconds,
                 "cost": round(cost, 6), "seconds": round(time.monotonic() - started, 2), "ok": ok}
        if error:
            entry["error"] = error[:300]
        with self._lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def _count_log(self) -> float:
        """Add the cost of log lines written since the last count (by this run or any other)."""
        try:
            size = self.log_path.stat().st_size
        except FileNotFoundError:
            return self._spent
        if size < self._log_read:            # the log was replaced: count it again from the start
            self._log_read, self._spent = 0, 0.0
        with open(self.log_path, "rb") as f:
            f.seek(self._log_read)
            chunk = f.read()
        whole = chunk.rfind(b"\n") + 1       # a line still being written is counted next time
        for line in chunk[:whole].splitlines():
            try:
                self._spent += float(json.loads(line).get("cost") or 0)
            except (ValueError, AttributeError, TypeError):
                continue                     # a damaged line is skipped
        self._log_read += whole
        return self._spent


# Helpers.

def _check_model(model: str) -> None:
    if model.endswith("-contributor"):
        raise ValueError(f"{model} is a -contributor model, which lets Meta train on what we send; "
                         "use the standard model")
    price_of(model)


def _schema_name(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", label)[:64] or "answer"


def _usage(raw: dict) -> Usage:
    u = raw.get("usage") or {}
    return Usage(input_tokens=int(u.get("input_tokens") or 0),
                 cached_tokens=int((u.get("input_tokens_details") or {}).get("cached_tokens") or 0),
                 output_tokens=int(u.get("output_tokens") or 0))


def _answer(model: str, raw: dict, *, parse: bool) -> Answer:
    texts, refusals = [], []
    for item in raw.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                texts.append(part.get("text") or "")
            elif part.get("type") == "refusal":
                refusals.append(part.get("refusal") or "")
    text = "".join(texts) or str(raw.get("output_text") or "")
    data = None
    if parse and text:
        try:
            data = json.loads(text)
        except ValueError:
            data = None
    usage = _usage(raw)
    return Answer(text=text, data=data, output=list(raw.get("output") or []), usage=usage,
                  response_id=str(raw.get("id") or ""), cost=cost_of(model, usage), refusal=" ".join(refusals))


def _audio_seconds(raw: dict, seconds: float) -> int:
    """Meta bills audio in whole seconds, rounded down."""
    ms = raw.get("audioDurationMs")
    return int(ms // 1000) if isinstance(ms, (int, float)) else int(seconds)


def _mime(path: Path) -> str:
    return {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".wav": "audio/wav", ".mp3": "audio/mpeg"}.get(path.suffix.lower(), "application/octet-stream")


def _wav_parts(path: Path, part_s: int) -> list[tuple[float, bytes, float]]:
    """(offset s, WAV bytes, length s) for each part of at most `part_s` seconds."""
    with wave.open(str(path), "rb") as w:
        channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        if channels != 1 or width != 2 or rate not in (16000, 24000):
            raise ValueError(f"{path.name} should be mono 16-bit WAV at 16 or 24 kHz "
                             f"(it is {channels} channels, {8 * width}-bit, {rate} Hz)")
        total, per_part = w.getnframes(), part_s * rate
        parts = []
        for start in range(0, max(total, 1), per_part):
            frames = w.readframes(per_part)
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(rate)
                out.writeframes(frames)
            parts.append((start / rate, buffer.getvalue(), len(frames) / 2 / rate))
        return parts


def _scrub(text: str, key: str) -> str:
    """Hide the key, and any long piece of it, from text that may be logged or shown."""
    if key:
        text = text.replace(key, "[key hidden]")
        text = re.sub(r"[A-Za-z0-9_\-]{8,}", lambda m: "[key hidden]" if m.group(0) in key else m.group(0), text)
    return text


def _message(exc: openai.APIStatusError) -> str:
    body = exc.body
    if isinstance(body, dict):
        inner = body.get("error") if isinstance(body.get("error"), dict) else body
        if inner.get("message"):
            return str(inner["message"])
    return exc.message


def _retry_after(response: httpx2.Response | None) -> float | None:
    if response is None:
        return None
    try:
        return min(float(response.headers.get("retry-after", "")), MAX_WAIT_S)
    except ValueError:
        return None


def _classify(exc: Exception, key: str) -> tuple[MetaError, bool, float | None]:
    """(the error to raise, whether to try again, how long Meta asked us to wait)."""
    if isinstance(exc, openai.APIStatusError):
        status, text = exc.status_code, _scrub(_message(exc), key)[:300]
        if status == 401:
            return NoKey("Meta did not accept the key in META_API_KEY. Make a new key and save it again."), False, None
        if status == 429 or status >= 500:
            return MetaUnavailable(f"Meta is busy right now ({status}: {text})"), True, _retry_after(exc.response)
        return MetaRefused(status, text), False, None
    if isinstance(exc, openai.APITimeoutError):
        return MetaUnavailable("Meta took too long to answer"), True, None
    if isinstance(exc, openai.APIConnectionError):
        return MetaUnavailable("Meta could not be reached; check the internet connection"), True, None
    if isinstance(exc, ValueError):
        return MetaUnavailable("Meta sent an answer that could not be read"), True, None
    return MetaUnavailable(f"Meta call failed: {_scrub(str(exc), key)[:200]}"), False, None


def _error_dict(error: MetaError) -> dict:
    if isinstance(error, MetaRefused):
        return {"type": "refused", "status": error.status, "message": error.reason}
    if isinstance(error, MetaUnavailable):
        return {"type": "unavailable", "message": error.reason}
    return {"type": "no_key", "message": str(error)}


def _error_from_dict(d: dict) -> MetaError:
    if d.get("type") == "refused":
        return MetaRefused(int(d.get("status") or 400), str(d.get("message") or ""))
    if d.get("type") == "no_key":
        return NoKey(str(d.get("message") or "no key"))
    return MetaUnavailable(str(d.get("message") or "Meta could not be reached"))
