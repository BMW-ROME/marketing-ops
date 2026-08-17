# VOICE_CLONE_MIGRATION.md

Decision: replace ElevenLabs with **Chatterbox** (Resemble AI, MIT-licensed,
open-source) for voice cloning in youtube-engine. Decided 2026-08-17.

## Why

- ElevenLabs voice cloning requires a paid tier -- ongoing per-character or
  subscription cost with no free path to a real clone.
- Chatterbox is free, MIT-licensed, fully local (runs on your own GPU), and
  in Resemble AI's own blind listening study, 65.3% of listeners preferred
  Chatterbox-Turbo over ElevenLabs (vs. 24.5% preferring ElevenLabs).
- Fits the existing local-first infrastructure pattern (Ollama, Docker) --
  no new recurring API dependency, no data leaving the local machine.
- Zero-shot cloning: only needs a short reference audio clip (~10 seconds
  for Turbo) rather than an account-based cloning flow.

## What changes in youtube-engine

`core/voice_clone.py` and `core/voice_gen.py` were built against ElevenLabs
(and Edge-TTS as a fallback) with 9 fake-client test cases. These need to be
reworked to call Chatterbox instead:

- Replace the ElevenLabs API client calls with local Chatterbox inference
  (`chatterbox-tts` pip package, `ChatterboxTTS.from_pretrained()` /
  `ChatterboxTurboTTS.from_pretrained()`).
- Voice "cloning" becomes: supply a reference `.wav` clip via
  `audio_prompt_path` at generation time -- no persistent "voice_id" to
  manage, no dashboard step, no account required beyond having Chatterbox
  installed locally.
- Existing fake-client test structure can largely be preserved -- swap the
  fake ElevenLabs client for a fake Chatterbox model object with the same
  `.generate()` interface shape.
- Hardware note: Chatterbox-Turbo is a 350M param model, designed for lower
  compute/VRAM than the full-size models -- should run on a reasonably
  modern GPU. Chatterbox-Multilingual (500M) is heavier if 23-language
  support is needed later.

## What this means for the ElevenLabs open item

The prior open item ("record a live ElevenLabs voice model ID") is now
**superseded, not resolved** -- there is no ElevenLabs voice_id to record,
because ElevenLabs is no longer the chosen path. The new open item is:
record the path to the reference voice clip(s) used with Chatterbox instead
(see below).

## New open item: reference voice clip

Chatterbox needs one or more short (~10s+) clean audio clips of the actual
voice to clone from, supplied as `audio_prompt_path` at generation time.

**Action needed:** record or select a clean ~10-30 second voice sample
(no background noise, natural speaking pace) and store it somewhere
`core/voice_clone.py` can reference (e.g. `assets/voice_reference.wav` in
youtube-engine, not committed to git if it's a personal recording -- treat
like a credential/asset, reference via path in `.env` instead).

- Reference clip path: _(not yet recorded -- pending a real recording/sample)_
