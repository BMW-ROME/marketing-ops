# lead-gen/README.md

Scaffold for the **Bright Data AI Lead Generator** integration (see
`../TOOLS.md` for the full tool-stack decision log).

## What this is

A Python + Streamlit app that:
1. Scrapes B2B contact/company data via Bright Data's scraping API, based on
   the target personas defined in `icp.yaml`
2. Qualifies and scores results using OpenAI + LangChain against that ICP
3. Outputs an outreach-ready lead list

This is **phase 1** of the lead-gen tool stack. It does not send any
outreach itself -- it produces a reviewed list for you (or a downstream n8n
workflow) to act on.

## Setup

```bash
cd lead-gen
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.template .env
# Fill in BRIGHT_DATA_API_TOKEN and OPENAI_API_KEY in .env
```

## Configuration

Edit `icp.yaml` to adjust target personas, signals, and exclusions. This
file is intentionally kept in sync with the niches defined in
`../brand_identity.yaml` -- if the niche/wedge decision changes there,
update `icp.yaml` to match.

## Running

```bash
streamlit run lead_generator.py
```

This opens a local Streamlit UI (default `http://localhost:8501`) where you
provide a target persona description (from `icp.yaml`) and the app scrapes,
qualifies, and returns a ranked lead list.

## Status

- [x] Directory scaffolded (this commit)
- [x] `icp.yaml` defined from brand_identity.yaml niches
- [x] `requirements.txt` and `.env.template` in place
- [ ] `lead_generator.py` implementation -- NOT YET WRITTEN. Follow the
      Bright Data reference implementation
      (https://brightdata.com/blog/ai/lead-generation-agent) or the
      open-source repo (https://github.com/brightdata/ai-lead-generator) to
      build this against a real Bright Data account.
- [ ] Wire output into the n8n lead-funnel workflow (CRM logging step) once
      both exist.

## Relationship to other tools in the stack

See `../TOOLS.md` for the full sequencing rationale. This directory only
covers Bright Data (phase 1). OpenSDR (phase 2, LinkedIn-specific), Enverif
(phase 3, email verification), and UnifAPI (phase 4, GEO monitoring) are
documented but not yet scaffolded.
