"""Export final audio to WAV / MP3 (local only)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .convert import AudioToolError, find_ffmpeg

MP3_BITRATES = {128, 192, 256, 320}


def export_wav(
    audio: np.ndarray,
    sample_rate: int,
    output_path: str | Path,
) -> Path:
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2 and audio.shape[0] <= 8:
        audio = audio.T
    sf.write(str(out), audio, int(sample_rate), subtype="PCM_16")
    return out


def _encode_mp3_lameenc(
    audio: np.ndarray,
    sample_rate: int,
    output_path: Path,
    bitrate_kbps: int,
) -> Path:
    import lameenc

    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        # (samples, channels) or (channels, samples)
        if audio.shape[0] <= 8 and audio.shape[1] > audio.shape[0]:
            audio = audio.T
        channels = audio.shape[1]
        # Interleave float -> int16
        interleaved = np.clip(audio, -1.0, 1.0)
        pcm = (interleaved * 32767.0).astype(np.int16).reshape(-1).tobytes()
    else:
        channels = 1
        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(int(bitrate_kbps))
    encoder.set_in_sample_rate(int(sample_rate))
    encoder.set_channels(int(channels))
    encoder.set_quality(2)  # 0=best, 9=worst
    mp3_bytes = encoder.encode(pcm) + encoder.flush()
    output_path.write_bytes(mp3_bytes)
    if output_path.stat().st_size <= 0:
        raise AudioToolError("lameenc produced an empty MP3 file")
    return output_path


def export_mp3(
    wav_path: str | Path,
    output_path: str | Path,
    *,
    bitrate_kbps: int = 192,
) -> Path:
    """
    Encode MP3 from a WAV file using local tools only.

    Preference order: lameenc (bundled) → ffmpeg.
    macOS afconvert can decode MP3 but often cannot encode it.
    """
    if bitrate_kbps not in MP3_BITRATES:
        raise ValueError(f"bitrate_kbps must be one of {sorted(MP3_BITRATES)}")

    src = Path(wav_path).expanduser().resolve()
    dst = Path(output_path).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not src.is_file():
        raise FileNotFoundError(src)

    audio, sr = sf.read(str(src), always_2d=False)
    lame_err = "lameenc unavailable"
    try:
        return _encode_mp3_lameenc(np.asarray(audio, dtype=np.float32), int(sr), dst, bitrate_kbps)
    except ImportError:
        lame_err = "lameenc package not installed"
    except Exception as exc:
        lame_err = str(exc)

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(src),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            f"{bitrate_kbps}k",
            str(dst),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:
            return dst
        err = (proc.stderr or proc.stdout or "").strip()
        raise AudioToolError(f"MP3 export failed (ffmpeg): {err}")

    raise AudioToolError(
        f"MP3 export failed ({lame_err}). Install the lameenc package or FFmpeg."
    )
