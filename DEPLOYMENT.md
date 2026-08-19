# DEPLOYMENT.md

Runbook for self-hosting the marketing-ops stack with Docker Compose:
**lead-gen Streamlit app + Ollama (sidecar) + n8n (host-only)**.

The stack is designed to run on a small, always-on host (e.g. a free-tier
VM) so scraping/qualification work leaves your laptop. Qualification stays
**local to the host** -- the code intentionally refuses to send lead data to
a cloud LLM (see `lead-gen/lead_generator.py`). If that constraint ever
changes, this doc changes with it.

## What you get

| Service  | Container | Port (host) | Purpose |
|---|---|---|---|
| leadgen  | `marketing-ops-leadgen` | 8501 | Streamlit UI: trigger Bright Data scrape, qualify via Ollama, ranked lead list |
| ollama   | `marketing-ops-ollama`  | (internal) | Local LLM inference for qualification, models in a named volume |
| n8n      | `marketing-ops-n8n`    | 5678 | Your existing automation layer (form -> auto-reply -> CRM). Hosted here only; workflows are imported separately, not scaffolded by this repo |

Persistent data lives in named volumes: `marketing-ops_ollama-models`,
`marketing-ops_n8n-data` (back up these -- see below).

## Choosing a host

Ollama is the sizing constraint: `llama3.1:8b` wants ~8 GB RAM + a few GB
for the model files. Options, honest ranking:

| Option | Cost | Works? | Notes |
|---|---|---|---|
| Oracle Cloud Always Free VM (AMD 4 OCPU / 24 GB RAM) | Free | **Yes** | The only genuinely free option big enough to run 8b-class models comfortably. Deploy Ubuntu 24.04 LTS, install Docker, follow Quick start. ARM 4 OCPU/24 GB also works. |
| Google Cloud free tier (e2-micro, 1 GB RAM) | Free | Marginal | Too small for 8b models. Only realistic with a 1.5b-class model (`qwen2.5:1.5b`) -- not recommended. |
| Streamlit Community Cloud / Railway / Render free tier | Free | **No** | Cannot run Ollama as a sidecar; the app hard-stops without it. |
| A cheap VPS (Hetzner, etc.) | ~4-8 USD/mo | Yes | Fine if you outgrow free tiers. |
| Your laptop (for dev only) | Local | Yes | `docker compose up -d` works locally too, but the point of this stack is moving off it. |

## Prerequisites (on the host)

