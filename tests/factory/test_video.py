import json
import re
import struct
import subprocess

import imageio_ffmpeg
import pytest
from yt_dlp.utils import DownloadError

from app.factory import video
from app.factory.video import (Fetched, Prepared, VideoError, VideoInfo, VideoRefused, fetch, ffmpeg_frames_args,
                               ffmpeg_small_args, ffmpeg_still_args, frame_at, pick_captions, prepare,
                               vtt_to_segments)
from app.meta.client import MetaClient

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# Automatic captions as YouTube writes them: a line holding one space keeps a cue's second row.
ROLLING_VTT = "\n".join([
    "WEBVTT", "Kind: captions", "Language: en", "",
    "00:00:00.000 --> 00:00:02.330 align:start position:0%", " ",
    "click<00:00:00.320><c> the</c><00:00:00.640><c> cell</c>", "",
    "00:00:02.330 --> 00:00:02.340 align:start position:0%", "click the cell", " ", "",
    "00:00:02.340 --> 00:00:05.000 align:start position:0%", "click the cell",
    "type<00:00:02.500><c> equals</c><00:00:03.000><c> sum</c>", "",
    "00:00:05.000 --> 00:00:05.010 align:start position:0%", "type equals sum", " ", "",
    "00:00:05.010 --> 00:01:07.500 align:start position:0%", "type equals sum",
    "then<00:00:05.400><c> press</c><00:00:06.000><c> enter &amp; done</c>", "",
])


def test_vtt_rolling_captions_become_clean_segments():
    assert vtt_to_segments(ROLLING_VTT) == [
        (0.0, 2.33, "click the cell"),
        (2.34, 5.0, "type equals sum"),
        (5.01, 67.5, "then press enter & done"),
    ]


