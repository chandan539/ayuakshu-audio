# Clean install test (Phase 7)

Use this checklist on a fresh Mac (or after deleting app data) to prove the
acceptance workflow from the OfflineVoice build specification.

Full developer setup (clone + Hugging Face / OpenAI model download): [SETUP.md](SETUP.md).

## Prerequisites

- Apple Silicon Mac (MVP target: `aarch64-apple-darwin`)
- `dist/AYUAKSHU-Audio.dmg` (build with `./scripts/build_dmg.sh`)
- Offline model package `OfflineVoice-Models/` (USB / local folder) **or** one-time
  download of Chatterbox + Whisper (see SETUP.md), then pack with `pack_offline_models.py`

Pack models (on a machine that already has weights):

```bash
backend/.venv/bin/python backend/scripts/pack_offline_models.py \
  --out dist/OfflineVoice-Models
```

## Procedure

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open `OfflineVoice.dmg` | Disk image mounts |
| 2 | Drag **OfflineVoice** to Applications | App copies |
| 3 | Launch OfflineVoice | Window opens; local backend starts on `127.0.0.1` |
| 4 | First-run: install models from local package (or wizard) | Models show Installed |
| 5 | Quit the app completely | Process exits |
| 6 | Turn **Wi‑Fi OFF** (and unplug Ethernet) | No Internet |
| 7 | Launch OfflineVoice again | App + backend start offline |
| 8 | Import a short reference voice | Voice profile appears |
| 9 | Enter Hindi text → Generate → Play | Audio plays |
| 10 | Export WAV + MP3 | Files written locally |
| 11 | Enter English text → Generate → Play → Export | Works offline |

## Automated counterpart (developer machine)

With models already under `models/tts/chatterbox/`:

```bash
./scripts/test_offline.sh
```

This blocks non-loopback connects in-process and verifies Hindi/English WAV/MP3.

## Record results

Copy into a release notes file when shipping:

```text
Date:
Mac model / chip:
macOS version:
DMG version:
Model package version:
Wi-Fi off during generate: yes/no
Hindi generate: pass/fail
English generate: pass/fail
WAV export: pass/fail
MP3 export: pass/fail
Unexpected network (Activity Monitor / Little Snitch): none / details
Notes:
```
