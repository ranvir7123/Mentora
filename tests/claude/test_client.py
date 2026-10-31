import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.ai import ai_name, key_name, make_client, make_maker_client
from app.claude.client import CLAUDE_MODEL, ClaudeClient
from app.coach.coach import CoachUnavailable, MetaCoach
from app.excel.vision import point_fallback
from app.meta.client import MetaClient, MetaRefused, MetaUnavailable, NoKey, SpendLimitReached


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
    assert sent_schema["schema"]["properties"]["left"] == {"type": "integer", "description": "At least 0. At most 1000."}


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


def test_the_lesson_maker_uses_claude_only_with_the_switch():
    assert isinstance(make_maker_client(environ={}), MetaClient)
    maker = make_maker_client(environ={"MENTORA_AI": "claude"})
    assert isinstance(maker, ClaudeClient)
    assert maker.max_tokens >= 16000 and maker.timeout_s >= 300      # a whole lesson is a long answer


def test_claude_takes_still_frames_not_a_video_file(tmp_path):
    client, api = _client(tmp_path)
    with pytest.raises(MetaRefused):
        client.upload(tmp_path / "small.mp4", label="writer_vid1_upload")
    assert api.sent == []


def test_the_writer_names_claude_when_its_lesson_breaks_the_rules(tmp_path):
    from app.core.fake_plugin import FakePlugin
    from app.factory.video import Prepared, VideoInfo
    from app.factory.writer import NotReady, write_lesson

    frame = tmp_path / "frame_0001.png"
    frame.write_bytes(b"\x89PNG fake picture")
    prepared = Prepared(tmp_path / "small.mp4", [(0.0, frame)], [(0.5, 4.0, "set k1 to one")])
    info = VideoInfo("vid1", "https://youtu.be/vid1", "Fill in the keys", "Key Teacher", "https://youtube.com/@keys",
                     "Creative Commons Attribution license (reuse allowed)", 120)
    client, api = _client(tmp_path, _reply(_text("not json")), _reply(_text("still not json")))

    got = write_lesson(prepared, info, FakePlugin(), client, lessons_dir=tmp_path / "lessons")

    assert isinstance(got, NotReady)
    assert got.reason == "Claude could not write a lesson that keeps the rules from this video. Try another video."
    assert got.detail == "Claude's lesson broke the rules: its answer was not a lesson in JSON."
    images = [b for b in api.sent[0]["messages"][0]["content"] if b["type"] == "image"]
    assert len(images) == 1                                          # the frames went, not the video


def test_the_lesson_maker_asks_claude_to_think_with_room_for_a_whole_lesson(tmp_path):
    client, api = _client(tmp_path, _reply(_text("{}")), max_tokens=32000, effort="medium", thinking=True)
    client.respond("muse-spark-1.3", "Write the lesson.", label="writer_vid1", schema={"type": "object"})
    [sent] = api.sent
    assert sent["max_tokens"] == 32000 and sent["thinking"] == {"type": "adaptive"}
    assert sent["output_config"]["effort"] == "medium"


def test_the_ask_box_does_not_ask_claude_to_think(tmp_path):
    client, api = _client(tmp_path, _reply(_text("Select A1 first.")))
    client.respond("muse-spark-1.3", "How?", label="coach_answer")
    assert "thinking" not in api.sent[0] and api.sent[0]["max_tokens"] == 4000


OPEN = {"type": "object", "properties": {
    "title": {"type": "string"},
    "starter": {"type": "object"},
    "steps": {"type": "array", "items": {"type": "object", "properties": {"state": {"type": "object"}},
                                         "required": ["state"]}}},
    "required": ["title", "starter", "steps"], "additionalProperties": False}


def test_an_open_object_goes_to_claude_as_json_text_and_comes_back_as_an_object(tmp_path):
    said = {"title": "Pie", "starter": json.dumps({"sheets": [{"name": "Sheet1"}]}),
            "steps": [{"state": json.dumps({"k1": 1})}]}
    client, api = _client(tmp_path, _reply(_text(json.dumps(said))))

    answer = client.respond("muse-spark-1.3", "Write it.", label="writer_vid1", schema=OPEN)

    sent = api.sent[0]["output_config"]["format"]["schema"]
    assert sent["properties"]["starter"]["type"] == "string"           # Claude cannot take an object of any shape
    assert sent["properties"]["steps"]["items"]["properties"]["state"]["type"] == "string"
    assert sent["properties"]["steps"]["items"]["additionalProperties"] is False   # Claude needs it said
    assert answer.data == {"title": "Pie", "starter": {"sheets": [{"name": "Sheet1"}]}, "steps": [{"state": {"k1": 1}}]}


def test_open_object_text_that_is_not_json_stays_text_for_the_caller_to_reject(tmp_path):
    said = {"title": "Pie", "starter": "not json", "steps": []}
    client, _ = _client(tmp_path, _reply(_text(json.dumps(said))))
    assert client.respond("m", "Write it.", label="w", schema=OPEN).data["starter"] == "not json"


def test_claudes_own_reason_for_refusing_a_request_reaches_the_call_log(tmp_path):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.BadRequestError("bad", response=httpx2.Response(400, request=request), body={
        "type": "error", "error": {"type": "invalid_request_error", "message": "schema: say additionalProperties"}})
    client, _ = _client(tmp_path, error)

    with pytest.raises(MetaRefused) as caught:
        client.respond("m", "Write it.", label="writer_vid1")

    assert "schema: say additionalProperties" in str(caught.value)
    logged = json.loads((tmp_path / "claude_calls.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert "schema: say additionalProperties" in logged["error"]


def test_an_object_with_optional_fields_goes_as_json_text_naming_its_fields(tmp_path):
    schema = {"type": "object", "properties": {"args": {"type": "object", "properties": {
        "cell": {"type": "string"}, "value": {"type": ["number", "string"]}}, "required": ["cell"],
        "additionalProperties": False}}, "required": ["args"], "additionalProperties": False}
    said = {"args": json.dumps({"cell": "B6"})}
    client, api = _client(tmp_path, _reply(_text(json.dumps(said))))

    answer = client.respond("m", "Write it.", label="w", schema=schema)

    sent = api.sent[0]["output_config"]["format"]["schema"]["properties"]["args"]
    assert sent["type"] == "string" and "cell" in sent["description"] and "value" in sent["description"]
    assert answer.data == {"args": {"cell": "B6"}}


def test_list_and_number_limits_claude_does_not_take_become_words(tmp_path):
    schema = {"type": "object", "properties": {
        "hints": {"type": "array", "items": {"type": "string", "maxLength": 80}, "minItems": 3, "maxItems": 3},
        "notes": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1}},
        "required": ["hints", "notes"], "additionalProperties": False}
    client, api = _client(tmp_path, _reply(_text('{"hints": [], "notes": []}')))

    client.respond("m", "Write it.", label="w", schema=schema)

    sent = api.sent[0]["output_config"]["format"]["schema"]["properties"]
    assert "minItems" not in sent["hints"] and "maxItems" not in sent["hints"]
    assert sent["hints"]["description"] == "At least 3 items. At most 3 items."
    assert "maxLength" not in sent["hints"]["items"] and "minimum" not in sent["notes"]["items"]
    assert sent["notes"]["minItems"] == 1                                # 0 and 1 Claude does take
