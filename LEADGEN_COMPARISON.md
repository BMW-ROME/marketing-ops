# LEADGEN_COMPARISON.md

How `lead-gen/lead_generator.py` (Bright Data scrape + local Ollama
qualification) stacks up against the three tools most often suggested for
this kind of funnel: **Apollo.io**, **Snov.io**, and **Leadfeeder**.
Apollo/Snov/Leadfeeder are commercial SaaS products (not literally GitHub
repos); this file compares capabilities so future tool decisions use the
same facts rather than marketing copy.

Date written: 2026-08-19. Feature snapshots reflect the free tiers as
documented at that time; verify current tiers on their sites before
deciding.

## Product focus, one line each

| Tool | Core offer |
|---|---|
| `lead_generator.py` | DIY lead sourcing: you supply a Scraper Studio collector + URLs; it scrapes, then scores fit against `icp.yaml` on a **local** LLM, and hands you a ranked list. No outreach, no built-in database. |
| Apollo.io | Owned, verified B2B contact/company database with filtering + sequences. |
| Snov.io | Email finding/verification plus multichannel drip outreach with AI personalization. |
| Leadfeeder | Intent: identifies which companies visit your website (reverse-IP lookup), ranked by fit. |

## Capability matrix

| Capability | `lead_generator.py` | Apollo.io | Snov.io | Leadfeeder |
|---|---|---|---|---|
| Lead database | None built-in (BYO collector + URL list) | Verified B2B DB (email, phone, tech-stack filters) | Email finder/verifier + small CRM | None (no contact DB) |
| Lead source | Outbound scraping of URLs you supply | Outbound search/filter on owned data | Outbound email lookup | **Inbound intent** (companies hitting your site) |
| Lead scoring / qualification | Custom, local LLM vs `icp.yaml` (free, private, JSON-mode) | Built-in scoring + filters | Basic | ICP fit + engagement recency |
| Data fields | Whatever your collector extracts (raw JSON) | Email, phone, company, LinkedIn, job titles, tech stack | Email, company, LinkedIn, job history | Company, industry, revenue, headcount, tech stack |
| Email finding + verification | **None** (Enverif is a deferred phase-3) | Built-in (dedicated to verification) | Built-in finder + verifier | N/A |
| Outreach automation | **None** (produces a reviewed list only; n8n workload deferred) | Sequences + engagement | Drip campaigns, multichannel, AI copywriting | N/A |
| Integrations | None wired (n8n hosted, not scaffolded) | Salesforce, HubSpot, Gmail, LinkedIn, Slack | HubSpot, Salesforce, Pipedrive, Zapier | Salesforce, HubSpot, Slack, Zapier |
| Cost model | Free self-host; only Bright Data credits + your hardware | Paid subscription | Paid subscription | Paid subscription |
| Data privacy | Qualification never leaves your host; only the scrape hits an external API | Lead data processed on Apollo's cloud | Lead data processed on Snov's cloud | Visitor behavior processed by Leadfeeder |

## Where `lead_generator.py` is clearly ahead

- **Privacy & cost of scoring.** Fit-scoring runs on your own Ollama
  (`phi4-mini` default). No per-token charge, no lead data sent to a cloud
  LLM for the qualification step.
- **No paid seat.** The whole pipeline is yours, on a free-tier VM if you
  want.
- **Any niche.** Personas and signals live in `icp.yaml`, so re-targeting
  is a YAML edit — no repurchase of another database slice.

## Where `lead_generator.py` falls short (the real gaps)

1. **No owned contact database.** It only processes what your collector
   returns for URLs you paste. Apollo/Snov sell ready-to-query verified
   data; we assemble raw records ourselves.
2. **No email find/verify.** Scraped data is unverified. This is the
   single most useful add-on and maps to **Enverif (TOOLS.md, phase 3)** —
   conditional on getting a real list first.
3. **No intent/visitor tracking.** Leadfeeder's signature feature isn't
   replicable with a scraper; it needs a tracking pixel/reverse-IP lookup
   wired to our stack. This would power warm, "they were already looking"
   outreach rather than cold scraping.
4. **No outreach or CRM wiring.** The app stops at a ranked list.
   Apollo's sequences / Snov's drips are the automation layer that n8n is
   meant to provide later (BUILD_PLAN phase E) for this repo.
5. **No structured field normalization.** We display raw scraped JSON,
   not a typed contact record (email/phone/LinkedIn/tech stack), so
   downstream dedup and CRM import are manual.

## Recommended roadmap (does not replace TOOLS.md)

| Step | What | Tool/effort | Unblocks |
|---|---|---|---|
| 1 (now) | Ship phase-1 pipeline to a host; calibrate `icp.yaml` on real scraped leads | This repo, Docker stack | Real candidate list |
| 2 | Email verification pass on the produced list | Enverif (phase 3) | Safe outreach |
| 3 | n8n funnel: form/email -> auto-reply -> CRM log | n8n workflow build (phase E) | Human-approved outreach at low volume |
| 4 | Intent layer: tracking pixel + company identification on the landing page (phase C) | New small component | Warm, Leadfeeder-style inbound |
| 5 | Structured record normalization + CSV/JSON export schema | Code in `lead_generator.py` | CRM import, dedup |

Rule of thumb: **do not buy Apollo/Snov/Leadfeeder** until phase-1 data
shows which of their specific capabilities is actually missing pain. Our
current differentiator (local, private, cheap scoring) is worth preserving
rather than trading away for a seat fee.