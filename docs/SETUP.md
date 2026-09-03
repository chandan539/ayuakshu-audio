# Setup guide — AYUAKSHU Audio

Private GitHub repo holds **application source only**. Multi‑GB TTS/STT weights are **third-party** and must be downloaded from Hugging Face / OpenAI (or copied from a USB pack). They are never committed.

**Supported Mac:** Apple Silicon (M1/M2/M3/M4). Intel is not built.

---

## 1. What is in GitHub vs what you download

| Item | In this private repo? | How you get it |
|------|------------------------|----------------|
| App source (Tauri, React, FastAPI, scripts) | **Yes** | `git clone` |
| Python / Node / Rust lockfiles & configs | **Yes** | `git clone` |
| `dist/AYUAKSHU-Audio.dmg` (~482 MB) | **No** (GitHub git 100 MB limit) | Rebuild with `./scripts/build_dmg.sh`, or a GitHub **Release** asset if uploaded |
| `OfflineVoice-Models/` (~3.5 GB) | **No** | Download Chatterbox + Whisper (below), then pack |
| `backend/.venv`, `node_modules`, PyInstaller bundle | **No** | Recreated on each machine |

### Third-party model sources (authoritative)

| Model | Owner | Download location | Size (approx.) |
|-------|--------|-------------------|----------------|
| Chatterbox Multilingual (TTS + clone) | Resemble AI | https://huggingface.co/ResembleAI/chatterbox | ~3.2 GB |
| Whisper `small` (STT / Record Voice) | OpenAI | OpenAI Whisper checkpoints (script uses official URLs) | ~461 MB |
| pkuseg extras (optional, Chinese tokenizer) | pkuseg | Vendored into the USB pack if present; Hindi/English TTS does not require it | ~70 MB |

You do **not** host these weights. You retrieve them with the installers below.

---

## 2. Clone the private repo

You need access as the owner or a collaborator.

```bash
git clone https://github.com/chandan539/ayuakshu-audio.git
cd ayuakshu-audio
```

SSH:

```bash
git clone git@github.com:chandan539/ayuakshu-audio.git
cd ayuakshu-audio
```

---

## 3. Developer toolchain (once per Mac)

Put Node and Cargo on `PATH` if they live in user installs:

```bash
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:$PATH"
```

Need:

- **Python 3.10+** (3.12–3.14 is fine)
- **Node.js + npm**
- **Rust** (`rustup`) for the Tauri shell
- **Apple Silicon Mac**, 16 GB RAM recommended

Create the Python env and install backend packages:

```bash
chmod +x scripts/*.sh
./scripts/setup_dev.sh
```

Frontend + Tauri CLI:

```bash
npm install
npm --prefix frontend install
```

---

## 4. Download the offline model files (required)

Internet is required **only for this step**. After this, generation and transcription stay on the Mac.

### 4a. Chatterbox (required for TTS)

Public Hugging Face repo: **[ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox)**

```bash
backend/.venv/bin/python backend/scripts/install_chatterbox_model.py
```

This is the **only** script allowed to contact Hugging Face for TTS weights. Files land in:

```text
models/tts/chatterbox/
  ve.pt
  t3_mtl23ls_v2.safetensors
  s3gen.pt
  grapheme_mtl_merged_expanded_v1.json
  conds.pt
  Cangjie5_TC.json
  LICENSE
  README.md
```

If Hugging Face rate-limits you, log in once (`huggingface-cli login`) and re-run the installer. The model is public; a token is usually not required.

### 4b. Whisper small (required for Record Voice / transcribe)

```bash
backend/.venv/bin/python backend/scripts/install_whisper_model.py --size small
```

Weight file:

```text
models/whisper/small.pt
```

The same script also copies into Application Support when those folders exist.

### 4c. Optional: USB / air-gap pack (same files, portable folder)

After 4a (and 4b), build the folder the in-app wizard expects:

```bash
backend/.venv/bin/python backend/scripts/pack_offline_models.py \
  --out dist/OfflineVoice-Models
```

That creates `dist/OfflineVoice-Models/` (~3.5 GB) with `manifest.json`, `tts/chatterbox/`, `whisper/`, and optional `extras/pkuseg`.

Install from that folder on another Mac (no internet):

```bash
backend/.venv/bin/python backend/scripts/install_chatterbox_model.py \
  --from-local dist/OfflineVoice-Models
```

Or in the **packaged app**: first launch → **Choose Offline Model Package** → select the `OfflineVoice-Models` folder (the folder itself, not `tts` inside it).

Do **not** zip this to a single 3.5 GB file for GitHub Releases (2 GB per-file limit). For GitHub, keep models on Hugging Face / OpenAI. For USB, copy the **folder**, not a giant zip.

---

## 5. Run from source

```bash
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:$PATH"
npm run tauri:dev
```

Backend-only:

```bash
./scripts/run_backend.sh
```

UI in a browser (no Tauri window):

```bash
./scripts/dev_ui.sh
```

Tests (skip TTS warmup):

```bash
npm run test:backend
# or
OFFLINEVOICE_SKIP_WARMUP=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -v
```

---

## 6. Build the Mac app (DMG)

Models stay **out** of the DMG. Recipients still need section 4 (download or USB pack).

```bash
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:$PATH"
./scripts/build_dmg.sh
```

Outputs:

- `dist/AYUAKSHU Audio.app`
- `dist/AYUAKSHU-Audio.dmg`

Signing: see [SIGNING.md](SIGNING.md). Without a Developer ID cert the build is ad-hoc; other Macs need **Right-click → Open**.

---

## 7. Share with others

| Goal | What to give them |
|------|-------------------|
| Developers | Access to this **private** GitHub repo + this setup guide |
| Testers with internet | DMG (or they build it) + they run the two install scripts **or** you give `OfflineVoice-Models` |
| Testers without internet | USB: `AYUAKSHU-Audio.dmg` + `OfflineVoice-Models/` folder (exFAT, 16 GB stick) |

App Store / notarized public download needs an Apple Developer Program account — not GitHub.

---

## 8. Data on disk (after the app runs)

```text
~/Library/Application Support/AYUAKSHU Audio/
```

Uninstall: [UNINSTALL.md](UNINSTALL.md). Clean-machine checklist: [CLEAN_INSTALL.md](CLEAN_INSTALL.md).
