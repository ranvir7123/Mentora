import json

import pytest

from app.core.fake_plugin import FakePlugin
from app.core.lesson import Lesson, Source, lesson_json_schema, validate
from app.factory.video import Prepared, VideoInfo
from app.factory.writer import NotReady, write_lesson

INFO = VideoInfo("vid1", "https://youtu.be/vid1", "Fill in the keys", "Key Teacher", "https://youtube.com/@keys",
                 "Creative Commons Attribution license (reuse allowed)", 120)


def _step(i, **over):
    step = {"id": f"s{i}", "instruction": f"Set k{i} to {i}.", "why": f"k{i} needs a value.",
            "target": {"kind": "key", "ref": f"k{i}"},
            "check": {"kind": "equals", "args": {"key": f"k{i}", "value": i}},
            "replay": {"kind": "set", "args": {"key": f"k{i}", "value": i}},
            "hints": [f"Find k{i}.", f"k{i} needs a number.", f"Set k{i} to {i}."],
            "mistakes": [{"replay": {"kind": "set", "args": {"key": f"k{i}", "value": -i}},
                          "not_yet": f"k{i} should be {i}, not {-i}."}],
            "clip": {"start": 10.0 * i, "end": 10.0 * i + 8}}
    step.update(over)
    return step


def _lesson(steps=None, title="Fill in the keys"):
    """What Muse Spark answers: the parts of a lesson the schema asks for."""
    return {"title": title, "goal": {"sentence": "Every key holds its number."}, "starter": {"k0": 0},
            "steps": steps if steps is not None else [_step(1), _step(2)]}


class Spy:
    """Passes calls on to the real client and keeps what was sent."""

    def __init__(self, inner):
        self.inner, self.uploads, self.responds = inner, [], []

    def upload(self, path, *, label):
        self.uploads.append({"path": path, "label": label})
        return self.inner.upload(path, label=label)

    def respond(self, model, input, *, label, schema=None, **extra):
        self.responds.append({"model": model, "input": input, "label": label, "schema": schema})
        return self.inner.respond(model, input, label=label, schema=schema, **extra)


@pytest.fixture
def spy(saved):
    return Spy(saved.client)


@pytest.fixture
def prepared(tmp_path):
    (tmp_path / "small.mp4").write_bytes(b"mp4")
    frames = []
    for i, t in enumerate((0.0, 1.5, 9.25)):
        path = tmp_path / f"frame_{i + 1:04d}.png"
        path.write_bytes(b"\x89PNG fake picture %d" % i)
        frames.append((t, path))
    return Prepared(tmp_path / "small.mp4", frames, [(0.5, 4.0, "set k1 to one"), (11.0, 15.0, "now k2")])


@pytest.fixture
def lessons(tmp_path):
    return tmp_path / "lessons"


def _parts(sent):
    """Every content part of every message sent."""
    return [p for m in sent for p in (m["content"] if isinstance(m["content"], list) else [])]


def _sent_text(sent):
    return json.dumps(sent, ensure_ascii=False)


def test_a_good_answer_becomes_a_valid_lesson(prepared, saved, spy, lessons):
    saved.file("writer_vid1_upload")
    saved.answer("writer_vid1", _lesson())

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert isinstance(got, Lesson)
    assert validate(got, FakePlugin()) == []
    assert got.id == "fill-in-the-keys" and got.folder == lessons / "fill-in-the-keys"
    assert (got.app, got.course, got.made_by, got.edited_by_hand) == ("fake", "fake", "generated", False)
    assert got.proof is None and got.test is None
    assert got.source == Source(INFO.url, INFO.title, INFO.creator, INFO.channel_url, INFO.licence, 120)
    assert [s.id for s in got.steps] == ["s1", "s2"] and got.steps[0].mistakes[0].code == ""

    assert spy.uploads == [{"path": prepared.small_mp4, "label": "writer_vid1_upload"}]
    (call,) = spy.responds
    assert call["model"] == "muse-spark-1.3"
    assert call["schema"] == lesson_json_schema(FakePlugin())
    assert {"type": "input_file", "file_id": "file-abc"} in _parts(call["input"])
    text = _sent_text(call["input"])
    assert "[0.5-4.0 s] set k1 to one" in text                       # the transcript, with its times
    assert "equals(key: text, value: value): the key holds this value" in text      # the check menu
    assert "delete(key: text): remove the key" in text                               # the operation menu
    rules = call["input"][0]["content"]
    assert "at most 12 words" in rules and 'Never say "simply" or "just"' in rules


