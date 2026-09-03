# AYUAKSHU Audio

Fully offline Mac desktop app for **local voice cloning** and **Hindi / English TTS**.

- **Bundle ID:** `com.ayuakshu.audio`
- **Stack:** Tauri 2 + React + local FastAPI/Python + Chatterbox Multilingual + Whisper
- **Target:** Apple Silicon only (`aarch64-apple-darwin`)
- **Network at runtime:** localhost API only. Speech never goes to a cloud TTS API.

This is a **private** repository: **source and build scripts only**. The ~3.5 GB `OfflineVoice-Models` pack is **not** in Git. Those files are third-party weights you download from Hugging Face and OpenAI.

**Full clone → models → run → USB → DMG:** **[docs/SETUP.md](docs/SETUP.md)**

---

## What GitHub contains

Included: frontend, backend, Tauri shell, installer scripts, tests, and docs.

**Not included** (too large, or regenerated locally):

| Path | Why it is omitted | How to get it |
|------|-------------------|---------------|
| `models/tts/chatterbox/` | Resemble AI weights (~3.2 GB) | [Hugging Face: ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox) via `install_chatterbox_model.py` |
| `models/whisper/small.pt` | OpenAI Whisper (~461 MB) | `install_whisper_model.py` |
| `dist/` (`.app` / `.dmg` / model pack) | 100 MB git file limit | `./scripts/build_dmg.sh` and `pack_offline_models.py` |
| `backend/.venv/`, `node_modules/`, PyInstaller bundle | Machine-local | `./scripts/setup_dev.sh` and `npm install` |

---

## Download the offline model files

Internet is required **once**. After this, keep Wi‑Fi off if you want; generation stays on device.

```bash
# 1) Python env
./scripts/setup_dev.sh

# 2) Chatterbox TTS + voice clone (Hugging Face)
backend/.venv/bin/python backend/scripts/install_chatterbox_model.py

# 3) Whisper STT (OpenAI)
backend/.venv/bin/python backend/scripts/install_whisper_model.py --size small
```

| File | Source |
|------|--------|
| `t3_mtl23ls_v2.safetensors`, `s3gen.pt`, `ve.pt`, … | https://huggingface.co/ResembleAI/chatterbox |
| `small.pt` | Official OpenAI Whisper checkpoints (URLs inside the Whisper package) |

Optional USB folder for machines with **no internet**:

```bash
backend/.venv/bin/python backend/scripts/pack_offline_models.py --out dist/OfflineVoice-Models
```

Then copy `dist/OfflineVoice-Models/` (the folder, not a 3.5 GB GitHub zip) onto an **exFAT** stick with `AYUAKSHU-Audio.dmg`. In the app: **Choose Offline Model Package** and select that folder.

Do not upload `OfflineVoice-Models.zip` to GitHub (over the 2 GB Release file limit, and redundant with Hugging Face).

---

## Quick start (after models)

```bash
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:$PATH"
npm install
npm --prefix frontend install
npm run tauri:dev
```

Build a DMG (models still not inside the disk image):

```bash
./scripts/build_dmg.sh
```

---

## Docs

| Doc | Contents |
|-----|----------|
| [docs/SETUP.md](docs/SETUP.md) | Clone, toolchain, **where to download models**, USB, run, build |
| [docs/SIGNING.md](docs/SIGNING.md) | Ad-hoc vs Developer ID + notarization |
| [docs/CLEAN_INSTALL.md](docs/CLEAN_INSTALL.md) | Fresh-Mac install checklist |
| [docs/UNINSTALL.md](docs/UNINSTALL.md) | Remove app + Application Support |
| [docs/BUILD_HISTORY.md](docs/BUILD_HISTORY.md) | Phase 1–7 engineering log |

Layout:

```text
frontend/          React + Vite UI
src-tauri/         Tauri 2 shell (spawns local backend)
backend/           FastAPI + Chatterbox + Whisper + jobs
scripts/           setup, bundle, DMG, sign, notarize
models/            empty placeholders — weights downloaded locally
```

Runtime data: `~/Library/Application Support/AYUAKSHU Audio/`

---

## License notes

Application source in this repo is yours to keep private.

Chatterbox package/code is MIT (Resemble). Whisper is MIT (OpenAI). **Weights** stay on their hosts; confirm redistribution terms before a public download page or App Store binary that embeds them.
