# VOICE_CLONE_MIGRATION.md

Decision: replace ElevenLabs with **Chatterbox** (Resemble AI, MIT-licensed,
open-source) for voice cloning in youtube-engine. Decided 2026-08-17.

**Ownership note (2026-08-17):** the youtube-engine rebuilding agent is
handling the actual code swap in `core/voice_clone.py` / `core/voice_gen.py`.
This file exists to give that agent a clear target spec and to track the
one input only the account owner can provide (the reference voice clip) --
it is not a competing implementation.

## Why

- ElevenLabs voice cloning requires a paid tier -- ongoing cost with no free
  path to a real clone.
- Chatterbox is free, MIT-licensed, fully local (runs on your own GPU), and
  in Resemble AI's own blind listening study, 65.3% of listeners preferred
  Chatterbox-Turbo over ElevenLabs (vs. 24.5% preferring ElevenLabs).
- Fits the existing local-first infrastructure pattern (Ollama, Docker) --
  no new recurring API dependency, no data leaving the local machine.
- Zero-shot cloning: only needs a short reference audio clip (~10 seconds
  for Turbo) rather than an account-based cloning flow.

## Target spec for the youtube-engine agent

`core/voice_clone.py` and `core/voice_gen.py` were built against ElevenLabs
(and Edge-TTS as a fallback) with 9 fake-client test cases. Target state:

- Replace ElevenLabs API client calls with local Chatterbox inference via
  the `chatterbox-tts` pip package (`ChatterboxTTS.from_pretrained()` or
  `ChatterboxTurboTTS.from_pretrained()` for the lighter 350M-param model).
- Voice "cloning" becomes: pass a reference `.wav` clip via
  `audio_prompt_path` at generation time -- no persistent voice_id, no
  dashboard step, no account required beyond having Chatterbox installed.
- Preserve the existing fake-client test structure where possible -- swap
  the fake ElevenLabs client for a fake Chatterbox model object exposing
  the same `.generate()` interface shape, so the 9 existing test cases can
  largely be adapted rather than rewritten from scratch.
- Keep Edge-TTS as the non-cloned fallback path (unchanged) -- Chatterbox
  only replaces the ElevenLabs cloning path, not the whole voice_gen module.
- Reference clip path should be read from an env var
  (e.g. `VOICE_REFERENCE_CLIP_PATH`) rather than hardcoded, matching the
  existing `.env`-driven config pattern in this repo.
- Hardware note: Chatterbox-Turbo (350M params) targets lower VRAM than the
  full-size Chatterbox-Multilingual (500M, 23 languages) -- start with Turbo
  unless multilingual output is needed.

## Status

- [x] Decision made: Chatterbox over ElevenLabs (2026-08-17)
- [ ] `core/voice_clone.py` / `core/voice_gen.py` rework -- IN PROGRESS by
      the youtube-engine rebuilding agent (not yet started as of the last
      check; most recent commit was an environment pre-flight checker,
      unrelated to this swap)
- [ ] Reference voice clip -- NOT YET PROVIDED (see below)
- [ ] `ELEVENLABS_VOICE_ID` references in `.env.template` / INTEGRATION.md
      should be removed once the swap lands (superseded, not applicable)

## Open item: reference voice clip

Chatterbox needs one or more short (~10s+) clean audio clips of the actual
voice to clone from, supplied as `audio_prompt_path` at generation time.

**Action needed from account owner:** record or select a clean ~10-30
second voice sample (no background noise, natural speaking pace). Store it
as a local asset (e.g. `assets/voice_reference.wav` in youtube-engine, kept
out of git like any personal recording) and reference its path via
`VOICE_REFERENCE_CLIP_PATH` in `.env`.

- Reference clip path: _(not yet recorded -- pending a real recording/sample)_

## Landing page dependency

Per the build plan, the landing-page build is intentionally held until this
voice-clone swap is settled, so the page can showcase real cloned-voice
demos rather than launch without them. See `INTEGRATION.md` for the
consolidated build-plan ordering.
