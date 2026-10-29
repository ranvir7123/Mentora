"""Live check: get one real tutorial and prepare it.

    <python> probes\\meta_video.py <video link>

Downloads into recordings/<video id>/, then prints the title, creator, licence, length, how many
frames were pulled and the first transcript lines. Calls Meta only when the video has no English
captions (Muse Voice Transcribe), and only when the key is saved.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.factory.video import VideoError, fetch, prepare, settle  # noqa: E402
from app.meta.client import MetaClient, MetaError  # noqa: E402
from app.meta.key import find_key  # noqa: E402


def main(url: str) -> int:
    recordings = ROOT / "recordings"
    recordings.mkdir(exist_ok=True)
    incoming = Path(tempfile.mkdtemp(prefix="incoming-", dir=recordings))
    try:
        got = fetch(url, incoming)
        fetched = settle(got, recordings / got.info.id)
    except VideoError as exc:
        shutil.rmtree(incoming, ignore_errors=True)
        print(f"refused: {exc}")
        return 1
    i = fetched.info
    print(f"title:    {i.title}")
    print(f"creator:  {i.creator} ({i.channel_url})")
    print(f"licence:  {i.licence}")
    print(f"length:   {i.length_s} s")
    print(f"captions: {fetched.captions.name if fetched.captions else 'none'}")
    _key, where = find_key()
    client = MetaClient() if where != "missing" else None
    try:
        prepared = prepare(fetched, client)
    except (VideoError, MetaError) as exc:
        print(f"prepare failed: {exc}")
        return 1
    size_mb = prepared.small_mp4.stat().st_size / 1e6
    print(f"small:    {prepared.small_mp4.relative_to(ROOT)} ({size_mb:.1f} MB)")
    print(f"frames:   {len(prepared.frames)} at {', '.join(f'{t:g}' for t, _ in prepared.frames[:12])}"
          f"{' ...' if len(prepared.frames) > 12 else ''}")
    print(f"transcript lines: {len(prepared.transcript)}")
    for start, end, words in prepared.transcript[:5]:
        print(f"  {start:7.2f}-{end:7.2f}  {words}")
    if client is not None:
        print(f"Meta spend so far: ${client.spent():.4f}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
