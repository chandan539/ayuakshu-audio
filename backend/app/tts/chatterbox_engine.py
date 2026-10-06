"""Chatterbox Multilingual TTS engine (local / offline).

Model weights live under the application models directory.
Generation never triggers a network download.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

import torch

from .base import TTSEngine
from .errors import ModelNotInstalledError

logger = logging.getLogger(__name__)

# Hugging Face repo used only by the explicit model installer (not by generate()).
CHATTERBOX_REPO_ID = "ResembleAI/chatterbox"

# Files required for multilingual V3 inference via from_local().
# Exact filenames may vary by package version; is_available() checks flexibly.
REQUIRED_MARKERS = (
    "grapheme_mtl_merged_expanded_v1.json",
)


def detect_device() -> str:
    """Prefer Apple Silicon MPS, then CUDA, else CPU."""
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class ChatterboxEngine(TTSEngine):
    name = "chatterbox"
    # Short chunks keep peak MPS memory lower and avoid "stuck" multi-minute chunks.
    default_chunk_chars = 360

    def __init__(self, model_dir: str | Path, device: Optional[str] = None):
        self.model_dir = Path(model_dir).expanduser().resolve()
        self.device = device or detect_device()
        self._model = None
        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self._conds_key: tuple[str, int] | None = None
        self._warmed = False
        self._loading = False
        self.clone_mode = "fast"
        self.temperature = 0.61
        self.exaggeration = 0.5
        self.cfg_weight = 0.47
        self.repetition_penalty = 1.29
        # None = not probed yet; True/False after first turbo attempt.
        self._turbo_ok: bool | None = None
        self.last_infer_sec: float = 0.0
        self.last_path: str = "unknown"

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def is_loading(self) -> bool:
        return self._loading

    @property
    def is_warmed(self) -> bool:
        return self._warmed

    def runtime_info(self) -> dict:
        return {
            "tts_device": self.device,
            "tts_fast_path": self._turbo_ok,
            "clone_mode": getattr(self, "clone_mode", "fast"),
        }

    def is_available(self) -> bool:
        if not self.model_dir.is_dir():
            return False
        # Accept either V3 or V2 multilingual checkpoints once present locally.
        has_tokenizer = (self.model_dir / "grapheme_mtl_merged_expanded_v1.json").exists()
        has_t3 = any(self.model_dir.glob("t3_mtl*.safetensors")) or any(
            self.model_dir.glob("t3*.safetensors")
        )
        has_s3 = (self.model_dir / "s3gen.pt").exists() or any(
            self.model_dir.glob("s3gen*.pt")
        ) or any(self.model_dir.glob("s3gen*.safetensors"))
        has_ve = (self.model_dir / "ve.pt").exists() or any(self.model_dir.glob("ve*.pt"))
        return has_tokenizer and has_t3 and has_s3 and has_ve

    def load(self) -> None:
        with self._load_lock:
            if self._model is not None:
                return
            if not self.is_available():
                raise ModelNotInstalledError(
                    self.name,
                    hint=f"expected local weights in {self.model_dir}",
                )

            self._loading = True
            try:
                # Force offline huggingface hub behavior during load.
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

                self._ensure_perth_watermarker()
                self._patch_hf_hub_to_local_model_dir()

                from chatterbox.mtl_tts import ChatterboxMultilingualTTS

                logger.info("Loading Chatterbox from %s on %s", self.model_dir, self.device)
                if self.device == "cpu":
                    logger.warning(
                        "Chatterbox is on CPU — generation will be very slow. "
                        "Apple Silicon MPS should be used on this Mac."
                    )
                model = ChatterboxMultilingualTTS.from_local(
                    str(self.model_dir),
                    self.device,
                )
                # Belt-and-suspenders: keep watermarker as no-op after construct.
                try:
                    import perth

                    model.watermarker = perth.DummyWatermarker()
                except Exception:
                    pass
                self._model = model
                self._conds_key = None
                logger.info("Chatterbox weights loaded")
            finally:
                self._loading = False

    def warm_up(self) -> None:
        """Load weights and run a tiny inference so the first user job is faster."""
        if self._warmed:
            return
        if not self.is_available():
            return
        self.load()
        assert self._model is not None
        with self._infer_lock:
            if self._warmed:
                return
            try:
                # Builtin speaker conditionals ship with the package (conds.pt).
                if self._model.conds is None:
                    logger.info("Skipping inference warm-up (no builtin conditionals)")
                    self._warmed = True
                    return
                logger.info("Warming Chatterbox with turbo path on %s…", self.device)
                _ = self._fast_generate("Hi.", "en")
                self._warmed = True
                logger.info(
                    "Chatterbox warm-up complete device=%s turbo=%s",
                    self.device,
                    self._turbo_ok,
                )
            except Exception:
                logger.exception("Chatterbox warm-up failed (generation will still work)")
                # Still mark warmed so we don't loop forever on a hard failure path.
                self._warmed = True

    def set_delivery(
        self,
        *,
        exaggeration: float,
        temperature: float,
        cfg_weight: float,
        repetition_penalty: float,
    ) -> None:
        self.exaggeration = float(exaggeration)
        self.temperature = float(temperature)
        self.cfg_weight = float(cfg_weight)
        self.repetition_penalty = float(repetition_penalty)
        self._apply_emotion()

    def _apply_emotion(self) -> None:
        """Update emotion on the cached clone without rebuilding the speaker embedding."""
        model = self._model
        if model is None or getattr(model, "conds", None) is None:
            return
        try:
            import torch
            from chatterbox.models.t3.modules.cond_enc import T3Cond
        except Exception:
            return
        current = model.conds.t3
        try:
            current_value = float(current.emotion_adv[0, 0, 0].item())
        except Exception:
            current_value = None
        if current_value is not None and abs(current_value - self.exaggeration) < 0.02:
            return
        model.conds.t3 = T3Cond(
            speaker_emb=current.speaker_emb,
            cond_prompt_speech_tokens=current.cond_prompt_speech_tokens,
            emotion_adv=self.exaggeration * torch.ones(1, 1, 1),
        ).to(device=model.device)

    def prepare_voice(self, reference_audio: str, *, exaggeration: float | None = None) -> None:
        """Cache speaker conditionals for a reference clip (once per file)."""
        self.load()
        assert self._model is not None
        if exaggeration is not None:
            self.exaggeration = float(exaggeration)
        ref = Path(reference_audio).expanduser().resolve()
        if not ref.is_file():
            raise FileNotFoundError(f"Reference audio not found: {ref}")
        key = (str(ref), int(ref.stat().st_mtime_ns))
        with self._infer_lock:
            if self._conds_key == key and self._model.conds is not None:
                self._apply_emotion()
                return
            self._model.prepare_conditionals(str(ref), exaggeration=self.exaggeration)
            self._conds_key = key
            self._apply_emotion()

    def generate(
        self,
        text: str,
        language: str,
        reference_audio: Optional[str],
        output_path: str,
    ) -> Path:
        if not self.is_available():
            raise ModelNotInstalledError(
                self.name,
                hint=f"expected local weights in {self.model_dir}",
            )
        self.load()
        assert self._model is not None

        language_id = language.lower().strip()
        out = Path(output_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        text = (text or "").strip()
        if not text:
            raise ValueError("Empty text chunk")

        try:
            return self._generate_to_path(text, language_id, reference_audio, out)
        except RuntimeError as exc:
            if not self._is_oom(exc):
                raise
            logger.warning("MPS/CUDA OOM on chunk (%s chars); releasing cache and splitting", len(text))
            self.release_memory()
            if len(text) < 80:
                raise RuntimeError(
                    "Out of memory generating speech. Close other apps, restart AYUAKSHU Audio, "
                    "and use shorter text (Settings → Max chunk characters ≈ 220)."
                ) from exc
            return self._generate_split(text, language_id, reference_audio, out)

    def _generate_split(
        self,
        text: str,
        language_id: str,
        reference_audio: Optional[str],
        out: Path,
    ) -> Path:
        """Split an oversized/OOM chunk into halves, generate, then concatenate WAVs."""
        import numpy as np
        import soundfile as sf

        mid = len(text) // 2
        split_at = text.rfind(" ", 0, mid)
        if split_at < 40:
            split_at = text.find(" ", mid)
        if split_at < 40:
            split_at = mid
        left, right = text[:split_at].strip(), text[split_at:].strip()
        if not left or not right:
            raise RuntimeError("Out of memory and could not split text further.")

        left_path = out.with_name(out.stem + "_a.wav")
        right_path = out.with_name(out.stem + "_b.wav")
        for part, path in ((left, left_path), (right, right_path)):
            try:
                self._generate_to_path(part, language_id, reference_audio, path)
            except RuntimeError as exc:
                if self._is_oom(exc) and len(part) >= 80:
                    self.release_memory()
                    self._generate_split(part, language_id, reference_audio, path)
                else:
                    raise
            self.release_memory()

        a, sr = sf.read(str(left_path), always_2d=True)
        b, sr2 = sf.read(str(right_path), always_2d=True)
        if sr != sr2:
            raise RuntimeError("Sample rate mismatch while joining OOM-split chunks")
        # Short silence between halves
        gap = np.zeros((int(sr * 0.12), a.shape[1]), dtype=a.dtype)
        joined = np.concatenate([a, gap, b], axis=0)
        sf.write(str(out), joined, sr, subtype="PCM_16")
        left_path.unlink(missing_ok=True)
        right_path.unlink(missing_ok=True)
        return out

    def _generate_to_path(
        self,
        text: str,
        language_id: str,
        reference_audio: Optional[str],
        out: Path,
    ) -> Path:
        assert self._model is not None
        t0 = time.perf_counter()
        used = "quality"
        with self._infer_lock:
            if reference_audio:
                ref = Path(reference_audio).expanduser().resolve()
                key = (str(ref), int(ref.stat().st_mtime_ns))
                if self._conds_key != key or self._model.conds is None:
                    self._model.prepare_conditionals(str(ref), exaggeration=self.exaggeration)
                    self._conds_key = key
                self._apply_emotion()
            elif self._model.conds is None:
                raise ValueError("reference_audio is required when no voice conditionals are loaded")

            if getattr(self, "clone_mode", "fast") == "quality":
                wav = self._model.generate(
                    text=text,
                    language_id=language_id,
                    audio_prompt_path=None,
                    exaggeration=self.exaggeration,
                    cfg_weight=self.cfg_weight,
                    temperature=self.temperature,
                    repetition_penalty=max(1.05, self.repetition_penalty),
                )
                used = "quality"
            else:
                wav = self._fast_generate(text, language_id)
                used = "turbo" if self._turbo_ok else "cfg-fallback"

        if hasattr(wav, "detach"):
            wav = wav.detach().cpu()
        if wav.ndim == 1:
            wav = wav.unsqueeze(0)

        import numpy as np
        import soundfile as sf

        from ..audio.merger import audio_too_short_for_text, trim_edge_silence

        audio = wav.numpy()
        if audio.ndim == 2 and audio.shape[0] <= 8:
            audio = np.transpose(audio, (1, 0))
        mono = audio.mean(axis=1) if audio.ndim == 2 else audio
        sr = int(self._model.sr)
        if audio_too_short_for_text(mono, sr, text) and used != "quality":
            logger.warning(
                "Chunk too short/silent (%d chars, %.2fs) — regenerating more conservatively",
                len(text),
                len(mono) / sr if sr else 0.0,
            )
            with self._infer_lock:
                wav = self._stable_generate(text, language_id)
            used = "stable-retry"
            if hasattr(wav, "detach"):
                wav = wav.detach().cpu()
            if wav.ndim == 1:
                wav = wav.unsqueeze(0)
            audio = wav.numpy()
            if audio.ndim == 2 and audio.shape[0] <= 8:
                audio = np.transpose(audio, (1, 0))
            mono = audio.mean(axis=1) if audio.ndim == 2 else audio

        mono = trim_edge_silence(mono, sr)
        sf.write(str(out), mono, sr, subtype="PCM_16")
        infer_sec = time.perf_counter() - t0
        self.last_infer_sec = infer_sec
        self.last_path = used
        audio_sec = float(len(mono) / sr) if sr else 0.0
        rtf = (infer_sec / audio_sec) if audio_sec > 0.05 else 0.0
        logger.info(
            "chunk path=%s device=%s chars=%d infer=%.2fs audio=%.2fs rtf=%.2fx",
            used,
            self.device,
            len(text),
            infer_sec,
            audio_sec,
            rtf,
        )
        return out

    def _fast_generate(self, text: str, language_id: str):
        """Hindi/English path that skips the slow CFG + 10-step vocoder loop.

        Official Chatterbox.generate() duplicates the batch for CFG and runs
        10 CFM steps. That is ~5–10× slower than needed. Fast mode uses
        single-batch turbo sampling and 2 vocoder steps (same idea as
        Chatterbox Turbo, kept multilingual).
        """
        import torch.nn.functional as F
        from chatterbox.models.s3tokenizer import drop_invalid_tokens
        from chatterbox.mtl_tts import punc_norm

        model = self._model
        assert model is not None

        text = punc_norm(text)
        text_tokens = model.tokenizer.text_to_tokens(
            text, language_id=language_id.lower() if language_id else None
        ).to(model.device)
        sot = model.t3.hp.start_text_token
        eot = model.t3.hp.stop_text_token
        text_tokens = F.pad(text_tokens, (1, 0), value=sot)
        text_tokens = F.pad(text_tokens, (0, 1), value=eot)

        # ~25 speech tokens/sec. Hindi syllables need more tokens than English chars.
        # Cap high enough that EOS can fire; too-low caps cut the line into silence.
        max_gen_len = min(1600, max(200, int(len(text) * 4.2) + 100))

        with torch.inference_mode():
            if self._turbo_ok is False:
                wav = self._cfg_fallback(text, language_id)
                return wav
            try:
                speech_tokens = model.t3.inference_turbo(
                    t3_cond=model.conds.t3,
                    text_tokens=text_tokens,
                    temperature=self.temperature,
                    top_k=1000,
                    top_p=0.9,
                    repetition_penalty=self.repetition_penalty,
                    max_gen_len=max_gen_len,
                )
                self._turbo_ok = True
            except (AttributeError, TypeError, RuntimeError) as exc:
                logger.exception("Turbo sampling failed once; later chunks use slower CFG path: %s", exc)
                self._turbo_ok = False
                return self._cfg_fallback(text, language_id)

            if speech_tokens.ndim == 2:
                speech_tokens = speech_tokens[0]
            speech_tokens = drop_invalid_tokens(speech_tokens)
            speech_tokens = speech_tokens.to(model.device)
            wav, _ = model.s3gen.inference(
                speech_tokens=speech_tokens,
                ref_dict=model.conds.gen,
                n_cfm_timesteps=4,
            )
        if hasattr(wav, "detach"):
            wav = wav.detach().cpu()
        return wav

    def _stable_generate(self, text: str, language_id: str):
        """One retry when turbo produced near-silence or a clipped line."""
        model = self._model
        assert model is not None
        return model.generate(
            text=text,
            language_id=language_id,
            audio_prompt_path=None,
            exaggeration=0.4,
            cfg_weight=0.3,
            temperature=0.6,
        )

    def _cfg_fallback(self, text: str, language_id: str):
        model = self._model
        assert model is not None
        return model.generate(
            text=text,
            language_id=language_id,
            audio_prompt_path=None,
            exaggeration=0.4,
            cfg_weight=0.0,
            temperature=0.7,
        )

    @staticmethod
    def _is_oom(exc: BaseException) -> bool:
        msg = str(exc).lower()
        return (
            "out of memory" in msg
            or "oom" in msg
            or "mps backend out of memory" in msg
            or isinstance(exc, torch.cuda.OutOfMemoryError)
        )

    def release_memory(self) -> None:
        """Free transient GPU/unified-memory caches between chunks."""
        import gc

        gc.collect()
        if self.device == "mps" and hasattr(torch, "mps"):
            try:
                torch.mps.empty_cache()
                if hasattr(torch.mps, "synchronize"):
                    torch.mps.synchronize()
            except Exception:
                pass
        elif self.device == "cuda" and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass

    @staticmethod
    def _ensure_perth_watermarker() -> None:
        """Use a no-op watermarker.

        Perth's real watermarker needs checkpoint files that are awkward in a
        frozen PyInstaller bundle and adds latency we do not need offline.
        """
        import perth

        perth.PerthImplicitWatermarker = perth.DummyWatermarker

    def _patch_hf_hub_to_local_model_dir(self) -> None:
        """Serve known sidecar files from the local model directory when offline."""
        import huggingface_hub

        model_dir = self.model_dir
        if getattr(huggingface_hub, "_offlinevoice_patched", False):
            return

        original = huggingface_hub.hf_hub_download

        def hf_hub_download(repo_id, filename, *args, **kwargs):
            local = model_dir / filename
            if local.is_file():
                return str(local)
            if os.environ.get("HF_HUB_OFFLINE") == "1":
                raise FileNotFoundError(
                    f"Offline mode: {filename} not found in {model_dir}"
                )
            return original(repo_id, filename, *args, **kwargs)

        huggingface_hub.hf_hub_download = hf_hub_download
        huggingface_hub._offlinevoice_patched = True

    def unload(self) -> None:
        with self._load_lock:
            with self._infer_lock:
                self._model = None
                self._conds_key = None
                self._warmed = False
                self._loading = False
        if self.device == "mps" and hasattr(torch, "mps"):
            try:
                torch.mps.empty_cache()
            except Exception:
                pass
