# lead-gen/README.md

Scaffold for the **Bright Data Scraper Studio + local Ollama** lead-gen
integration (see `../TOOLS.md` for the full tool-stack decision log).

## What this is

A Python + Streamlit app that:
1. Triggers a Bright Data Scraper Studio collector against a list of input
   URLs (or whatever input schema your collector defines)
2. Polls for the scraped dataset, then qualifies/scores each result using a
   LOCAL Ollama model against the ICP defined in `icp.yaml`
3. Outputs a ranked, outreach-ready lead list

This is **phase 1** of the lead-gen tool stack. It does not send any
outreach itself -- it produces a reviewed list for you (or a downstream n8n
workflow) to act on.

## IMPORTANT: you need a Collector, not just a dataset ID

Bright Data's current API (Scraper Studio) requires you to first **build a
collector** -- a published scraper definition -- before you can trigger it.
There is no generic "search the web for X" endpoint; a collector is scoped
to a specific site/schema (e.g. "scrape LinkedIn company pages" or "scrape
a list of product pages").

Three ways to build one (pick whichever fits your workflow):

1. **CLI** (fastest if you're comfortable in a terminal): follow
   https://docs.brightdata.com/datasets/scraper-studio/build-with-the-cli --
   run `bdata scraper create <url> "<what to extract>"` and Bright Data's AI
   Agent writes the scraper for you.
2. **AI Agent in the control panel** (no code): describe what to extract in
   natural language at https://brightdata.com/cp/scrapers.
3. **IDE** (full control): https://docs.brightdata.com/datasets/scraper-studio/develop-a-scraper

Once built, copy its Collector ID (starts with `c_`) into
`BRIGHT_DATA_COLLECTOR_ID` in your `.env`.

## Setup

```bash
cd lead-gen
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.template .env
# Fill in BRIGHT_DATA_API_TOKEN and BRIGHT_DATA_COLLECTOR_ID in .env
```

Get your API token from https://brightdata.com/cp/setting (Account Settings
-> API Tokens). **If a token has ever been shared outside your local `.env`
(e.g. pasted into a chat), rotate it immediately from that same page.**

## Configuration

Edit `icp.yaml` to adjust target personas, signals, and exclusions. This
file is intentionally kept in sync with the niches defined in
`../brand_identity.yaml`.

## Running

```bash
streamlit run lead_generator.py
```

In the UI:
1. Pick a target persona (from `icp.yaml`)
2. Paste your Collector ID (or it will pre-fill from `.env`)
3. Paste one input URL per line (adjust `_parse_inputs_textarea()` in
   `lead_generator.py` if your collector's input schema isn't a simple
   `{"url": ...}` shape)
4. Click "Run lead generation"

## How the API actually works (for reference)

1. `POST /dca/trigger?collector={id}&queue_next=1` with a JSON array of
   input objects -> returns `{"collection_id": "j_..."}`
2. `GET /dca/dataset?id={collection_id}` -- poll until the response is a
   JSON array (not a `{"status": "building"}` object) -- that array is your
   scraped dataset.

Full docs: https://docs.brightdata.com/datasets/scraper-studio/quickstart

## Status

- [x] Directory scaffolded
- [x] `icp.yaml` defined from brand_identity.yaml niches
- [x] `requirements.txt` and `.env.template` in place
- [x] `lead_generator.py` implemented against the real Scraper Studio API
      (`/dca/trigger` + `/dca/dataset`), with retry/backoff and clear error
      messages for 401/404/422 responses
- [ ] A real Collector has been built in Bright Data's Scraper Studio --
      NOT YET DONE (account owner action, see above)
- [ ] `BRIGHT_DATA_API_TOKEN` rotated after being shared in a prior chat
      session -- NOT YET DONE (treat previous token as compromised)
- [ ] End-to-end test against live Bright Data + Ollama -- pending the above
- [ ] Wire output into the n8n lead-funnel workflow (CRM logging step) once
      both exist.
