"""Text -> calm speech audio file, with Piper (free, open source, runs offline on the laptop).

Piper is a small neural text-to-speech model. Each voice is one .onnx file (~60-120 MB)
in voices/. Nothing is sent to the internet, and there is no account or API key.

What makes it "calm":
  - length_scale > 1 stretches every sound, so she speaks a bit slower
  - a pause between sentences, so each instruction can land
  - a soft two-note chime first, so she notices before the words start
"""
import hashlib
import math
import os
import shutil
import struct
import subprocess
import wave

from piper import PiperVoice, SynthesisConfig

HERE = os.path.dirname(os.path.abspath(__file__))
VOICES = os.path.join(HERE, "voices")
CACHE = os.path.join(HERE, "cache")

DEFAULT_VOICE = os.environ.get("SQUINT_VOICE", "en_US-hfc_female-medium")
SLOWER = 1.15            # 1.0 = normal speed, 1.15 = 15% slower
SENTENCE_PAUSE = 0.45    # seconds of silence between sentences

_loaded = {}


def load(name=DEFAULT_VOICE):
    if name not in _loaded:
        path = os.path.join(VOICES, name + ".onnx")
        if not os.path.exists(path):
            raise FileNotFoundError(f"voice '{name}' not found in {VOICES}: run ./get_voices.sh")
        _loaded[name] = PiperVoice.load(path)
    return _loaded[name]


def chime(rate, seconds=0.9):
    """Two soft notes (E5 then C5) with a slow fade, as 16-bit samples."""
    out = []
    for f0, start in ((659.25, 0.0), (523.25, 0.32)):
        n0, n = int(start * rate), int(seconds * rate)
        while len(out) < n0 + n:
            out.append(0.0)
        for i in range(n):
            t = i / rate
            env = min(1.0, t / 0.02) * math.exp(-4.0 * t)          # quick soft attack, gentle decay
            out[n0 + i] += 0.18 * env * math.sin(2 * math.pi * f0 * t)
    return [int(max(-1, min(1, s)) * 32767) for s in out]


def synth(text, voice=DEFAULT_VOICE, with_chime=True):
    """Return the path of an audio file saying `text`. Same text + voice -> same file (cached)."""
    key = hashlib.sha1(f"{voice}|{SLOWER}|{SENTENCE_PAUSE}|{with_chime}|{text}".encode()).hexdigest()[:16]
    os.makedirs(CACHE, exist_ok=True)
    wav_path = os.path.join(CACHE, key + ".wav")
    m4a_path = os.path.join(CACHE, key + ".m4a")
    if os.path.exists(m4a_path):
        return m4a_path
    if not os.path.exists(wav_path):
        v = load(voice)
        cfg = SynthesisConfig(length_scale=SLOWER)
        rate = v.config.sample_rate
        pause = b"\x00\x00" * int(SENTENCE_PAUSE * rate)
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            if with_chime:
                w.writeframes(struct.pack(f"<{len(c := chime(rate))}h", *c) + pause)
            for chunk in v.synthesize(text, syn_config=cfg):      # one chunk per sentence
                w.writeframes(chunk.audio_int16_bytes + pause)
    # The Nest plays WAV, but AAC (.m4a) is ~10x smaller, so it starts faster over Wi-Fi.
    # afconvert ships with macOS; elsewhere we just use the WAV.
    # Piper makes 22.05 kHz audio; AAC at 96 kbps needs 44.1 kHz, so afconvert resamples too.
    if shutil.which("afconvert"):
        r = subprocess.run(["afconvert", "-f", "m4af", "-d", "aac@44100", "-b", "96000", wav_path, m4a_path],
                           capture_output=True)
        if r.returncode == 0:
            return m4a_path
    return wav_path


def duration(path):
    """Length in seconds (for the WAV next to an .m4a)."""
    wav = os.path.splitext(path)[0] + ".wav"
    with wave.open(wav) as w:
        return w.getnframes() / w.getframerate()


def available():
    return sorted(f[:-5] for f in os.listdir(VOICES) if f.endswith(".onnx")) if os.path.isdir(VOICES) else []
