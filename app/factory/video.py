"""Getting a tutorial video and preparing it for Muse Spark.

`fetch` asks YouTube about the video first and refuses it, with a plain reason, before downloading
anything when it is too long, private, removed or blocked. Then it downloads an MP4 of at most 720p and
English captions (written ones first, then automatic ones). `prepare` makes a small copy for Muse Spark
(854 px wide, 2 frames a second, small mono sound), pulls still frames at scene changes and at a steady
beat (at most 40), and turns the captions into a transcript, or asks Muse Voice Transcribe when there
are none. Everything lands in the video's own folder under `recordings/`, which git ignores.
"""
from __future__ import annotations

import html
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence, TypeVar

import imageio_ffmpeg
import yt_dlp
from yt_dlp.utils import DownloadError

from app.meta.client import MetaClient

MAX_FRAMES = 40
SCENE = 0.3
SMALL_WIDTH = 854
FORMAT = ("bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/bv*[height<=720]+ba/b[height<=720]")

Segment = tuple[float, float, str]
T = TypeVar("T")


class VideoError(Exception):
    """The video could not be got or prepared; the message is plain words."""


class VideoRefused(VideoError):
    """The video is not one we can make a lesson from; the message says why."""


@dataclass(frozen=True)
class VideoInfo:
    id: str
    url: str
    title: str
    creator: str
    channel_url: str
    licence: str
    length_s: int


@dataclass(frozen=True)
class Fetched:
    info: VideoInfo
    video: Path
    captions: Path | None


@dataclass(frozen=True)
class Prepared:
    small_mp4: Path
    frames: list[tuple[float, Path]]             # (seconds into the video, picture)
    transcript: list[Segment]


# Getting the video.

def fetch(url: str, dest: Path, *, max_length_s: int = 900, ydl_class: Any = None) -> Fetched:
    ydl_class = ydl_class or yt_dlp.YoutubeDL
    dest = Path(dest)
    quiet = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True}
    info = _ask(ydl_class, quiet, url, download=False)
    if not isinstance(info, dict) or info.get("_type") == "playlist":
        raise VideoRefused("That link is not one video. Paste the link of a single video.")
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
        raise VideoRefused("That is a live stream. Pick a finished video.")
    length = info.get("duration")
    if not length:
        raise VideoRefused("The video's length could not be found. Pick another video.")
    if length > max_length_s:
        raise VideoRefused(f"This video is {math.ceil(length / 60)} minutes. Pick one under {max_length_s // 60}.")

    dest.mkdir(parents=True, exist_ok=True)
    page = info.get("webpage_url") or url
    captions = pick_captions(info)
    opts = {**quiet, "format": FORMAT, "merge_output_format": "mp4",
            "outtmpl": {"default": str(dest / "video.%(ext)s")}, "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
            "writesubtitles": bool(captions and not captions[1]), "writeautomaticsub": bool(captions and captions[1]),
            "subtitleslangs": [captions[0]] if captions else [], "subtitlesformat": "vtt"}
    try:
        _ask(ydl_class, opts, page, download=True)
    except VideoRefused:
        if not captions:
            raise
        # Captions often fail on their own (YouTube rate-limits them); the video is still worth having.
        captions = None
        _ask(ydl_class, {**opts, "writesubtitles": False, "writeautomaticsub": False, "subtitleslangs": []},
             page, download=True)
    video = dest / "video.mp4"
    if not video.exists():
        raise VideoError("The download finished but no MP4 was saved. Try again.")
    vtt = dest / f"video.{captions[0]}.vtt" if captions else None
    return Fetched(_info(info, page), video, vtt if vtt is not None and vtt.exists() else None)


def settle(fetched: Fetched, folder: Path) -> Fetched:
    """Move a download into its video's own folder, replacing an older download of the same video."""
    folder = Path(folder)
    if folder.exists():
        shutil.rmtree(folder)
    fetched.video.parent.replace(folder)
    return Fetched(fetched.info, folder / fetched.video.name,
                   None if fetched.captions is None else folder / fetched.captions.name)


def _ask(ydl_class: Any, opts: dict, url: str, *, download: bool) -> Any:
    try:
        with ydl_class(opts) as ydl:
            return ydl.extract_info(url, download=download)
    except DownloadError as exc:
        raise VideoRefused(_plain(str(exc))) from None


def _info(info: dict, page: str) -> VideoInfo:
    return VideoInfo(id=str(info["id"]), url=page, title=str(info.get("title") or "Untitled video"),
                     creator=str(info.get("channel") or info.get("uploader") or "Unknown creator"),
                     channel_url=str(info.get("channel_url") or info.get("uploader_url") or ""),
                     licence=str(info.get("license") or "Standard YouTube licence"),
                     length_s=int(info["duration"]))


_REASONS = (
    ("private video", "This video is private."),
    ("removed", "This video has been removed."),
    ("your country", "This video is not available in your country."),
    ("confirm your age", "This video needs a signed-in adult account. Pick another one."),
    ("not a bot", "YouTube asked us to prove we are not a bot. Try again later."),
    ("unsupported url", "That link is not a video link we can open."),
    ("is not a valid url", "That link is not a video link we can open."),
    ("unable to download webpage", "YouTube could not be reached. Check the internet connection."),
    ("video unavailable", "This video is unavailable."),
)


