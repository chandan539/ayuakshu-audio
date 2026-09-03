# AYUAKSHU Audio — build history (Phases 1–7)

Current setup and model-download instructions: [SETUP.md](SETUP.md). Product README: [../README.md](../README.md).

# AYUAKSHU Audio

Fully offline Mac desktop app for local voice cloning + Hindi/English TTS.

> **Current status: PHASE 7 COMPLETE — offline QA passed.**  
> Product name: **AYUAKSHU Audio** (bundle id `com.ayuakshu.audio`).

## Phase 7 results (2026-09-03)

| Item | Result |
|------|--------|
| Harness | `./scripts/test_offline.sh` / `npm run test:offline` |
| Network guard | Non-loopback `socket.connect` blocked during QA |
| Pytest | **25 passed** |
| App bundle | `dist/OfflineVoice.app` present; **no** model weights inside |
| Hindi | `outputs/phase7_hi.wav` + `.mp3` |
| English | `outputs/phase7_en.wav` + `.mp3` |
| Network audit | `scripts/network_audit.sh` → **0 critical** cloud/telemetry SDKs |
| Docs | `docs/CLEAN_INSTALL.md`, `docs/UNINSTALL.md` |
| Bugfix | SQLite job-queue locking + WAL (API/worker race) |

```bash
./scripts/test_offline.sh
# or
npm run test:offline
```

## Phase 6 results (2026-09-03)

| Item | Result |
|------|--------|
| Backend sidecar | PyInstaller **onedir** → `src-tauri/resources/backend/offlinevoice-backend/` (~860 MB; no model weights) |
| Tauri release | Spawns bundled `offlinevoice-backend`; data under `~/Library/Application Support/OfflineVoice` |
| Artifacts | `dist/OfflineVoice.app` (~1.3 GB), `dist/OfflineVoice.dmg` (~479 MB) — aarch64 only |
| Models in DMG | **None** — ship `OfflineVoice-Models` separately |
| Bundle ID | `com.offlinevoice.desktop` |
| Signing / notarize | Optional via `OFFLINEVOICE_SIGN_IDENTITY` / `OFFLINEVOICE_NOTARY_PROFILE` |

```bash
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:$PATH"

# Full production build (bundles backend + app + DMG)
./scripts/build_dmg.sh

# Reuse an existing backend bundle
SKIP_BUNDLE=1 ./scripts/build_dmg.sh

# Optional signing / notarization
export OFFLINEVOICE_SIGN_IDENTITY="Developer ID Application: …"
export OFFLINEVOICE_NOTARY_PROFILE="…"
./scripts/sign_mac.sh dist/OfflineVoice.app
./scripts/notarize_mac.sh dist/OfflineVoice.dmg
```

## Phase 5 results (2026-09-03)

| Item | Result |
|------|--------|
| Detection / validation | Required chatterbox files checked; missing files reported |
| Offline package | `OfflineVoice-Models/` + `manifest.json` (+ optional `extras/pkuseg`) |
| Install API | `POST /models/install` **local package only** — never auto-downloads |
| First-run wizard | Shown when model missing; Install / Skip for now |
| Models screen | Status, size, path validation, local install |
| Pack script | `backend/scripts/pack_offline_models.py` |
| Tests | **17 passed** (Phase 5 + API) |

```bash
# Build USB/air-gap package from installed weights
backend/.venv/bin/python backend/scripts/pack_offline_models.py \
  --out dist/OfflineVoice-Models

# Install on another Mac (no Internet)
backend/.venv/bin/python backend/scripts/install_chatterbox_model.py \
  --from-local dist/OfflineVoice-Models
```

## Phase 4 results (2026-09-03)

| Item | Result |
|------|--------|
| Desktop shell | **Tauri 2** + React + TypeScript + Vite |
| Backend sidecar | Rust launches local Python FastAPI on `127.0.0.1` (ephemeral port) |
| Port discovery | `get_backend_info` / endpoint file under app data cache |
| UI | Sidebar: TTS, Projects, Voices, Models, Settings, Privacy |
| TTS screen | Voice/language selectors, editor, progress, play/export via local API |
| Offline fonts | System fonts only (no Google Fonts CDN) |
| Verified | `npm run tauri:dev` → Vite + backend ready + `GET /health` **200** |

```bash
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:$PATH"
npm run tauri:dev
```

Browser-only UI (no Tauri window):

```bash
./scripts/dev_ui.sh
```

## Phase 3 results (2026-09-03)

| Item | Result |
|------|--------|
| API | FastAPI on **127.0.0.1** only (ephemeral port) |
| DB | SQLite `database/app.sqlite` (voices, projects, jobs, chunks, settings) |
| Jobs | Background worker + progress + cancel + resume after interrupt |
| Voices / Projects | Local CRUD; audio files on disk (not SQLite blobs) |
| Models | Status endpoint; no silent downloads; local-package install only when offline |
| Smoke test | `test_backend.py` → `outputs/phase3_hi.wav` + `.mp3` |
| Unit tests | **18 passed** (Phase 2 + 3) |

```bash
# API unit tests
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -v

# End-to-end job smoke test
backend/.venv/bin/python test_backend.py

# Run server (writes port to Application Support cache)
./scripts/run_backend.sh
```

## Phase 2 results (2026-09-03)

