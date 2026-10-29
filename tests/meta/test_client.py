import json
import wave

import httpx2
import pytest

from app.meta import client as meta_client
from app.meta.client import (Answer, MetaClient, MetaRefused, MetaUnavailable, NoKey, SpendLimitReached,
                             Transcript)
from app.meta.prices import Usage, cost_of

# Built at run time so this file never holds anything shaped like a key.
FAKE_KEY = "test-" + "k3y" * 8


def _answer_json(text="hello", input_tokens=1000, output_tokens=500, cached=0):
    return {"id": "resp_1", "object": "response", "status": "completed", "model": "muse-spark-1.3",
            "output": [{"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": text, "annotations": []}]}],
            "usage": {"input_tokens": input_tokens, "input_tokens_details": {"cached_tokens": cached},
                      "output_tokens": output_tokens, "output_tokens_details": {"reasoning_tokens": 0},
                      "total_tokens": input_tokens + output_tokens}}


class FakeMeta:
    """Stands in for Meta's servers: each request gets the next scripted reply."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx2.Response):
            return reply
        return httpx2.Response(200, json=reply)

    def http(self) -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(self))


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("META_API_KEY", FAKE_KEY)
    return FAKE_KEY


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.setattr("app.meta.key._from_user_settings", lambda name: None)


def _live(tmp_path, fake, **kw):
    sleeps = []
    c = MetaClient(mode=kw.pop("mode", "live"), saved_dir=tmp_path / "saved", log_path=tmp_path / "calls.jsonl",
                   http_client=fake.http(), sleep=sleeps.append, **kw)
    return c, sleeps


def _log(tmp_path):
    return [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()]


def test_replay_returns_the_saved_answer_without_network(tmp_path, no_key):
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "hello.json").write_text(json.dumps({"request": {"label": "hello"}, "response": _answer_json("hi there")}))
    fake = FakeMeta(AssertionError("the network was touched"))
    c = MetaClient(mode="replay", saved_dir=saved, log_path=tmp_path / "calls.jsonl", http_client=fake.http())

    answer = c.respond("muse-spark-1.3", [{"role": "user", "content": "hi"}], label="hello")

    assert isinstance(answer, Answer)
    assert answer.text == "hi there"
    assert answer.response_id == "resp_1"
    assert answer.usage == Usage(input_tokens=1000, cached_tokens=0, output_tokens=500)
    assert answer.cost == pytest.approx(0.003375)
    assert fake.requests == []
    assert not (tmp_path / "calls.jsonl").exists()      # replaying spends nothing, so nothing is logged


def test_replay_without_a_saved_answer_says_which_file_is_missing(tmp_path):
    c = MetaClient(mode="replay", saved_dir=tmp_path)
    with pytest.raises(LookupError, match="nothing_here.json"):
        c.respond("muse-spark-1.3", "hi", label="nothing_here")


def test_every_call_is_logged_with_its_cost(tmp_path, key):
    fake = FakeMeta(_answer_json())
    c, _ = _live(tmp_path, fake)

    answer = c.respond("muse-spark-1.3", "hi", label="greeting")

    assert answer.cost == pytest.approx(0.003375)
    [line] = _log(tmp_path)
    assert line["model"] == "muse-spark-1.3"
    assert line["label"] == "greeting"
    assert (line["input_tokens"], line["cached_tokens"], line["output_tokens"]) == (1000, 0, 500)
    assert line["cost"] == pytest.approx(0.003375)
    assert line["ok"] is True
    assert line["time"] and line["seconds"] >= 0
    assert c.spent() == pytest.approx(0.003375)


def test_cached_tokens_are_charged_at_the_cached_price():
    usage = Usage(input_tokens=1000, cached_tokens=400, output_tokens=0)
    assert cost_of("muse-spark-1.3", usage) == pytest.approx(600 * 1.25e-6 + 400 * 0.15e-6)
    assert cost_of("muse-wonder-1.0", Usage(input_tokens=1000, output_tokens=1000)) == pytest.approx(0.024)
    assert cost_of("muse-voice-transcribe-1.0", Usage(audio_seconds=3600)) == pytest.approx(0.18)


def test_a_model_with_no_price_is_refused_before_calling(tmp_path, key):
    fake = FakeMeta(_answer_json())
    c, _ = _live(tmp_path, fake)
    with pytest.raises(ValueError, match="no price"):
        c.respond("muse-mystery-9", "hi", label="x")
    assert fake.requests == []


def test_spending_stops_at_the_limit(tmp_path, key):
    fake = FakeMeta(_answer_json())                     # 0.003375 a call
    c, _ = _live(tmp_path, fake, limit_usd=0.01)
    for i in range(3):
        c.respond("muse-spark-1.3", "hi", label=f"call{i}")
    with pytest.raises(SpendLimitReached, match="0.01"):
        c.respond("muse-spark-1.3", "hi", label="one_too_many")
    assert len(fake.requests) == 3

    # The limit counts everything in the log, so a new program run is stopped too.
    again, _ = _live(tmp_path, fake, limit_usd=0.01)
    assert again.spent() == pytest.approx(3 * 0.003375)
    with pytest.raises(SpendLimitReached):
        again.respond("muse-spark-1.3", "hi", label="after_restart")
    assert len(fake.requests) == 3


def test_contributor_models_are_refused(tmp_path):
    c = MetaClient(mode="replay", saved_dir=tmp_path)
    with pytest.raises(ValueError, match="contributor"):
        c.respond("muse-spark-1.3-contributor", "hi", label="cheap")


def test_the_key_never_reaches_saved_files_or_logs(tmp_path, key):
    refused = httpx2.Response(401, json={"error": {"message": f"Incorrect API key provided: {key}",
                                                    "type": "authentication_error", "code": "invalid_api_key"}})
    fake = FakeMeta(_answer_json(), refused)
    c, _ = _live(tmp_path, fake, mode="record")

    c.respond("muse-spark-1.3", "hi", label="recorded")
    with pytest.raises(NoKey) as err:
        c.respond("muse-spark-1.3", "hi", label="bad_key")

    assert fake.requests[0].headers["authorization"] == f"Bearer {key}"   # the key was used...
    assert key not in str(err.value)
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert {p.name for p in written} >= {"recorded.json", "calls.jsonl"}
    for p in written:                                                     # ...and is in no file
        text = p.read_text(encoding="utf-8")
        assert key not in text and key[5:17] not in text, p.name
    saved = json.loads((tmp_path / "saved" / "recorded.json").read_text(encoding="utf-8"))
    assert saved["request"]["label"] == "recorded"
    assert saved["response"]["id"] == "resp_1"


def test_no_key_is_a_plain_error_and_never_calls(tmp_path, no_key):
    fake = FakeMeta(_answer_json())
    c, _ = _live(tmp_path, fake)
    with pytest.raises(NoKey, match="META_API_KEY"):
        c.respond("muse-spark-1.3", "hi", label="x")
    assert fake.requests == []


def test_network_failure_becomes_meta_unavailable(tmp_path, key):
    fake = FakeMeta(httpx2.ConnectError("no route to host"))
    c, sleeps = _live(tmp_path, fake)

    with pytest.raises(MetaUnavailable) as err:
        c.respond("muse-spark-1.3", "hi", label="offline")

    assert len(fake.requests) == 3                      # three tries
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0]   # growing waits between them
    assert "reach" in err.value.reason
    [line] = _log(tmp_path)
    assert line["ok"] is False and line["cost"] == 0


def test_a_server_error_is_retried_and_can_recover(tmp_path, key):
    busy = httpx2.Response(503, headers={"retry-after": "2"}, json={"error": {"message": "busy"}})
    fake = FakeMeta(busy, _answer_json("made it"))
    c, sleeps = _live(tmp_path, fake)

    assert c.respond("muse-spark-1.3", "hi", label="flaky").text == "made it"
    assert sleeps == [2.0]                              # Meta's Retry-After is honoured


def test_a_refused_request_is_not_retried(tmp_path, key):
    bad = httpx2.Response(400, json={"error": {"message": "The video could not be read.", "type": "invalid_request_error"}})
    fake = FakeMeta(bad)
    c, sleeps = _live(tmp_path, fake)

    with pytest.raises(MetaRefused) as err:
        c.respond("muse-spark-1.3", "hi", label="refused")

    assert err.value.status == 400
    assert "video could not be read" in err.value.reason
    assert len(fake.requests) == 1 and sleeps == []


def test_a_schema_becomes_structured_output_and_its_json_is_parsed(tmp_path, key):
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    fake = FakeMeta(_answer_json('{"n": 3}'), _answer_json('{"n": 3'))
    c, _ = _live(tmp_path, fake)

    good = c.respond("muse-spark-1.3", "count", label="count", schema=schema)
    broken = c.respond("muse-spark-1.3", "count", label="count_again", schema=schema)

    body = json.loads(fake.requests[0].content)
    assert body["text"]["format"] == {"type": "json_schema", "name": "count", "schema": schema, "strict": False}
    assert good.data == {"n": 3}
    assert broken.data is None and broken.text == '{"n": 3'


def test_a_model_refusal_is_reported(tmp_path, key):
    refusal = _answer_json()
    refusal["output"][0]["content"] = [{"type": "refusal", "refusal": "I can't help with that video."}]
    c, _ = _live(tmp_path, FakeMeta(refusal))
    answer = c.respond("muse-spark-1.3", "hi", label="no")
    assert answer.text == "" and answer.refusal == "I can't help with that video."


def test_upload_sends_the_file_and_returns_its_id(tmp_path, key):
    fake = FakeMeta({"id": "file-abc", "object": "file", "bytes": 3, "created_at": 0, "filename": "small.mp4",
                     "purpose": "user_data", "status": "processed"})
    c, _ = _live(tmp_path, fake, mode="record")
    video = tmp_path / "small.mp4"
    video.write_bytes(b"mp4")

    assert c.upload(video, label="upload_small") == "file-abc"
    assert fake.requests[0].url.path == "/v1/files"
    assert b'name="purpose"' in fake.requests[0].content and b"user_data" in fake.requests[0].content

    replay = MetaClient(mode="replay", saved_dir=tmp_path / "saved")
    assert replay.upload(video, label="upload_small") == "file-abc"


def _wav(path, seconds, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))
    return path


def test_transcribe_turns_become_segments_in_seconds(tmp_path, key):
    fake = FakeMeta({"sessionId": "s1", "transcript": "Click the cell. Type sum.", "audioDurationMs": 4000,
                     "turns": [{"turnId": 1, "startMs": 0, "endMs": 1500, "transcript": "Click the cell."},
                               {"turnId": 2, "startMs": 2000, "endMs": 4000, "transcript": "Type sum."}]})
    c, _ = _live(tmp_path, fake)

    t = c.transcribe(_wav(tmp_path / "a.wav", 4), label="voice")

    assert isinstance(t, Transcript)
    assert t.text == "Click the cell. Type sum."
    assert t.segments == [(0.0, 1.5, "Click the cell."), (2.0, 4.0, "Type sum.")]
    request = fake.requests[0]
    assert request.url.path == "/v1/asr/transcribe"
    assert b'"muse-voice-transcribe-1.0"' in request.content and b'name="audio"' in request.content
    [line] = _log(tmp_path)
    assert line["audio_seconds"] == 4 and line["cost"] == pytest.approx(4 / 3600 * 0.18)


def test_long_audio_is_sent_in_parts_with_shifted_times(tmp_path, key, monkeypatch):
    monkeypatch.setattr(meta_client, "AUDIO_PART_S", 3)
    part = {"transcript": "hi", "audioDurationMs": 3000, "turns": [{"startMs": 500, "endMs": 1000, "transcript": "hi"}]}
    fake = FakeMeta(part)
    c, _ = _live(tmp_path, fake)

    t = c.transcribe(_wav(tmp_path / "long.wav", 7), label="long")

    assert len(fake.requests) == 3                      # 3 s + 3 s + 1 s
    assert [s[:2] for s in t.segments] == [(0.5, 1.0), (3.5, 4.0), (6.5, 7.0)]
    assert t.text == "hi hi hi"


def test_a_transcript_with_no_turns_is_one_segment(tmp_path, key):
    fake = FakeMeta({"transcript": "all of it", "audioDurationMs": 2000, "turns": []})
    c, _ = _live(tmp_path, fake)
    assert c.transcribe(_wav(tmp_path / "a.wav", 2), label="v").segments == [(0.0, 2.0, "all of it")]