- Docker Engine 24+ with the compose plugin (`docker compose version` works)
- Git
- Your Bright Data API token, **rotated** (the one shared in a past chat
  session is treated as compromised -- rotate at
  https://brightdata.com/cp/setting before first use)
- A Bright Data Collector ID (starts with `c_`, from Scraper Studio) --
  see `lead-gen/README.md` if you haven't built one yet

## Quick start

```bash
git clone https://github.com/BMW-ROME/marketing-ops.git
cd marketing-ops

cp lead-gen/.env.template .env
# Edit .env: set BRIGHT_DATA_API_TOKEN, BRIGHT_DATA_COLLECTOR_ID.
# OLLAMA_BASE_URL in .env is NOT used by the compose stack -- compose
# overrides it to http://ollama:11434 automatically.

docker compose up -d --build

docker compose exec ollama ollama pull llama3.1:8b   # first time only
```

Verify:

```bash
curl -f http://localhost:8501/_stcore/health   # "ok" -- Streamlit is up
curl -f http://localhost:5678                  # n8n UI
docker compose logs -f leadgen                 # should show "Ollama is up. Starting app."
```

Then open `http://<host-ip>:8501`.

## Configuration

Everything is driven by the `.env` file next to `compose.yaml`
(never commit it -- it's gitignored):

| Variable | Used by | Notes |
|---|---|---|
| `BRIGHT_DATA_API_TOKEN` | leadgen | **Required**; `compose up` fails fast with a clear error if missing |
| `BRIGHT_DATA_COLLECTOR_ID` | leadgen | Optional here (can be typed in the UI), recommended to set |
| `OLLAMA_MODEL` | leadgen | Default `llama3.1:8b`; the app lists models actually pulled in Ollama, so it must match one you pulled |
| `N8N_HOST` / `N8N_PROTOCOL` | n8n | Set before first n8n startup if you plan to reach it by domain name |

Changing `.env` after first deploy: `docker compose up -d` again.

## Ollama model management

```bash
docker compose exec ollama ollama pull llama3.1:8b     # pull a model
docker compose exec ollama ollama list                 # models present
docker compose exec ollama ollama rm <model>           # free disk
```

Models persist in the `ollama-models` volume across container recreation.

## n8n -- hosted, not scaffolded

This repo only *hosts* n8n. Your lead-funnel workflows
(form -> auto-reply -> CRM, matching `lead_capture.yaml` intake questions)
live in the `n8n-data` volume and are managed from the UI on port 5678.

Migrating from a local n8n instance:
1. On the old instance: export workflows (UI: Workflows -> ... -> Download,
   or the n8n CLI `export:workflow`).
2. On the host: open `http://<host-ip>:5678`, create a new owner account,
   and import the exported JSON.

If external services (webhooks from a landing page, email triggers) must
reach n8n, it needs a public inbound path -- a domain with `N8N_HOST` set,
plus a reverse proxy. Caddy is the recommended free option (TLS
auto-provisioned, ~10 lines of config). Not included in compose by design
-- add it when you have a domain.

## Backups

```bash
# Stop the stack, tar the volumes off-box, restart.
docker compose down
docker run --rm -v marketing-ops_ollama-models:/data -v "$PWD/backups":/backup \
  alpine tar czf /backup/ollama-models-$(date +%F).tar.gz -C /data .
docker run --rm -v marketing-ops_n8n-data:/data -v "$PWD/backups":/backup \
  alpine tar czf /backup/n8n-data-$(date +%F).tar.gz -C /data .
docker compose up -d
```

Restoring: extract the archive into the volume container, then `docker
compose up -d`.

## Security checklist

- [ ] Bright Data token rotated (any version ever shown in a chat = compromised)
- [ ] Token lives only in the host `.env` -- never in git, never in the image
- [ ] Host firewall exposes only 22, 8501, 5678 (or put everything behind a
      reverse proxy / VPN; do not expose 11434 -- Ollama has no auth)
- [ ] n8n owner account uses a strong password on first login
- [ ] Root `.gitignore` is in place so `.env` cannot be committed by accident
      (`git check-ignore lead-gen/.env` should print the path)

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `compose up` fails: "required variable BRIGHT_DATA_API_TOKEN is missing" | `.env` missing or empty; `cp lead-gen/.env.template .env` and fill it in |
| leadgen logs loop "Waiting for Ollama..." | Ollama container unhealthy/restarting; `docker compose ps` and `docker compose logs ollama` |
| UI shows "Cannot reach Ollama at ..." | Entrypoint waits on startup, but if Ollama dies later the app shows this; restart the stack |
| 401 Unauthorized in the UI | Token wrong/revoked -- re-copy from https://brightdata.com/cp/setting |
| 404 Not Found for collector | Collector ID typo or wrong account |
| 422 Unprocessable Entity | Input objects don't match the collector's input schema (see lead-gen README) |
| App is slow on first run | Model still loading into memory; subsequent runs are warm |
| Backup restore fails on Windows | Tar POSIX perms vs Windows; do backups/restores on the Linux host |

## Out of scope (intentionally)

- Landing page (BUILD_PLAN.md Phase C) -- remains blocked on the Chatterbox swap
- Chatterbox voice-clone rework (youtube-engine repo, Phase B)
- OpenSDR / Enverif / UnifAPI lead toolstack phases (TOOLS.md)
- n8n workflow construction -- hosted here, owned in your n8n UI