| Item | Result |
|------|--------|
| Preprocess | decode → mono → 24 kHz → loudness normalize → trim silence |
| Validation | advisory quality report (does not hard-reject usable clips) |
| Chunking | paragraph → sentence → clause → word; pause markers `[pause:1s]` |
| Pronunciation | simple dictionary replace (e.g. SUBHAG → सुभाग) |
| Join | linear crossfade + pause silence + final peak normalize |
| Export | WAV (PCM16) + MP3 via **lameenc** (afconvert cannot encode MP3 here) |
| Hindi long | `outputs/hindi_long.wav` / `.mp3` — ~18.4 s |
| English long | `outputs/english_long.wav` / `.mp3` — ~17.4 s |
| Unit tests | `pytest backend/tests/test_audio_phase2.py` — **8 passed** |

```bash
backend/.venv/bin/python test_audio_pipeline.py
```

## Phase 1 results (2026-09-03)

| Item | Result |
|------|--------|
| TTS engine | **Chatterbox Multilingual** (`chatterbox-tts==0.1.7`, Resemble AI) |
| Checkpoint | Multilingual V2 (`t3_mtl23ls_v2.safetensors`) from `ResembleAI/chatterbox` |
| Device | **MPS** (Apple M4) |
| Hindi WAV | `outputs/hindi.wav` — 24 kHz mono, ~6.5 s, 307 KB |
| English WAV | `outputs/english.wav` — 24 kHz mono, ~5.4 s, 252 KB |
| Cloud API | **None** — local inference only (`HF_HUB_OFFLINE=1`) |
| Model license | Code/package: **MIT** (Resemble). Weights on HF — do not embed in DMG until redistribution terms are confirmed for your release. |
| Model install | Explicit installer only: `backend/scripts/install_chatterbox_model.py` (+ `--from-local` for air-gap) |
| Supported Mac (MVP) | **aarch64-apple-darwin** (Apple Silicon). Intel later. |

### System detected

| Item | Value |
|------|-------|
| Chip | Apple M4 (arm64) |
| RAM | 16 GB |
| Disk free | ~68 GB |
| Python | 3.14.3 (venv in `backend/.venv`) |
| Node / npm | Not installed (needed Phase 4+) |
| Rust / Cargo | Not installed (needed Phase 4+) |
| FFmpeg | Not installed (Phase 1 used macOS `afconvert`) |

### Dependency problems found & mitigated

1. **setuptools ≥81** removes `pkg_resources` → breaks `resemble-perth`. Pinned `setuptools>=70,<81`.
2. **torchaudio 2.14** `save()` requires `torchcodec` → write WAV with **soundfile** instead.
3. **Cangjie JSON** (Chinese only) tries Hugging Face Hub → patched to read from local model dir when offline.
4. **spacy-pkuseg** first load downloaded `spacy_ontonotes` into `~/.pkuseg/` — must be vendored into the offline model package for air-gapped machines (Phase 5).
5. Installed PyPI package exposes **V2 multilingual** API (not `t3_model="v3"` yet). Hindi (`hi`) + English (`en`) are supported.

## Phase 1 goal

Prove local (no cloud API) Hindi + English speech generation with voice cloning via **Chatterbox Multilingual**.

## TTS engine selected

**Chatterbox Multilingual** (`chatterbox-tts`, Resemble AI)

- Zero-shot voice cloning from a short reference clip
- Hindi (`hi`) + English (`en`) supported
- Runs locally on MPS (Apple Silicon) or CPU
- MIT-licensed package; PerTh watermark embedded in outputs
- Models are **not** bundled in the future `.dmg`; they install once into a local models directory

### Model installation method

```bash
# One-time (Internet allowed ONLY here)
backend/.venv/bin/python backend/scripts/install_chatterbox_model.py

# Air-gapped alternative
backend/.venv/bin/python backend/scripts/install_chatterbox_model.py \
  --from-local /path/to/OfflineVoice-Models
```

Weights land in:

```text
offline-voice/models/tts/chatterbox/   (~3.0 GB)
```

(Production app will use `~/Library/Application Support/OfflineVoice/models/`.)

Generation **never** auto-downloads. If weights are missing → `MODEL_NOT_INSTALLED`.

## Quick start (Phase 1)

```bash
cd offline-voice
chmod +x scripts/setup_dev.sh
./scripts/setup_dev.sh
python backend/scripts/install_chatterbox_model.py
python test_tts.py
```

Expected outputs:

```text
outputs/hindi.wav
outputs/english.wav
```

## Project layout (Phase 1–4)

```text
offline-voice/
├── frontend/                 # React + Vite UI
├── src-tauri/                # Tauri shell + backend process manager
├── backend/                  # FastAPI + TTS + audio pipeline
├── models/tts/chatterbox/
├── scripts/
│   ├── setup_dev.sh
│   ├── run_backend.sh
│   └── dev_ui.sh
├── package.json              # npm run tauri:dev
└── test_*.py
```

## What is intentionally NOT built yet

- Full Apple Developer ID notarization (needs paid Apple cert — see `docs/SIGNING.md`; ad-hoc sign works locally)
- Intel Mac universal binary

Whisper STT and Record Voice are implemented (local-only).

## Deployment architecture (locked in)

```text
OfflineVoice.dmg  →  OfflineVoice.app (Tauri + React + Python runtime + FFmpeg)
                         │
                         └── first-run / USB model package
                                 ↓
                 ~/Library/Application Support/OfflineVoice/models/
```

No multi-GB model weights inside the DMG for v1.
