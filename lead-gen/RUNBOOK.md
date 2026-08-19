# LeadGen Runbook

This is the operating procedure for `lead-gen/lead_generator.py` (Bright Data discovery + local Ollama ICP qualification), aligned with the existing `marketing-ops` repo goal: convert YouTube/brand content and direct discovery into qualified, human-approved outreach.

## 0. Prerequisites (one-time)

1. Python 3.10+ and PowerShell available locally.
2. A **rotated** Bright Data API token and your Scraper Studio Collector ID (confirm rotation happened in the Bright Data dashboard before proceeding).
3. [Ollama](https://ollama.com) installed and running locally with a pulled model (e.g. `ollama pull phi4-mini`).
4. Clone this repo locally:
   ```powershell
   git clone https://github.com/BMW-ROME/marketing-ops.git
   cd marketing-ops\lead-gen
   ```

## 1. Setup

```powershell
.\setup.ps1
```

This creates a virtual environment, installs dependencies, and copies `.env.template` to `.env` (git-ignored). Edit `.env` and fill in:

- `BRIGHT_DATA_API_TOKEN` — your **rotated** token, never the one previously committed.
- `BRIGHT_DATA_COLLECTOR_ID`
- `OLLAMA_BASE_URL` / `OLLAMA_MODEL` if different from defaults.
- `FALLBACK_CONTACT_METHOD` — your direct contact email.
- `BRIGHT_DATA_INPUT_URLS` — comma-separated seed URLs for the headless CLI
  (used by `./run.ps1` when no `--urls` / `--inputs-file` is passed; the
  Streamlit UI takes URLs from its text area instead).

Never commit `.env`. It is excluded via `.gitignore`.

## 2. Smoke test (required before any full run)

```powershell
.\run.ps1 -SmokeTest
```

This pulls a small batch (~15 leads) end-to-end: Bright Data trigger → dataset retrieval → Ollama ICP scoring against `icp.yaml` → CSV written to `output/smoke_test_leads.csv` (git-ignored).

**Pass condition:** the CSV contains company, source URL, segment, ICP score/reason, and contact info where available, for most rows.

If it fails: check the specific broken interface (Bright Data auth/collector ID, or Ollama reachability/model name) — don't rebuild the pipeline.

## 3. Manual review and ICP calibration

Copy each smoke-test row into `LEAD_REVIEW_TEMPLATE.csv` and hand-label `icp_fit_notes` as: good fit / borderline / not a fit / no reachable contact / compliance concern.

Use this to tune `icp.yaml` — adjust criteria based on real false positives/negatives, not assumptions.

## 4. Scale to weekly batches

Once the smoke test and calibration look right:

```powershell
.\run.ps1
```

Target ~20-30 qualified candidates per weekly batch. Do not scrape or contact at high volume — the value here is targeting and relevance.

## 5. Human-approved outreach only

For every lead marked `human_approved = yes` in your review sheet:

- Send a short, personalized message referencing something specific about their content/business.
- Link one relevant demo and the landing page / direct contact method.
- Log `first_contact_date`.
- One follow-up after 5-7 business days if no reply, then stop.

## 6. Track outcomes and feed back

Update `reply_status`, `quote_sent_date`, `outcome`, `revenue`, and `loss_reason` for every contacted lead. Review weekly:

- Which segment replies most?
- Which source (YouTube vs. discovery vs. referral) converts?
- Which ICP score band actually becomes real work?

Feed findings back into `icp.yaml` and your YouTube CTA copy — not into more tooling.

## Security notes

- The Bright Data token previously committed to `.env.template` must be treated as compromised. Confirm rotation before running anything against production Bright Data usage.
- `.env`, generated lead CSVs/JSON, and anything under `lead-gen/output/` are git-ignored by design — they may contain personal/contact data.
- Run `git status` before any `git add`/commit in this folder to make sure you're not about to stage `.env` or output files.
