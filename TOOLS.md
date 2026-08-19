# TOOLS.md

Decision log for the lead-generation tool stack evaluated 2026-08-17,
alongside `lead_capture.yaml` (the funnel/CTA config) and `brand_identity.yaml`
(the tone/copy config). This file records what was considered, what was
chosen, and why -- so future agents don't re-evaluate from scratch or
introduce a conflicting tool.

## Candidates evaluated

| Tool | What it is | Verdict |
|---|---|---|
| **OpenSDR** | Open-source Node/TypeScript CLI + MCP server. Automates LinkedIn research: finds people/companies, mutual connections, drafts outreach messages via Puppeteer-driven browser session. Requires `FIRECRAWL_API_KEY`, `GOOGLE_GENERATIVE_AI_API_KEY`, `ANTHROPIC_API_KEY`. | **Adopted -- phase 2.** Good fit for LinkedIn-specific outreach (agencies, course creators) once phase 1 (Bright Data) is running. Node-based, so it runs alongside rather than inside the Python pipeline. |
| **Bright Data AI Lead Generator** | Open-source Python + Streamlit app. Scrapes B2B contact/company data via Bright Data's Scraper Studio API, qualifies/scores leads against an ideal-customer-profile using a LOCAL Ollama model via LangChain (LLMChain, JSON mode). Requires `BRIGHT_DATA_API_TOKEN` only -- no `OPENAI_API_KEY`; qualification never leaves the host. | **Adopted -- phase 1 (this integration).** Python-native, matches the existing stack (Docker, n8n). Broader than LinkedIn -- general web/company data. Scaffolded in this repo. |
| **Enverif** | Enterprise lead intelligence platform. Core service: email verification/validation (5 credits per email). | **Adopted -- phase 3, conditional.** Only useful once phase 1/2 produce an actual contact list worth cleaning before outreach. Not wired yet -- revisit once a lead list exists. |
| **Bricks (Bricks.ai)** | B2B SaaS for sales/marketing/IT teams to collaboratively build hyper-personalized proposals, contracts, and reports at scale. | **Rejected.** Built for larger B2B sales teams doing tender/proposal work. Wrong shape for a solo voice-actor funnel -- adds process overhead with no matching need. |
| **UnifAPI Agent & Marketing MCP** | Open-source MCP server + read-only marketing skills: SEO audits, GEO/AI-visibility checks (tracking citation in ChatGPT/Perplexity/AI Overviews), local SEO, competitive intelligence. Explicitly read-only -- "eyes, not hands," never posts on your behalf. | **Adopted -- phase 4, monitoring only.** This is the GEO/citability tracking layer from the earlier authority-system strategy, not a lead-scraper. Deploy after the home-base landing page exists (nothing to track citations for yet). Does not touch outreach or lead lists. |

## Sequencing rationale

1. **Bright Data AI Lead Generator first** -- Python-native, builds the actual prospect list from public web/company data, no LinkedIn login friction. Matches "start lead sourcing with a no-signup public data source first" preference.
2. **OpenSDR second** -- once the wedge/niche is proven out via phase 1, add LinkedIn-specific outreach for the same prospect types (agencies, course creators, SaaS companies).
3. **Enverif third, conditional** -- only once a real list exists worth verifying before spending outreach effort on dead emails.
4. **UnifAPI last, monitoring-only** -- once the home-base landing page exists, track whether AI assistants cite it/you for niche queries. No lead data flows through this tool; it's pure visibility monitoring.

## Explicit non-goals

- No tool here writes to CRM or sends outreach autonomously without review -- all four (when wired) produce lists/drafts for human review, consistent with the "top players" ethical framing discussed earlier (leverage, not spam/manipulation).
- Trading-related data sourcing (market intelligence, financial signals) is explicitly out of scope for this file and this repo.
