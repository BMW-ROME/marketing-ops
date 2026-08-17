# INTEGRATION.md

This repo (`marketing-ops`) is the shared marketing/brand/ops layer across all
customer-facing and lead-generation surfaces. It is intentionally separate
from trading repos (`LLM_STU`, `COMPETITIVE-AGENTS--SAVING`, `EliteAgents`),
which must remain isolated from brand/public-facing logic.

## Purpose

Prevent brand drift across three parallel initiatives:

1. **YouTube engine** (`youtube-engine` repo) — 7 channels + Freestyle mode
2. **n8n automation pipeline** (local n8n instance)
3. **Voice-acting brand** (Voices.com, Voice123, future landing page)

Each of these has been built/rebuilt somewhat independently. Without a shared
reference, each surface risks inventing its own tone, copy, and positioning.

## What lives here

- `brand_identity.yaml` — canonical tone, bio, niches, language rules. The
  single source of truth for all external-facing copy.
- `lead-funnel/` *(planned)* — n8n workflow spec for the lead intake pipeline
  (form -> auto-reply -> CRM -> notification -> follow-up).
- `content/` *(planned)* — content calendar, outreach templates, niche wedge
  decisions for the 90-day growth plan.

## Status: youtube-engine integration (updated 2026-08-17)

The following have been pushed directly to `youtube-engine` to wire it to
this repo:

- `config/brand_loader.py` — fetches `brand_identity.yaml` from this repo via
  raw GitHub content API, with local cache + built-in default fallback.
  Never raises; safe to call unconditionally from pipeline stages.
- `config/.env.brand.template` — adds `GITHUB_TOKEN` and
  `BRAND_IDENTITY_BRANCH` vars needed for the loader to fetch live (this repo
  is private, so anonymous raw fetches will fail without a token).
- `BRAND_INTEGRATION_SNIPPET.md` — exact copy-in code for wiring
  `get_brand_identity()` / `get_voice_tone_descriptors()` /
  `get_language_rules()` / `get_primary_niches()` into
  `core/script_writer.py` (Stage 1, GPT-4o script generation) and
  `core/seo_optimizer.py` (Stage 8, GPT-4o SEO metadata generation).
  **Not yet applied** — those two files were mid-edit by another agent
  fixing integration bugs (missing `content_db.init_db()`, mismatched
  `ChatClient` protocol shapes) as of the same day, so the snippet was left
  as a doc rather than a blind overwrite.

### ElevenLabs voice cloning — CONFIRMED EXISTING (resolves prior open item)

`youtube-engine` already has voice-cloning infrastructure in place:

- `core/voice_clone.py` (added 2026-08-13) — "ElevenLabs voice cloning setup,
  tested with fake client (9 test cases)."
- `core/voice_gen.py` (added 2026-08-13, Stage 2 of the pipeline) — Edge-TTS
  and ElevenLabs voice synthesis, tested with a fake synthesizer +
  concatenator.

Both are unit-tested against fake/mock clients, not yet confirmed wired to a
real ElevenLabs account or a real cloned voice model ID. **Action needed:**
confirm whether a live ElevenLabs voice model ID exists for the actual brand
voice, and if so, record it below so YouTube narration and any future
automated audio content use the same voice asset as the Voices.com/Voice123
voice-acting brand.

- ElevenLabs voice model ID: _(not yet recorded — pending confirmation)_

## Instructions for the YouTube engine agent

- Read `brand_identity.yaml` before generating any channel description,
  video title/description copy, or narration script tone parameters.
- Wire `config/channels.py` in `youtube-engine` to import or reference the
  `voice_tone`, `language_rules`, and `niches` sections here, rather than
  hardcoding tone per channel.
- Apply `BRAND_INTEGRATION_SNIPPET.md` to `core/script_writer.py` and
  `core/seo_optimizer.py` once those files are stable (see status above).
- If `core/voice_clone.py` is connected to a real ElevenLabs voice, record
  the model ID in this file's "ElevenLabs voice cloning" section above —
  reference `identity` and `voice_tone` fields in `brand_identity.yaml` for
  consistency.
- Do not introduce new tone descriptors or taglines locally — propose
  additions to `brand_identity.yaml` instead.

## Instructions for the n8n pipeline agent

- Any workflow that sends external-facing text (lead auto-replies, outreach
  emails, YouTube comment/DM responses) should pull subject lines, greeting
  style, and signature copy from `brand_identity.yaml`.
- Keep trading-related workflows (TradeStation, FTMO, Alpaca) in their own
  namespace/credentials, fully separate from any workflow that touches this
  repo's brand content.
- When the lead-funnel workflow is built, mirror its spec into
  `lead-funnel/` here so there's a durable record outside the n8n instance
  itself.

## Non-goals

- This repo does not manage trading logic, credentials, or strategies.
- This repo does not replace marketplace profiles (Voices.com/Voice123) —
  it defines what those profiles (and everything else) should say.

## Open items

- Confirm whether channel-level tone should be fully uniform (all 7 channels
  match `brand_identity.yaml` exactly) or niche-adapted per channel while
  keeping the same core descriptors. Default until decided: niche-adapted,
  core descriptors preserved.
- ~~Decide on and record the ElevenLabs voice model ID once a voice clone is
  finalized~~ — infrastructure confirmed existing (`core/voice_clone.py`,
  `core/voice_gen.py`); still need the actual live model ID recorded once
  connected to a real ElevenLabs account.
- Generate a fine-grained GitHub PAT (read-only, scoped to this repo) and add
  it to `youtube-engine`'s real `.env` so `config/brand_loader.py` fetches
  live instead of falling back to its built-in default.
- Apply `BRAND_INTEGRATION_SNIPPET.md` to `core/script_writer.py` and
  `core/seo_optimizer.py` once those files are no longer mid-edit.
