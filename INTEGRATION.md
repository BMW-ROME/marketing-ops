# INTEGRATION.md

This repo (`marketing-ops`) is the shared marketing/brand/ops layer across all
customer-facing and lead-generation surfaces. It is intentionally separate
from trading repos (`LLM_STU`, `COMPETITIVE-AGENTS--SAVING`, `EliteAgents`),
which must remain isolated from brand/public-facing logic.

## Purpose

Prevent brand drift across three parallel initiatives:

1. **YouTube engine** (`youtube-engine` repo) -- 7 channels + Freestyle mode
2. **n8n automation pipeline** (local n8n instance)
3. **Voice-acting brand** (Voices.com, Voice123, future landing page)

## Status: youtube-engine integration -- COMPLETE (as of 2026-08-17)

Full chain confirmed live end-to-end:

- `config/brand_loader.py` -- fetches `brand_identity.yaml` from this repo,
  with local cache + built-in default fallback.
- `config/.env.brand.template` -- `GITHUB_TOKEN` + `BRAND_IDENTITY_BRANCH` vars.
- `core/brand_aware_prompts.py` -- single-call wrapper exposing
  `get_script_style_block()`, `get_seo_style_block()`, `get_video_cta_text()`,
  `get_pinned_comment_cta()`.
- `core/script_writer.py` -- wired (commit a8ae6de): adds brand voice/tone to
  the system prompt via `get_script_style_block()`.
- `core/seo_optimizer.py` -- wired (commit a8ae6de): adds brand voice/tone to
  the SEO prompt, and appends the lead-gen CTA to the video description and
  pinned comment via `get_video_cta_text()` / `get_pinned_comment_cta()`.
  Skips CTA injection if lead_capture.yaml's CTA is still an unconfigured
  placeholder. Both wired via try/except so a marketing-ops fetch failure
  never blocks video generation.
- Verified by the implementing agent across three paths: brand-absent,
  brand-present, and placeholder-skip.

Every video this pipeline generates now automatically uses brand tone in
scripts and SEO copy, and appends the real lead-gen CTA
(`thee3litesolutions@zohomail.com`, per `lead_capture.yaml`) to descriptions
and pinned comments.

## Decision: channel-level tone uniformity (RESOLVED 2026-08-17)

**Decision: uniform tone across all 7 channels**, at least for now.

Rationale: `brand_aware_prompts.py` feeds the same `voice_tone` block from
`brand_identity.yaml` into every script/SEO call regardless of which of the
7 channels (or Freestyle mode) is generating content. No per-channel
override mechanism exists in `config/channels.py` today, and introducing
one would require a new config schema, a decision about which niches map to
which channels, and rework of `brand_aware_prompts.py` to accept a
channel-id parameter -- none of which is justified yet without evidence
that uniform tone is underperforming.

Revisit this if/when:
- Channels are differentiated enough (e.g. one is explicitly comedic, one
  explicitly clinical/technical) that a single tone block feels wrong for
  some of them, or
- Data (view retention, comments, subscriber growth) suggests tone mismatch
  is hurting specific channels.

If revisited, the extension point is `brand_aware_prompts.get_script_style_block()`
and `get_seo_style_block()` -- add an optional `channel_id` parameter that
looks up a per-channel override section in `brand_identity.yaml` (to be
added, e.g. under a new `channel_overrides:` key) and falls back to the
global `voice_tone` block when no override exists for that channel.

## ElevenLabs voice model ID (STILL OPEN)

`core/voice_clone.py` and `core/voice_gen.py` exist and are unit-tested
against a fake client (9 test cases). As of 2026-08-17, **no live
ElevenLabs voice model ID has been confirmed or recorded**. This requires:

1. An active ElevenLabs account (paid tier needed for voice cloning).
2. A real voice sample uploaded and cloned via the ElevenLabs dashboard or
   API, producing a `voice_id`.
3. That `voice_id` recorded here and wired into `core/voice_clone.py` /
   `core/voice_gen.py`'s configuration (likely via `.env`, e.g.
   `ELEVENLABS_VOICE_ID=`).

**Action needed from the account owner:** confirm whether an ElevenLabs
account/clone already exists outside of this codebase (e.g. created
manually via their dashboard) before assuming this needs to be built from
scratch. If it exists, provide the `voice_id` to record here. If it
doesn't exist yet, this is a manual step (record audio samples, upload to
ElevenLabs, clone) that no agent can complete without your voice and an
ElevenLabs account -- it cannot be automated end-to-end.

- ElevenLabs voice model ID: _(not yet recorded -- pending account owner confirmation)_

## Landing page URL (STILL OPEN)

`lead_capture.yaml`'s `landing_page_url` remains blank. Per the earlier
90-day growth plan, this is the single highest-leverage missing piece for
the overall lead-gen strategy -- it's the anchor point that GEO, social,
YouTube CTAs, and marketplace profiles should all point back to, rather than
routing traffic to a bare email address indefinitely.

Until this exists, `core/brand_aware_prompts.py` correctly falls back to
`fallback_contact_method` (thee3litesolutions@zohomail.com), so nothing is
broken -- but the funnel is weaker than it will be once a real landing page
exists (no case studies, no niche-specific service pages, no
schema markup for GEO/AI-citation purposes).

**Action needed:** build the landing page (see the earlier 90-day plan:
headline, bio, 3-5 demos, offers, contact form, schema markup) and set
`landing_page_url` in `lead_capture.yaml` once live. This is a build task,
not a config task -- no agent can invent your actual hosted page.

## What lives here

- `brand_identity.yaml` -- canonical tone, bio, niches, language rules.
- `lead_capture.yaml` -- CTA copy, intake questions, funnel destination config.
- `TOOLS.md` -- lead-gen tool stack decision log (OpenSDR, Bright Data,
  Enverif, Bricks, UnifAPI).
- `lead-gen/` -- Bright Data AI Lead Generator scaffold, qualification via
  local Ollama models (not OpenAI).
- `INTEGRATION.md` -- this file.

## Non-goals

- This repo does not manage trading logic, credentials, or strategies.
- This repo does not replace marketplace profiles (Voices.com/Voice123) --
  it defines what those profiles (and everything else) should say.
- Voice123 is explicitly excluded as a funnel/fallback destination (decided
  2026-08-17) -- see `lead_capture.yaml` notes.

## Remaining open items (updated 2026-08-17)

1. **ElevenLabs voice model ID** -- needs account owner to confirm/provide
   (see section above). Cannot be automated.
2. **Landing page** -- needs to be built and its URL added to
   `lead_capture.yaml` (see section above). Cannot be automated end-to-end.
3. ~~Channel-level tone uniformity~~ -- RESOLVED: uniform tone adopted, see
   decision section above.
4. `lead-gen/lead_generator.py` needs a real Bright Data dataset ID and a
   rotated `BRIGHT_DATA_API_TOKEN` (the previously shared token should be
   treated as compromised and rotated) before it can run against live data.