def test_an_off_menu_check_is_retried_once_then_not_ready(prepared, saved, spy, lessons):
    bad = _lesson([_step(1, check={"kind": "contains", "args": {"key": "k1"}}), _step(2)])
    saved.file("writer_vid1_upload")
    saved.answer("writer_vid1", bad)
    saved.answer("writer_vid1_retry", bad)

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert isinstance(got, NotReady)
    assert "step s1: check contains is not on the Fake app menu" in got.reason
    assert [c["label"] for c in spy.responds] == ["writer_vid1", "writer_vid1_retry"]
    assert "step s1: check contains is not on the Fake app menu" in _sent_text(spy.responds[1]["input"])


def _in_starter(t):
    return {**_lesson(), "starter": {"k0": t}}


def _in_replay(t):
    return _lesson([_step(1, replay={"kind": "set", "args": {"key": "k1", "value": t}}), _step(2)])


def _in_mistake(t):
    return _lesson([_step(1), _step(2, mistakes=[{"replay": {"kind": "set", "args": {"key": "k2", "value": t}},
                                                  "not_yet": "k2 should be 2."}])])


def _in_hint(t):
    return _lesson([_step(1, hints=["Find k1.", t, "Set k1 to 1."]), _step(2)])


def _in_instruction(t):
    return _lesson([_step(1, instruction=t), _step(2)])


def _sent_back_then_not_ready(prepared, saved, spy, lessons, answer, problem):
    saved.file("writer_vid1_upload")
    saved.answer("writer_vid1", answer)
    saved.answer("writer_vid1_retry", answer)

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert got == NotReady(f"Muse Spark's lesson broke the rules: {problem}.")
    retry = spy.responds[1]["input"][-1]["content"]
    assert retry == f"That lesson broke these rules:\n- {problem}\nWrite the whole lesson again, fixing every one."


@pytest.mark.parametrize("where, text, put", [
    ("the starter", '=HYPERLINK("https://example.com","x")', _in_starter),
    ("step s2", "=cmd|' /c calc'!A0", _in_mistake),
    ("the starter", "\\\\server\\share\\prices.xlsx", _in_starter),
    ("the starter", "=[Budget.xlsx]Sheet1!A1", _in_starter),
    ("step s1", "See www.example.com for the numbers.", _in_hint),
    ("step s1", "Write to mailto:help@example.com.", _in_hint),
])
def test_a_lesson_that_reaches_outside_the_app_is_sent_back_then_not_ready(prepared, saved, spy, lessons,
                                                                          where, text, put):
    _sent_back_then_not_ready(prepared, saved, spy, lessons, put(text),
                              f"{where}: {text} reaches outside Fake app; a lesson must stay inside it")


@pytest.mark.parametrize("where, text, put, name", [
    ("step s1", "=WEBSERVICE(A1)", _in_replay, "WEBSERVICE"),
    ("the starter", "=IMPORTCSV(A1)", _in_starter, "IMPORTCSV"),          # a new function that reads files
    ("the starter", "=_xlfn.COPILOT(A1)", _in_starter, "COPILOT"),        # as saved in a file, with its prefix
    ("the starter", "=MAP(A1,WEBSERVICE)", _in_starter, "MAP"),           # calls a function it names
    ("the starter", "=LET(f,A1,f+1)", _in_starter, "LET"),
    ("the starter", "=MyMacro(A1)", _in_starter, "MYMACRO"),              # a function written in a macro
    ("step s1", "k1\t=WEBSERVICE(A1)", _in_replay, "WEBSERVICE"),        # Tab moves to the next cell when typed
    ("step s1", "Type =WEBSERVICE(A1) in k1.", _in_instruction, "WEBSERVICE"),   # the agent types what it reads
    ("step s1", "Type =SUM(A1) + WEBSERVICE(B1) in k1.", _in_hint, "WEBSERVICE"),
])
def test_a_formula_using_a_function_lessons_may_not_use_is_sent_back_then_not_ready(prepared, saved, spy, lessons,
                                                                                   where, text, put, name):
    _sent_back_then_not_ready(prepared, saved, spy, lessons, put(text),
                              f"{where}: {text} uses {name}, which a lesson may not use")


def test_formulas_that_stay_in_the_workbook_are_fine(prepared, saved, spy, lessons):
    inside = ["=SUM(Table1[Sales])", "=B2+B3", "Save the file: it keeps your work.", "-5", "Call it Total.",
              '=TEXTJOIN("|",TRUE,A1:A3)', "=IFERROR(VLOOKUP(A2,B:C,2,FALSE),0)", "=_xlfn.XLOOKUP(A1,B:B,C:C)",
              "=@INDEX(B2:B9,3)", "Type =B2*12 in B3 (the yearly total).", "Make k1 = 5 (five).",
              "Step 2 - insert an image (PNG) later.", "=sum(b2:b5)"]
    saved.file("writer_vid1_upload")
    saved.answer("writer_vid1", {**_lesson(), "starter": {f"k{i}": t for i, t in enumerate(inside)}})

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert isinstance(got, Lesson) and len(spy.responds) == 1


