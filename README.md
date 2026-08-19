# marketing-ops

Marketing & ops layer: shared brand identity, lead-gen funnel, and content
strategy across YouTube, n8n, and the voice-acting brand.

## What lives here

| File | Purpose |
|---|---|
| `brand_identity.yaml` | Canonical brand tone, bio, niches, language rules (single source of truth) |
| `lead_capture.yaml` | CTA copy, intake questions, funnel destination config |
| `lead-gen/` | Bright Data + local Ollama lead qualification app (Streamlit) |
| `BUILD_PLAN.md` | Sequenced build plan / what's next |
| `INTEGRATION.md` | Wiring status with youtube-engine and other surfaces |
| `TOOLS.md` | Lead-gen tool stack decision log |
| `VOICE_CLONE_MIGRATION.md` | ElevenLabs -> Chatterbox swap target spec |
| `DEPLOYMENT.md` | Runbook for the self-hosted Docker stack |

## Deployment

The deployable app is `lead-gen/` (Streamlit). It ships as a Docker Compose
stack: **leadgen + Ollama sidecar + n8n (host-only)** -- designed to run on
a free-tier VM so scraping/qualification work leaves your laptop.

```bash
cp lead-gen/.env.template .env   # fill in BRIGHT_DATA_API_TOKEN (rotated!)
docker compose up -d --build
docker compose exec ollama ollama pull phi4-mini   # default qualification model
```

Full runbook, host options, backups, and troubleshooting:
**[DEPLOYMENT.md](DEPLOYMENT.md)**.

## Local development

```bash
cd lead-gen
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.template .env                          # fill in
streamlit run lead_generator.py                # http://localhost:8501
```