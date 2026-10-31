import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.ai import ai_name, key_name, make_client
from app.claude.client import CLAUDE_MODEL, ClaudeClient
from app.coach.coach import CoachUnavailable, MetaCoach
from app.excel.vision import point_fallback
from app.meta.client import MetaClient, MetaUnavailable, NoKey, SpendLimitReached


def _reply(*blocks, stop="end_turn", input_tokens=100, output_tokens=20):
    return SimpleNamespace(id="msg_1", content=list(blocks), stop_reason=stop, stop_details=None,
                           usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0))


def _text(text):
    return SimpleNamespace(type="text", text=text)


class FakeApi:
    """Stands in for anthropic.Anthropic: keeps each request, answers from a list."""

    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request):
        self.sent.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _client(tmp_path, *answers, **kw):
    api = FakeApi(*answers)
    return ClaudeClient(api=api, log_path=tmp_path / "claude_calls.jsonl", **kw), api


def _status_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("nope", response=httpx2.Response(status, request=request), body=None)


def test_the_meta_style_request_becomes_a_claude_request(tmp_path):
    client, api = _client(tmp_path, _reply(_text("Click B6, then type =SUM(B2:B5).")))
    answer = client.respond("muse-spark-1.3", [{"role": "system", "content": "Be calm."},
                                               {"role": "user", "content": "How do I total?"}], label="coach_answer")
    assert answer.text == "Click B6, then type =SUM(B2:B5)."
    assert answer.refusal == ""
    sent = api.sent[0]
    assert sent["model"] == CLAUDE_MODEL == "claude-opus-5-5"
    assert sent["system"] == "Be calm."
    assert sent["messages"] == [{"role": "user", "content": "How do I total?"}]
    assert sent["output_config"]["effort"] == "low"


def test_a_picture_and_a_schema_go_across_and_the_json_comes_back(tmp_path):
    client, api = _client(tmp_path, _reply(_text('{"found": true, "left": 1, "top": 2, "right": 3, "bottom": 4}')))
    schema = {"title": "point_fallback", "type": "object", "additionalProperties": False,
              "properties": {"found": {"type": "boolean"}, "left": {"type": "integer", "minimum": 0, "maximum": 1000}},
              "required": ["found", "left"]}
    answer = client.respond("muse-spark-1.3", [{"role": "user", "content": [
        {"type": "input_text", "text": "Find this button: Home > Bold"},
        {"type": "input_image", "image_url": "data:image/png;base64,QUJD"}]}], label="point_fallback", schema=schema)
    assert answer.data == {"found": True, "left": 1, "top": 2, "right": 3, "bottom": 4}
    content = api.sent[0]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "Find this button: Home > Bold"}
    assert content[1] == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"}}
    sent_schema = api.sent[0]["output_config"]["format"]
    assert sent_schema["type"] == "json_schema"
    assert "title" not in sent_schema["schema"]
    assert sent_schema["schema"]["properties"]["left"] == {"type": "integer"}


def test_a_refusal_is_an_answer_with_its_refusal_set(tmp_path):
    client, _ = _client(tmp_path, _reply(stop="refusal"))
    answer = client.respond("muse-spark-1.3", "help", label="coach_answer")
    assert answer.refusal
    assert answer.text == ""


@pytest.mark.parametrize("error, kind", [
    (lambda: _status_error(anthropic.AuthenticationError, 401), NoKey),
    (lambda: _status_error(anthropic.RateLimitError, 429), MetaUnavailable),
    (lambda: _status_error(anthropic.InternalServerError, 529), MetaUnavailable),
    (lambda: anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")), MetaUnavailable),
])
def test_claude_errors_become_the_errors_the_coach_already_handles(tmp_path, error, kind):
    client, _ = _client(tmp_path, error())
    with pytest.raises(kind):
        client.respond("muse-spark-1.3", "help", label="coach_answer")


def test_no_key_is_a_no_key_error(tmp_path):
    client = ClaudeClient(log_path=tmp_path / "log.jsonl", find_key=lambda name: (None, "missing"))
    with pytest.raises(NoKey):
        client.respond("muse-spark-1.3", "help", label="coach_answer")


def test_each_call_is_logged_with_its_cost_and_the_limit_stops_more(tmp_path):
    log = tmp_path / "claude_calls.jsonl"
    client, _ = _client(tmp_path, _reply(_text("ok"), input_tokens=1_000_000, output_tokens=0), limit_usd=3.0)
    client.respond("muse-spark-1.3", "help", label="coach_answer")
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["label"] == "coach_answer" and entry["model"] == CLAUDE_MODEL
    assert entry["cost"] == pytest.approx(4.0)            # $4 per million input tokens
    with pytest.raises(SpendLimitReached):
        client.respond("muse-spark-1.3", "help", label="coach_answer")


def test_the_coach_works_unchanged_on_claude(tmp_path):
    client, _ = _client(tmp_path, _reply(_text("Select B6 first, then type the formula.")))
    coach = MetaCoach(client)
    assert coach.answer("How?", {"instruction": "Total B6.", "hints": ["Click B6."], "hints_shown": 0}) \
        == "Select B6 first, then type the formula."


def test_the_coach_names_claude_when_the_claude_key_is_missing(tmp_path):
    coach = MetaCoach(ClaudeClient(log_path=tmp_path / "l.jsonl", find_key=lambda name: (None, "missing")))
    with pytest.raises(CoachUnavailable, match="Claude key"):
        coach.answer("How?", {"instruction": "Total B6."})


def test_the_pointing_fallback_works_on_claude(tmp_path):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (2000).to_bytes(4, "big") + (1000).to_bytes(4, "big") + b"\x00" * 8
    client, _ = _client(tmp_path, _reply(_text('{"found": true, "left": 100, "top": 100, "right": 200, "bottom": 300}')))
    box = point_fallback(client)(png, "Home > Bold")
    assert (box.x, box.y, box.w, box.h) == (200, 100, 200, 200)


def test_meta_stays_the_default_and_claude_needs_the_switch():
    assert ai_name({}) == "meta" and key_name({}) == "META_API_KEY"
    assert isinstance(make_client(timeout_s=30.0, environ={}), MetaClient)
    on = {"MENTORA_AI": "claude"}
    assert ai_name(on) == "claude" and key_name(on) == "ANTHROPIC_API_KEY"
    assert isinstance(make_client(timeout_s=30.0, environ=on), ClaudeClient)
    assert ai_name({"MENTORA_AI": "something else"}) == "meta"
