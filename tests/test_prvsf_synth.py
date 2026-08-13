"""Batch narration synthesis.

The model load is per-process and costs ~0.9 s, so a per-chunk shell-out
wastes about a minute on a sixty-observation walk. These tests cover the
chunk plan and the encode; the Kokoro run itself needs weights and is
skipped without them.
"""

import base64
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "pr-voice-review-single-file"
sys.path.insert(0, str(SKILL))

import synth  # noqa: E402


def test_chunks_are_keyed_by_segment_and_observation():
    segments = [
        {"speech": "overview", "notes": []},
        {"speech": "file intro", "notes": [{"speech": "first point"}, {"text": "silent card"}]},
    ]
    assert synth.plan_chunks(segments) == [
        ("0:0", "overview"),
        ("1:0", "file intro"),
        ("1:1", "first point"),
    ]


def test_plan_chunks_skips_empty_speech():
    assert synth.plan_chunks([{"speech": "", "notes": []}]) == []


def test_plan_chunks_numbers_notes_past_silent_ones():
    """A silent card still occupies an index the client counts."""
    segments = [{"speech": "a", "notes": [{"text": "silent"}, {"speech": "voiced"}]}]
    assert synth.plan_chunks(segments) == [("0:0", "a"), ("0:2", "voiced")]


def test_plan_chunks_treats_whitespace_only_speech_as_silent():
    assert synth.plan_chunks([{"speech": "   \n ", "notes": []}]) == []


def test_plan_chunks_handles_a_segment_with_no_notes_key():
    assert synth.plan_chunks([{"speech": "just me"}]) == [("0:0", "just me")]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_encode_mp3_produces_small_mono_base64(tmp_path):
    wav = tmp_path / "s.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-ar", "24000", "-ac", "1", str(wav)],
        check=True,
    )
    b64 = synth.encode_mp3(wav)
    raw = base64.b64decode(b64)
    assert raw[:2] in (b"\xff\xfb", b"\xff\xf3", b"ID"), "not an MP3 frame"
    assert len(raw) < 6000, "1 s at 24 kbps should be ~3 KB"