def _plain(message: str) -> str:
    low = message.lower()
    for clue, reason in _REASONS:
        if clue in low:
            return reason
    detail = re.sub(r"^ERROR:\s*(\[[^\]]*\]\s*[\w-]+:\s*)?", "", message.strip())
    return f"The video could not be downloaded: {detail[:200]}"


def pick_captions(info: dict) -> tuple[str, bool] | None:
    """(language, automatic) for the best English captions: written ones first, then automatic ones."""
    for langs, automatic, first in ((info.get("subtitles") or {}, False, ("en",)),
                                    (info.get("automatic_captions") or {}, True, ("en-orig", "en"))):
        for lang in first:
            if lang in langs:
                return lang, automatic
        for lang in sorted(langs):
            if lang.lower().startswith(("en-", "en_")):
                return lang, automatic
    return None


# Captions to a transcript.

_TIME = r"(?:(\d+):)?(\d{1,2}):(\d{2})\.(\d{3})"
_CUE = re.compile(rf"^\s*{_TIME}\s+-->\s+{_TIME}")
_TAG = re.compile(r"<[^>]*>")


def _seconds(h: str | None, m: str, s: str, ms: str) -> float:
    return round(int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000, 3)


def vtt_to_segments(text: str) -> list[Segment]:
    """Caption cues as (start s, end s, words).

    Automatic captions roll: each cue repeats the line before it beside the new words, and short
    in-between cues repeat it again. Only words not in the previous cue are kept, so each line appears once.
    """
    cues: list[tuple[float, float, list[str]]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        timing = _CUE.match(line)
        if timing:
            g = timing.groups()
            current = []
            cues.append((_seconds(*g[:4]), _seconds(*g[4:]), current))
        elif line == "":
            current = None                       # a blank line ends a cue; a line holding a space does not
        elif current is not None:
            words = html.unescape(_TAG.sub("", line)).strip()
            if words:
                current.append(words)
    segments: list[Segment] = []
    previous: list[str] = []
    for start, end, lines in cues:
        new = [line for line in lines if line not in previous]
        if new:
            segments.append((start, end, " ".join(new)))
        previous = lines
    return segments


# Preparing the video.

def ffmpeg_small_args(src: Path | str, dst: Path | str) -> list[str]:
    return ["-y", "-i", str(src), "-vf", f"scale={SMALL_WIDTH}:-2,fps=2", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "28", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "32k", "-ac", "1",
            "-movflags", "+faststart", str(dst)]


def ffmpeg_frames_args(src: Path | str, frames_dir: Path | str, *, every_s: float = 30) -> list[str]:
    """Still frames at scene changes, plus the first frame and one at least every `every_s` seconds."""
    pick = f"select='gt(scene,{SCENE})+isnan(prev_selected_t)+gte(t-prev_selected_t,{every_s:g})'"
    return ["-y", "-i", str(src), "-vf", f"{pick},showinfo,scale={SMALL_WIDTH}:-2", "-fps_mode", "vfr",
            str(Path(frames_dir) / "frame_%04d.png")]


def ffmpeg_audio_args(src: Path | str, dst: Path | str) -> list[str]:
    return ["-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)]


def thin(items: Sequence[T], n: int) -> list[T]:
    """At most n items, spread evenly, keeping the first and the last."""
    if len(items) <= n:
        return list(items)
    if n == 1:
        return [items[0]]
    return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)]


def prepare(fetched: Fetched, client: MetaClient | None, *, workdir: Path | None = None) -> Prepared:
    work = Path(workdir) if workdir is not None else fetched.video.parent
    work.mkdir(parents=True, exist_ok=True)
    small = work / "small.mp4"
    _ffmpeg(ffmpeg_small_args(fetched.video, small), "make the small copy")
    frames = _frames(fetched.video, work / "frames", fetched.info.length_s)
    return Prepared(small, frames, _transcript(fetched, client, work))


def _ffmpeg(args: list[str], what: str) -> str:
    """Run ffmpeg; returns what it wrote to stderr (its log)."""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    done = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", creationflags=flags)
    if done.returncode != 0:
        last = (done.stderr.strip().splitlines() or ["no message"])[-1]
        raise VideoError(f"ffmpeg could not {what}: {last[:200]}")
    return done.stderr


def _frames(src: Path, frames_dir: Path, length_s: int) -> list[tuple[float, Path]]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("frame_*.png"):
        old.unlink()
    every = max(1.0, min(30.0, length_s / 30))
    log = _ffmpeg(ffmpeg_frames_args(src, frames_dir, every_s=every), "pull still frames")
    times = [round(float(t), 3) for t in re.findall(r"Parsed_showinfo.*?pts_time:\s*([0-9.]+)", log)]
    pairs = list(zip(times, sorted(frames_dir.glob("frame_*.png"))))
    kept = thin(pairs, MAX_FRAMES)
    for _, path in set(pairs) - set(kept):
        path.unlink()
    return kept


def _transcript(fetched: Fetched, client: MetaClient | None, work: Path) -> list[Segment]:
    if fetched.captions is not None:
        segments = vtt_to_segments(fetched.captions.read_text(encoding="utf-8", errors="replace"))
        if segments:
            return segments
    if client is None:
        return []
    audio = work / "audio.wav"
    try:
        _ffmpeg(ffmpeg_audio_args(fetched.video, audio), "take out the sound")
    except VideoError as exc:
        if "does not contain any stream" in str(exc) or "matches no streams" in str(exc):
            return []                            # a silent screen recording has nothing to transcribe
        raise
    return client.transcribe(audio, label=f"transcribe_{fetched.info.id}").segments
