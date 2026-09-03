"""PyInstaller runtime hook: tolerate missing dist-info in the frozen app.

diffusers/transformers call importlib.metadata.version() during import.
Prefer real metadata via copy_metadata() in the .spec; this is a safety net.

Important: on Python 3.12+, metadata.version() is implemented via
metadata.distribution(). Patch only through the *original* distribution
lookup to avoid RecursionError.
"""

from __future__ import annotations

import sys


def _install() -> None:
    if not getattr(sys, "frozen", False):
        return

    import importlib.metadata as md

    _orig_distribution = md.distribution

    _FALLBACKS = {
        "requests": "2.32.0",
        "urllib3": "2.0.0",
        "charset-normalizer": "3.0.0",
        "idna": "3.0",
        "certifi": "2024.0.0",
        "filelock": "3.0.0",
        "numpy": "1.26.0",
        "tqdm": "4.66.0",
        "regex": "2024.0.0",
        "packaging": "24.0",
        "pyyaml": "6.0",
        "tokenizers": "0.20.0",
        "huggingface-hub": "0.25.0",
        "safetensors": "0.4.0",
        "accelerate": "0.30.0",
        "diffusers": "0.29.0",
        "transformers": "4.44.0",
        "torch": "2.0.0",
    }

    def _fallback_version(distribution_name: str) -> str | None:
        names = {
            distribution_name,
            distribution_name.replace("_", "-"),
            distribution_name.replace("-", "_"),
            distribution_name.lower(),
            distribution_name.replace("_", "-").lower(),
        }
        for name in names:
            if name in _FALLBACKS:
                return _FALLBACKS[name]
        key = distribution_name.replace("_", "-").lower()
        for k, v in _FALLBACKS.items():
            if k.replace("_", "-").lower() == key:
                return v
        return None

    class _FakeDist:
        def __init__(self, name: str, ver: str):
            self.version = ver
            self.metadata = {"Name": name, "Version": ver}

        def read_text(self, filename: str) -> str | None:  # noqa: ARG002
            return None

    def distribution(distribution_name: str):  # type: ignore[no-redef]
        try:
            return _orig_distribution(distribution_name)
        except md.PackageNotFoundError:
            ver = _fallback_version(distribution_name)
            if ver is None:
                raise
            return _FakeDist(distribution_name, ver)

    def version(distribution_name: str) -> str:  # type: ignore[no-redef]
        return distribution(distribution_name).version

    md.distribution = distribution  # type: ignore[assignment]
    md.version = version  # type: ignore[assignment]


_install()
