import base64
import json

import pytest

from app.core.types import Rect
from app.excel.vision import point_fallback
from app.meta.client import MetaClient, MetaRefused, MetaUnavailable, NoKey, SpendLimitReached
from app.win.windows import png_bytes
from tests.excel.fakes import FakeMeta, box

PICTURE = png_bytes(400, 300, bytes(400 * 300 * 4))     # a black 400 x 300 picture standing in for Excel
PIE = "Insert > Pie"


def test_an_answer_on_the_1000_grid_becomes_pixels_of_the_picture():
    assert point_fallback(FakeMeta(box(250, 100, 300, 200)))(PICTURE, PIE) == Rect(100, 30, 20, 30)


def test_muse_spark_is_shown_the_picture_and_told_which_button():
    meta = FakeMeta(box(250, 100, 300, 200))
    point_fallback(meta)(PICTURE, PIE)
    [call] = meta.asked
    assert call["model"] == "muse-spark-1.3" and call["label"] == "point_fallback"
    assert set(call["schema"]["required"]) == {"found", "left", "top", "right", "bottom"}
    parts = call["input"][-1]["content"]
    assert {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(PICTURE).decode()} in parts
    words = " ".join(p["text"] for p in parts if p["type"] == "input_text")
    assert "Pie" in words and "Insert" in words


@pytest.mark.parametrize("answer", [
    box(250, 100, 300, 200, found=False),          # Muse Spark could not see it
    box(300, 100, 250, 200),                       # its right edge left of its left edge
    box(250, 100, 300, 1200),                      # off the grid
    box(250, 100, 250, 200),                       # no width
    {"found": True, "left": 250},                  # half an answer
    box("250", 100, 300, 200),                     # words, not numbers
    box(True, 100, 300, 200),
    [250, 100, 300, 200],
    None,                                          # not JSON at all
])
def test_an_answer_that_is_not_a_clear_box_is_no_answer(answer):
    assert point_fallback(FakeMeta(answer))(PICTURE, PIE) is None


def test_a_refusal_is_no_answer():
    meta = FakeMeta(box(250, 100, 300, 200), refusal="I can't help with that")
    assert point_fallback(meta)(PICTURE, PIE) is None


@pytest.mark.parametrize("error", [NoKey("no key"), MetaUnavailable("Meta is down"),
                                   SpendLimitReached("the limit is reached"), MetaRefused(400, "bad picture")])
def test_trouble_with_meta_is_no_answer(error):
    assert point_fallback(FakeMeta(error=error))(PICTURE, PIE) is None


def test_something_that_is_not_a_picture_is_never_sent():
    meta = FakeMeta(box(250, 100, 300, 200))
    assert point_fallback(meta)(b"not a picture", PIE) is None
    assert meta.asked == []


def test_the_real_client_reads_a_saved_answer(tmp_path):
    reply = {"id": "resp_1", "usage": {"input_tokens": 1500, "output_tokens": 20},
             "output": [{"type": "message", "role": "assistant",
                         "content": [{"type": "output_text", "text": json.dumps(box(250, 100, 300, 200))}]}]}
    (tmp_path / "point_fallback.json").write_text(json.dumps({"request": {"label": "point_fallback"},
                                                              "response": reply}))
    client = MetaClient(mode="replay", saved_dir=tmp_path)
    assert point_fallback(client)(PICTURE, PIE) == Rect(100, 30, 20, 30)
