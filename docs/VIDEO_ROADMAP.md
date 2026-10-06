# Roadmap — local spokesperson video (HeyGen-style)

Status: **plan only**. Not started. Use this when building a local “photo + script + cloned voice → talking video” feature on top of AYUAKSHU Audio.

Target machine for v1: **Apple M4, 16 GB RAM**, fully offline. This is the same Mac the audio app already runs on.

---

## How HeyGen works (what we are matching)

HeyGen is a **cloud** video studio. The face model does not run on the user’s Mac. You send a face, a script, and a voice; their servers return an MP4.

Pipeline:

1. **Avatar** from one of three sources:
   - **Photo** — one still image. Fast. Less real than a video twin.
   - **Digital twin** — short video footage of a real person. This is the “looks like HeyGen” path. Their product asks for **consent** before a real person’s video twin can be used.
   - **Prompt** — a text description of a synthetic character (no photo).
2. **Voice** — a stock voice, or a **clone** from a short audio sample (they also strip background noise).
3. **Script** — their cloud text-to-speech speaks it, **or** the mouth is driven by an audio file you already have.
4. **Render** — Avatar engine III, IV (common default), or V (higher quality). Lips, eyes, head, and sometimes hands. Optional: background color or image, captions, speed, pitch, and a motion prompt (“nod”, “gesture”).
5. **Export** — MP4, or WebM with a transparent background.
6. **Separate products, not the core clip:** live streaming avatar, video translation with new lip-sync, new outfits/backgrounds (“looks”) for an existing avatar.

Public API surface (2026) this plan is based on: photo / digital-twin / prompt avatars, script + voice video render, voice clone, captions, background, motion prompt, and realtime avatar sessions (TTS, audio, or streaming text).

---

## What “local” means here

v1 on this Mac:

```text
Script → AYUAKSHU Audio (Chatterbox clone) → WAV → SadTalker → MP4
```

Voice clone (Hindi + English) already exists. The new piece is **one photo + that WAV → a talking-head MP4**.

| HeyGen piece | Local stand-in | On this M4 / 16 GB |
|---|---|---|
| Photo avatar + script | SadTalker + existing voice clone | Yes — first version |
| Voice clone, Hindi/English | Already in this app | Yes |
| Captions, solid or image background, MP4 export | FFmpeg in the app | Yes |
| Video digital twin, hands, motion prompts | Not in v1 | No |
| Live talking avatar | Needs a much faster GPU | No |
| Translate a video and re-lip-sync | Later, separate project | No |
| Use any person’s photo with no consent | Do not ship | Consent screen required |

**Quality:** SadTalker moves the head, blinks, and approximates lips. It will not look like HeyGen Avatar IV/V. MuseTalk has better lips but wants a **video** of the person and about **20 GB RAM while rendering**, which is tight on 16 GB. Wav2Lip only moves the mouth and also needs an existing video.

**Speed (honest):** about **4–8 minutes of processing per 1 minute of video** after models are loaded. Run the voice model and the face model **one after the other**. Loading both at once can exhaust 16 GB unified memory.

---

## Resources

### Already on this machine

- Apple M4, 16 GB RAM
- AYUAKSHU Audio (Tauri + local FastAPI)
- Chatterbox + Whisper weights (~3.5 GB), not stored in git

### Add for v1

- SadTalker code and weights, about **2–4 GB** (download once; do not commit weights)
- A **separate Python 3.10 environment**. SadTalker does not share the app’s Python 3.14 / current PyTorch setup cleanly
- FFmpeg
- About **30 GB free disk** while packaging
- Input rules: one front-facing, well-lit, shoulders-up photo. Side faces and group photos fail
- Product rule: a consent checkbox that the person in the photo and the cloned voice agreed to this use

### People and money

- One engineer who already knows this repo
- No cloud GPU bill for v1

### Only if a later version must look closer to HeyGen

- A machine with an NVIDIA GPU and **12–24 GB VRAM**, **or** accept the photo-avatar look
- A **10–30 second video** of the person, not only a still
- That is a second project (MuseTalk-style lips, or a heavier portrait model). It is not week one

---

## Timeline

One person, inside this repo, local only. Estimates, not a start date.

| When | Outcome |
|---|---|
| Days 1–5 | Proof only: one photo + one existing WAV → one MP4 on this Mac. Go / no-go on look and speed. Do not change the voice UI until that clip is acceptable. |
| Weeks 2–5 | Usable screen: upload photo, paste script, pick cloned voice, progress, play, save MP4. Hindi and English. |
| Weeks 6–9 | Captions, background color or image, keep models loaded across clips, export to a folder the user chooses. |
| Month 3+ | Only if the photo version is worth keeping: short-video avatar (better lips). Still not HeyGen hand motion or live chat. |

- **~5 weeks** — local spokesperson you can demo (30–60 second clip).
- **~9 weeks** — stable desktop tool: photo, clone, script, captions, export.
- **Not a HeyGen replacement** on this hardware. Digital twin, gestures, live avatar, and translation are many more months and different hardware, and still would not copy HeyGen’s cloud models.

---

## Build order (when this roadmap is started)

1. Prove SadTalker on this Mac with an existing WAV. Stop if the look or the memory use is unacceptable.
2. Add a Video screen: photo, script, voice, Generate, Save MP4.
3. Generate speech first, release that model, then run the face model.
4. Captions and background.
5. Only then consider a video-based avatar.

### v1 demo target

One clear photo, a 30–60 second Hindi or English script, the existing cloned voice, and one MP4 saved to a folder the user picks.

### Explicitly out of v1

- Live / streaming avatar
- Hand gestures and motion prompts
- Outfit or scene changes from a text prompt
- Video translation
- Cloud HeyGen API (this roadmap is offline)
- Putting multi-GB face weights inside the app DMG or git (same rule as Chatterbox: download or USB, then local)

---

## Licenses and consent

- SadTalker and any face weights stay under **their** licenses. Confirm redistribution before a public download.
- A still photo of a real person plus a cloned voice is personal data. The app should require an on-screen confirmation that the user has permission, and should keep files on this Mac only (same offline rule as AYUAKSHU Audio).
