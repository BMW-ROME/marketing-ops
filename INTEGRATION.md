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

## Instructions for the YouTube engine agent

- Read `brand_identity.yaml` before generating any channel description,
  video title/description copy, or narration script tone parameters.
- Wire `config/channels.py` in `youtube-engine` to import or reference the
  `voice_tone`, `language_rules`, and `niches` sections here, rather than
  hardcoding tone per channel.
- If a channel's TTS voice is intended to reflect the real brand voice
  (e.g. an ElevenLabs clone), reference `identity` and `voice_tone` fields
  for consistency, and note the voice model ID back in this repo once
  finalized.
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
- Decide on and record the ElevenLabs voice model ID here once a voice clone
  is finalized, so both YouTube and any future automated audio content use
  the same voice asset.
