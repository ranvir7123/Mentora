"""Make the screens' five sounds as small WAV files in app/ui/sounds/.

One family: the same soft tone (a sine with a little of its second and third harmonics) with a gentle
start and a smooth fade, so nothing clicks or sounds harsh. Success rises; "not yet" is one soft low note.
Standard library only. Run: <py> probes/ui_make_sounds.py
"""
import math
import struct
import wave
from pathlib import Path

RATE = 44100
OUT = Path(__file__).resolve().parents[1] / "app" / "ui" / "sounds"
PEAK = 0.5                     # loudest sample, half of full scale, so the family sits quietly


def _note(freq, start, length, attack=0.006, gain=1.0, glide_to=None):
    """One soft note as (start sample, samples). It fades out over its whole length after the attack."""
    count = int(length * RATE)
    samples, phase = [], 0.0
    for i in range(count):
        t = i / RATE
        f = freq if glide_to is None else freq + (glide_to - freq) * (i / count)
        phase += 2 * math.pi * f / RATE
        tone = math.sin(phase) + 0.25 * math.sin(2 * phase) + 0.08 * math.sin(3 * phase)
        rise = min(1.0, t / attack)
        fall = (1 - i / count) ** 2.2
        samples.append(gain * tone * rise * fall)
    return int(start * RATE), samples


def _mix(notes, length):
    total = [0.0] * int(length * RATE)
    for first, samples in notes:
        for i, value in enumerate(samples):
            if first + i < len(total):
                total[first + i] += value
    top = max(abs(v) for v in total) or 1.0
    return [v / top * PEAK for v in total]


SOUNDS = {
    # A short soft tick for a routine button.
    "click": (0.09, [_note(1320, 0, 0.09, attack=0.002)]),
    # Two rising notes: a step done right.
    "right": (0.28, [_note(659.3, 0, 0.13), _note(987.8, 0.1, 0.18)]),
    # One soft low note with a slow start: not yet, never harsh.
    "not_yet": (0.22, [_note(329.6, 0, 0.22, attack=0.03, glide_to=311.1)]),
    # A quick upward hop for the mascot.
    "hop": (0.12, [_note(523.3, 0, 0.12, attack=0.004, glide_to=784.0)]),
    # A rising four-note chime: the lesson is finished.
    "complete": (0.48, [_note(523.3, 0, 0.22), _note(659.3, 0.08, 0.22), _note(784.0, 0.16, 0.24),
                        _note(1046.5, 0.24, 0.24)]),
}


def write(name, length, notes):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.wav"
    frames = b"".join(struct.pack("<h", int(v * 32767)) for v in _mix(notes, length))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(frames)
    return path


def main():
    for name, (length, notes) in SOUNDS.items():
        path = write(name, length, notes)
        with wave.open(str(path), "rb") as check:
            ms = check.getnframes() / check.getframerate() * 1000
        print(f"{name:9s} {ms:5.0f} ms  {path.stat().st_size:6d} bytes  {path}")


if __name__ == "__main__":
    main()
