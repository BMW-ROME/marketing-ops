# BUILD_PLAN.md

Consolidated, sequenced build plan across the YouTube engine, lead-gen, and
brand layers. This is the single place to check "what's next" -- individual
files (INTEGRATION.md, VOICE_CLONE_MIGRATION.md, TOOLS.md, lead_capture.yaml)
hold the detail; this file holds the order and ownership.

Last updated: 2026-08-17

## Ownership legend

- **[marketing-ops agent]** -- handled in this repo (brand config, docs, lead-gen scaffold)
- **[youtube-engine agent]** -- handled by the separate agent rebuilding youtube-engine
- **[account owner]** -- requires BMW-ROME's direct action (credentials, recordings, decisions only a human can make)

## Phase A -- Brand + CTA sync (COMPLETE)

1. [marketing-ops agent] `brand_identity.yaml`, `lead_capture.yaml` created -- DONE
2. [youtube-engine agent] `config/brand_loader.py`, `core/brand_aware_prompts.py` created -- DONE
3. [youtube-engine agent] `script_writer.py` + `seo_optimizer.py` wired to brand/CTA -- DONE (commit a8ae6de)
4. [account owner] Provided fallback contact email -- DONE (thee3litesolutions@zohomail.com)
5. [marketing-ops agent] Removed Voice123 as funnel fallback -- DONE
6. [marketing-ops agent] Resolved channel-tone decision (uniform across all 7 channels) -- DONE

## Phase B -- Voice cloning swap (IN PROGRESS)

1. [marketing-ops agent] Decided: Chatterbox replaces ElevenLabs -- DONE
   (see VOICE_CLONE_MIGRATION.md for full rationale + target spec)
2. [youtube-engine agent] Rework `core/voice_clone.py` / `core/voice_gen.py`
   to call local Chatterbox inference instead of ElevenLabs -- IN PROGRESS
   (ownership confirmed with account owner 2026-08-17; not yet started as
   of last commit check)
3. [account owner] Provide a ~10-30s clean reference voice clip for
   Chatterbox to clone from -- NOT YET PROVIDED (blocks real end-to-end
   testing of phase B, but does not block the code rework itself, which can
   be built/tested against a placeholder clip first)

## Phase C -- Landing page (BLOCKED on Phase B)

1. [account owner + assistant] Build the actual home-base landing page
   (headline, bio, demos, offers, contact form, schema markup) -- NOT STARTED,
   intentionally held so it can showcase real Chatterbox-cloned voice demos
   rather than launching without them
2. [marketing-ops agent] Set `landing_page_url` in `lead_capture.yaml` once
   the page is live -- NOT STARTED

## Phase D -- Lead-gen activation (PARALLEL, NOT BLOCKED)

This phase does not depend on Phase B/C and can proceed independently:

1. [account owner] Rotate the previously-shared Bright Data API token
   (treat as compromised since it was pasted into a chat session) -- ACTION NEEDED
2. [account owner] Provision a real Bright Data dataset/collector ID for the
   target source (web search, company data, etc.) -- NOT YET PROVIDED
3. [marketing-ops agent] `lead-gen/lead_generator.py` implemented against
   Bright Data + local Ollama qualification -- DONE, untested against live
   credentials
4. [account owner] Test the Streamlit app end-to-end once token + dataset
   ID exist -- NOT YET DONE

## Phase E -- Deferred / not yet scheduled

- OpenSDR integration (phase 2 of the lead-gen tool stack, per TOOLS.md)
- Enverif email verification (phase 3, conditional on having a real lead list)
- UnifAPI GEO/citation monitoring (phase 4, conditional on landing page existing)
- n8n lead-funnel workflow (form -> auto-reply -> CRM) -- referenced in
  earlier planning but not yet scaffolded in any repo
- stunning-dollop / EliteAgents integration -- explicitly out of scope per
  account owner's instruction to focus on YouTube + lead-gen only

## What to check before starting new work

Before starting any new build step, check:
1. `INTEGRATION.md` for the current wiring status between marketing-ops and youtube-engine
2. `VOICE_CLONE_MIGRATION.md` for the voice-clone swap target spec and status
3. `TOOLS.md` for the lead-gen tool stack sequencing
4. This file's Phase status for what's actually next in order