def test_manual_captions_keep_every_cue():
    text = "WEBVTT\n\n1\n00:01.000 --> 00:03.500\nOpen the Home tab.\n\n2\n00:03.500 --> 00:06.000\nPick Bold.\n"
    assert vtt_to_segments(text) == [(1.0, 3.5, "Open the Home tab."), (3.5, 6.0, "Pick Bold.")]


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL: `info` is what YouTube would say; `files` what a download writes."""

    def __init__(self, info=None, error=None, files=()):
        self.info, self.error, self.files = info, error, files
        self.calls = []

    def __call__(self, opts):
        self.calls.append(("open", opts))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        self.calls.append(("extract_info", download))
        if self.error:
            raise DownloadError(self.error)
        if download:
            outtmpl = self.calls[-2][1]["outtmpl"]["default"]
            for name in self.files:
                path = outtmpl.replace("video.%(ext)s", name)
                open(path, "w", encoding="utf-8").write("WEBVTT\n" if name.endswith(".vtt") else "mp4")
        return self.info


def _info(**over):
    info = {"id": "abc123", "webpage_url": "https://www.youtube.com/watch?v=abc123", "title": "SUM in Excel",
            "channel": "Sheet Skills", "channel_url": "https://www.youtube.com/@sheetskills",
            "license": "Creative Commons Attribution license (reuse allowed)", "duration": 312,
            "subtitles": {}, "automatic_captions": {"en": [{"ext": "vtt"}]}}
    info.update(over)
    return info


def test_long_video_is_refused_with_the_reason(tmp_path):
    ydl = FakeYDL(_info(duration=1380))
    with pytest.raises(VideoRefused, match="This video is 23 minutes. Pick one under 15."):
        fetch("https://youtu.be/abc123", tmp_path, ydl_class=ydl)
    assert ("extract_info", True) not in ydl.calls          # refused before anything was downloaded
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("message, reason", [
    ("ERROR: [youtube] abc123: Private video. Sign in if you've been granted access", "private"),
    ("ERROR: [youtube] abc123: Video unavailable. This video has been removed by the uploader", "removed"),
    ("ERROR: [youtube] abc123: Video unavailable. The uploader has not made this video available in your country",
     "your country"),
    ("ERROR: Unsupported URL: https://example.com/x", "not a video link"),
])
def test_private_removed_or_blocked_videos_get_a_plain_reason(tmp_path, message, reason):
    with pytest.raises(VideoRefused, match=reason):
        fetch("https://youtu.be/abc123", tmp_path, ydl_class=FakeYDL(error=message))


def test_a_download_error_with_no_plain_reason_keeps_its_words_for_the_log_only(tmp_path):
    message = "ERROR: [youtube] abc123: HTTP Error 403: Forbidden"
    with pytest.raises(VideoRefused) as caught:
        fetch("https://youtu.be/abc123", tmp_path, ydl_class=FakeYDL(error=message))
    assert str(caught.value) == "The video could not be downloaded. Try another video."
    assert caught.value.detail == message


def test_ffmpeg_trouble_is_said_plainly_and_its_words_kept_for_the_log(tmp_path):
    not_a_video = tmp_path / "notes.mp4"
    not_a_video.write_text("not a video")
    with pytest.raises(VideoError) as caught:
        frame_at(not_a_video, 1, tmp_path / "goal.png")
    assert str(caught.value) == "The video could not be read. Try another video."
    assert caught.value.detail.startswith("ffmpeg could not take a still picture: ")


def test_a_good_video_is_downloaded_with_its_details_and_captions(tmp_path):
    ydl = FakeYDL(_info(), files=("video.mp4", "video.en.vtt"))
    got = fetch("https://youtu.be/abc123", tmp_path, ydl_class=ydl)

    assert got.info == VideoInfo(id="abc123", url="https://www.youtube.com/watch?v=abc123", title="SUM in Excel",
                                 creator="Sheet Skills", channel_url="https://www.youtube.com/@sheetskills",
                                 licence="Creative Commons Attribution license (reuse allowed)", length_s=312)
    assert got.video == tmp_path / "video.mp4"
    assert got.captions == tmp_path / "video.en.vtt"
    opts = ydl.calls[2][1]
    assert opts["writeautomaticsub"] is True and opts["subtitleslangs"] == ["en"]
    assert "height<=720" in opts["format"] and opts["merge_output_format"] == "mp4"


def test_manual_english_captions_are_picked_before_automatic_ones():
    info = _info(subtitles={"live_chat": [], "en-GB": [{"ext": "vtt"}]},
                 automatic_captions={"en": [], "en-orig": []})
    assert pick_captions(info) == ("en-GB", False)
    assert pick_captions(_info(automatic_captions={"fr": [], "en-orig": [], "en": []})) == ("en-orig", True)
    assert pick_captions(_info(automatic_captions={"fr": []})) is None


def test_ffmpeg_args():
    small = ffmpeg_small_args("in.mp4", "out.mp4")
    assert small[:3] == ["-y", "-i", "in.mp4"] and small[-1] == "out.mp4"
    assert "scale=854:-2,fps=2" in small
    assert small[small.index("-ac") + 1] == "1"                          # the audio stays, small and mono
    frames = ffmpeg_frames_args("in.mp4", "frames", every_s=30)
    vf = frames[frames.index("-vf") + 1]
    assert "gt(scene,0.3)" in vf and "showinfo" in vf and "30" in vf
    assert frames[-1].replace("\\", "/") == "frames/frame_%04d.png"


def _width(path):
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    return int(re.search(r"Video:.*?(\d{3,4})x\d{3,4}", out).group(1))


def _fetched(clip, captions=None):
    info = VideoInfo("vid1", "https://youtu.be/vid1", "Test", "Me", "https://youtube.com/@me", "cc", 3)
    return Fetched(info, clip, captions)


def test_no_captions_falls_back_to_transcribe(tmp_path, clip):
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "transcribe_vid1.json").write_text(json.dumps({"request": {}, "response": {
        "transcript": "Click B7.", "audioDurationMs": 3000,
        "turns": [{"startMs": 200, "endMs": 1800, "transcript": "Click B7."}]}}))
    client = MetaClient(mode="replay", saved_dir=saved)

    prepared = prepare(_fetched(clip), client, workdir=tmp_path / "work")

    assert isinstance(prepared, Prepared)
    assert prepared.transcript == [(0.2, 1.8, "Click B7.")]
    assert _width(prepared.small_mp4) == 854
    assert [t for t, _ in prepared.frames] == [0.0, 1.0, 2.0]            # one a second for a 3-second clip
    assert all(p.exists() for _, p in prepared.frames)


def test_captions_are_used_when_there_are_some(tmp_path, clip):
    vtt = tmp_path / "video.en.vtt"
    vtt.write_text(ROLLING_VTT, encoding="utf-8")
    prepared = prepare(_fetched(clip, vtt), None, workdir=tmp_path / "work")
    assert prepared.transcript[0] == (0.0, 2.33, "click the cell")


def test_frames_are_thinned_to_forty(monkeypatch):
    times = [float(t) for t in range(100)]
    kept = video.thin(times, 40)
    assert len(kept) == 40 and kept[0] == 0.0 and kept[-1] == 99.0


def test_settle_moves_a_download_into_its_video_folder(tmp_path):
    incoming = tmp_path / "incoming-x"
    incoming.mkdir()
    (incoming / "video.mp4").write_text("new")
    (incoming / "video.en.vtt").write_text("WEBVTT\n")
    old = tmp_path / "vid1"
    old.mkdir()
    (old / "video.mp4").write_text("old")
    (old / "small.mp4").write_text("old small")
    info = VideoInfo("vid1", "https://youtu.be/vid1", "Test", "Me", "https://youtube.com/@me", "cc", 3)

    settled = video.settle(Fetched(info, incoming / "video.mp4", incoming / "video.en.vtt"), tmp_path / "vid1")

    assert settled == Fetched(info, old / "video.mp4", old / "video.en.vtt")
    assert (old / "video.mp4").read_text() == "new"
    assert not (old / "small.mp4").exists()               # an older download of the same video is replaced whole
    assert not incoming.exists()


def test_a_still_picture_is_taken_at_a_time_in_the_video(tmp_path, clip):
    assert ffmpeg_still_args("in.mp4", 2.5, "goal.png") == ["-y", "-loglevel", "error", "-ss", "2.500", "-i", "in.mp4",
                                                            "-frames:v", "1", "goal.png"]
    still = frame_at(clip, 2.5, tmp_path / "goal.png")
    data = still.read_bytes()
    assert still == tmp_path / "goal.png" and data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (1280, 720)


def test_a_time_past_the_end_of_the_video_has_no_picture(tmp_path, clip):
    with pytest.raises(VideoError, match="the video has no picture at 10 s"):
        frame_at(clip, 10, tmp_path / "goal.png")
    assert not (tmp_path / "goal.png").exists()
