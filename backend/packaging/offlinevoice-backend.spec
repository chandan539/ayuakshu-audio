# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir bundle for OfflineVoice backend (aarch64-apple-darwin).
# Does NOT include multi-GB TTS model weights.

from PyInstaller.utils.hooks import copy_metadata

block_cipher = None

# diffusers/transformers call importlib.metadata.version() at import time.
# Without dist-info in the bundle, Chatterbox fails with PackageNotFoundError
# (commonly: "No package metadata was found for requests").
_METADATA_PACKAGES = [
    "requests",
    "urllib3",
    "charset-normalizer",
    "idna",
    "certifi",
    "filelock",
    "numpy",
    "diffusers",
    "transformers",
    "huggingface-hub",
    "tokenizers",
    "safetensors",
    "torch",
    "tqdm",
    "packaging",
    "PyYAML",
    "regex",
    "pillow",
    "scipy",
    "scikit-learn",
    "librosa",
    "soundfile",
    "einops",
    "chatterbox-tts",
    "perth",
]

datas = []
for _pkg in _METADATA_PACKAGES:
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass

a = Analysis(
    ["launch.py"],
    pathex=[".."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "app",
        "app.main",
        "app.api",
        "app.api.routes",
        "app.api.schemas",
        "app.audio",
        "app.audio.pipeline",
        "app.audio.chunker",
        "app.audio.export",
        "app.audio.merger",
        "app.audio.preprocess",
        "app.audio.validate",
        "app.audio.convert",
        "app.tts",
        "app.tts.chatterbox_engine",
        "app.tts.manager",
        "app.jobs.queue",
        "app.stt",
        "app.stt.whisper_engine",
        "whisper",
        "tiktoken",
        "app.services",
        "app.services.voices",
        "app.services.projects",
        "app.services.models",
        "app.services.model_package",
        "app.services.settings",
        "app.database",
        "chatterbox",
        "chatterbox.mtl_tts",
        "perth",
        "soundfile",
        "lameenc",
        "pyloudnorm",
        "librosa",
        "sklearn",
        "scipy",
        "numpy",
        "torchaudio",
        "safetensors",
        "einops",
        "conformer",
        "diffusers",
        "transformers",
        "huggingface_hub",
        # Required by diffusers dependency_versions_check
        "requests",
        "urllib3",
        "charset_normalizer",
        "idna",
        "certifi",
        "filelock",
        "packaging",
        "regex",
        "tqdm",
        "yaml",
        "tokenizers",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["runtime_hook_pkg_metadata.py"],
    excludes=[
        "gradio",
        "tkinter",
        "matplotlib.tests",
        "IPython",
        "notebook",
        "pytest",
        "PyQt5",
        "PySide6",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="offlinevoice-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="offlinevoice-backend",
)