def test_broken_json_is_not_ready_with_a_plain_reason(prepared, saved, spy, lessons):
    saved.file("writer_vid1_upload")
    saved.answer("writer_vid1", '{"title": "Fill in')
    saved.answer("writer_vid1_retry", "Here is your lesson!")

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert isinstance(got, NotReady)
    assert got.reason == "Muse Spark's lesson broke the rules: its answer was not a lesson in JSON."


@pytest.mark.parametrize("refused_at", ["upload", "answer"])
def test_a_refused_video_falls_back_to_frames(prepared, saved, spy, lessons, refused_at):
    refused = {"type": "refused", "status": 400, "message": "video input is not supported"}
    if refused_at == "upload":
        saved.error("writer_vid1_upload", **refused)
    else:
        saved.file("writer_vid1_upload")
        saved.error("writer_vid1", **refused)
    saved.answer("writer_vid1_frames", _lesson())

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert isinstance(got, Lesson)
    sent = spy.responds[-1]
    assert sent["label"] == "writer_vid1_frames"
    parts = _parts(sent["input"])
    assert not [p for p in parts if p["type"] == "input_file"]
    pictures = [p for p in parts if p["type"] == "input_image"]
    assert len(pictures) == 3 and all(p["image_url"].startswith("data:image/png;base64,") for p in pictures)
    assert "Frame at 1.5 s:" in _sent_text(sent["input"])


def test_long_instructions_are_sent_back_with_the_problem(prepared, saved, spy, lessons):
    long = _step(1, instruction="Click on the cell called k1 and then type the number one into it now")
    saved.file("writer_vid1_upload")
    saved.answer("writer_vid1", _lesson([long, _step(2)]))
    saved.answer("writer_vid1_retry", _lesson())

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert isinstance(got, Lesson) and got.steps[0].instruction == "Set k1 to 1."
    retry = _sent_text(spy.responds[1]["input"])
    assert "step s1: the instruction has 15 words; keep it to 12" in retry
    assert "Click on the cell called k1" in retry                     # its own first answer goes back too


def test_a_clip_past_the_end_and_a_step_with_no_mistakes_are_problems(prepared, saved, spy, lessons):
    saved.file("writer_vid1_upload")
    saved.answer("writer_vid1", _lesson([_step(1, clip={"start": 100, "end": 500}), _step(2, mistakes=[])]))
    saved.answer("writer_vid1_retry", _lesson([_step(1, clip={"start": 100, "end": 500}), _step(2, mistakes=[])]))

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert isinstance(got, NotReady)
    assert got.reason == ("Muse Spark's lesson broke the rules: step s1: the clip ends at 500 s, after the video "
                          "ends at 120 s; step s2: it has no predicted mistakes; give 1 or 2.")


def test_not_ready_names_only_the_first_three_problems(prepared, saved, spy, lessons):
    bad = _lesson([_step(i, hints=["one"]) for i in range(1, 6)])
    saved.file("writer_vid1_upload")
    saved.answer("writer_vid1", bad)
    saved.answer("writer_vid1_retry", bad)

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert got.reason == ("Muse Spark's lesson broke the rules: step s1: it has 1 hints; it needs exactly 3; "
                          "step s2: it has 1 hints; it needs exactly 3; step s3: it has 1 hints; it needs exactly 3; "
                          "and 2 more.")


def test_the_id_is_unique_in_the_lessons_folder(prepared, saved, spy, lessons):
    (lessons / "fill-in-the-keys").mkdir(parents=True)
    saved.file("writer_vid1_upload")
    saved.answer("writer_vid1", _lesson(title="Fill in the keys!"))

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert got.id == "fill-in-the-keys-2"


def test_the_provers_reason_goes_into_the_request(prepared, saved, spy, lessons):
    saved.file("writer_vid1_fix_upload")
    saved.answer("writer_vid1_fix", _lesson())

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons,
                       feedback="step s2: its check was already true before the step")

    assert isinstance(got, Lesson)
    assert "step s2: its check was already true before the step" in _sent_text(spy.responds[0]["input"])


def test_a_refusal_by_the_model_is_not_ready(prepared, saved, spy, lessons):
    saved.file("writer_vid1_upload")
    saved.refusal("writer_vid1", "I can't help with that video.")

    got = write_lesson(prepared, INFO, FakePlugin(), spy, lessons_dir=lessons)

    assert got == NotReady("Muse Spark would not write this lesson: I can't help with that video.")
    assert len(spy.responds) == 1
