"""Helpers shared by the factory's tests: a real test video and saved Meta answers."""
import json
import subprocess

import imageio_ffmpeg
import pytest

from app.meta.client import MetaClient


@pytest.fixture(scope="session")
def clip(tmp_path_factory):
    """A real 3-second video with sound, made by ffmpeg."""
    path = tmp_path_factory.mktemp("clip") / "video.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=10:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


def _content(part):
    return {"id": "resp_1", "output": [{"type": "message", "role": "assistant", "content": [part]}],
            "usage": {"input_tokens": 9000, "output_tokens": 1200}}


class Saved:
    """Saved Meta answers for one test, replayed by a real MetaClient."""

    def __init__(self, folder):
        self.folder = folder
        folder.mkdir()
        self.client = MetaClient(mode="replay", saved_dir=folder)

    def _write(self, label, record):
        (self.folder / f"{label}.json").write_text(json.dumps({"request": {"label": label}, **record}))

    def file(self, label, file_id="file-abc"):
        self._write(label, {"response": {"id": file_id, "object": "file"}})

    def answer(self, label, payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self._write(label, {"response": _content({"type": "output_text", "text": text})})

    def refusal(self, label, words):
        self._write(label, {"response": _content({"type": "refusal", "refusal": words})})

    def error(self, label, **error):
        self._write(label, {"error": error})


@pytest.fixture
def saved(tmp_path):
    return Saved(tmp_path / "saved")
