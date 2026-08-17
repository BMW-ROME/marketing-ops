"""
lead-gen/lead_generator.py

Bright Data AI Lead Generator (phase 1 of the tool stack -- see ../TOOLS.md).

Scrapes B2B company/contact data via Bright Data's scraping API, scores
each result against the Ideal Customer Profile in icp.yaml using OpenAI +
LangChain, and surfaces a ranked, outreach-ready lead list via Streamlit.

SECURITY NOTE:
    BRIGHT_DATA_API_TOKEN and OPENAI_API_KEY are read from environment
    variables (via .env, never committed) or Streamlit secrets. Never
    hardcode credentials in this file. If a token is ever pasted into a
    chat, notebook, or committed by mistake, rotate it immediately in the
    Bright Data / OpenAI dashboard.

Usage:
    streamlit run lead_generator.py
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import streamlit as st
import yaml
from dotenv import load_dotenv

load_dotenv()

BRIGHT_DATA_API_TOKEN = os.environ.get("BRIGHT_DATA_API_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ICP_CONFIG_PATH = os.environ.get("ICP_CONFIG_PATH", "./icp.yaml")

BRIGHT_DATA_TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"
BRIGHT_DATA_SNAPSHOT_URL = "https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}"
BRIGHT_DATA_POLL_INTERVAL_SECONDS = 5
BRIGHT_DATA_POLL_TIMEOUT_SECONDS = 180


def load_icp(path: str = ICP_CONFIG_PATH) -> Dict[str, Any]:
    """Load the Ideal Customer Profile config (target personas, signals, exclusions)."""
    icp_path = Path(path)
    if not icp_path.exists():
        raise FileNotFoundError(
            f"ICP config not found at {icp_path.resolve()}. "
            "Copy/edit icp.yaml before running this app."
        )
    with open(icp_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def trigger_bright_data_scrape(
    dataset_id: str,
    search_query: str,
    token: str = BRIGHT_DATA_API_TOKEN,
) -> str:
    """
    Triggers a Bright Data dataset scrape job and returns the snapshot_id
    used to poll for results.

    dataset_id: the Bright Data dataset/collector ID for the target source
                (e.g. a LinkedIn companies dataset, a web-search dataset,
                etc.) -- configure this per the dataset you provision in
                your Bright Data account.
    search_query: free-text query built from an icp.yaml persona description.
    """
    if not token:
        raise RuntimeError(
            "BRIGHT_DATA_API_TOKEN is not set. Add it to lead-gen/.env "
            "(see .env.template) -- never hardcode it in source."
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "dataset_id": dataset_id,
        "input": [{"query": search_query}],
    }
    resp = requests.post(BRIGHT_DATA_TRIGGER_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    snapshot_id = data.get("snapshot_id") or data.get("id")
    if not snapshot_id:
        raise RuntimeError(f"Bright Data trigger response missing snapshot_id: {data}")
    return snapshot_id


def poll_bright_data_snapshot(
    snapshot_id: str,
    token: str = BRIGHT_DATA_API_TOKEN,
    poll_interval: int = BRIGHT_DATA_POLL_INTERVAL_SECONDS,
    timeout: int = BRIGHT_DATA_POLL_TIMEOUT_SECONDS,
) -> List[Dict[str, Any]]:
    """Polls a Bright Data snapshot until ready, then returns the scraped records."""
    headers = {"Authorization": f"Bearer {token}"}
    url = BRIGHT_DATA_SNAPSHOT_URL.format(snapshot_id=snapshot_id)
    elapsed = 0

    while elapsed < timeout:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, list):
                return body
            if body.get("status") == "ready":
                return body.get("data", [])
        time.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(f"Bright Data snapshot {snapshot_id} not ready after {timeout}s")


def build_qualification_chain(openai_api_key: str = OPENAI_API_KEY):
    """
    Builds a LangChain LLMChain that scores a scraped lead record against
    the ICP signals and returns a structured qualification verdict.
    """
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    from langchain.chains import LLMChain

    if not openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to lead-gen/.env "
            "(see .env.template) -- never hardcode it in source."
        )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=openai_api_key)

    prompt = PromptTemplate(
        input_variables=["persona_label", "persona_signals", "lead_record"],
        template=(
            "You are qualifying a scraped B2B lead against an Ideal Customer "
            "Profile persona.\n\n"
            "Persona: {persona_label}\n"
            "Signals that indicate a strong fit:\n{persona_signals}\n\n"
            "Lead record (raw scraped data):\n{lead_record}\n\n"
            "Return a JSON object with exactly these fields:\n"
            '  "score": integer 0-100 (100 = perfect fit)\n'
            '  "matched_signals": list of signal strings that this lead matches\n'
            '  "rationale": one or two sentence explanation\n'
            '  "excluded": true/false -- true if this lead matches an exclusion criterion\n'
            "Respond with ONLY the JSON object, no other text."
        ),
    )
    return LLMChain(llm=llm, prompt=prompt)


def qualify_lead(
    lead_record: Dict[str, Any],
    persona: Dict[str, Any],
    chain,
) -> Dict[str, Any]:
    """Runs a single lead record through the qualification chain for one persona."""
    signals_text = "\n".join(f"- {s}" for s in persona.get("signals", []))
    raw = chain.run(
        persona_label=persona.get("label", ""),
        persona_signals=signals_text,
        lead_record=json.dumps(lead_record, default=str)[:4000],
    )
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "score": 0,
            "matched_signals": [],
            "rationale": f"Failed to parse model output: {raw[:200]}",
            "excluded": False,
        }
    result["persona_label"] = persona.get("label", "")
    result["lead_record"] = lead_record
    return result


def run_pipeline(
    dataset_id: str,
    search_query: str,
    persona: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """End-to-end: trigger scrape -> poll -> qualify each record for one persona."""
    snapshot_id = trigger_bright_data_scrape(dataset_id, search_query)
    records = poll_bright_data_snapshot(snapshot_id)
    chain = build_qualification_chain()
    return [qualify_lead(r, persona, chain) for r in records]


def render_app():
    st.set_page_config(page_title="Lead Generator (Bright Data + OpenAI)", layout="wide")
    st.title("Voice-Acting Brand -- Lead Generator")
    st.caption(
        "Phase 1 of the lead-gen tool stack (see marketing-ops/TOOLS.md). "
        "Scrapes via Bright Data, qualifies via OpenAI against icp.yaml personas."
    )

    if not BRIGHT_DATA_API_TOKEN or not OPENAI_API_KEY:
        st.error(
            "Missing BRIGHT_DATA_API_TOKEN and/or OPENAI_API_KEY. "
            "Set them in lead-gen/.env before running."
        )
        st.stop()

    icp = load_icp()
    persona_labels = [p["label"] for p in icp.get("target_personas", [])]

    selected_label = st.selectbox("Target persona", persona_labels)
    persona = next(p for p in icp["target_personas"] if p["label"] == selected_label)
    st.write("**Signals used for scoring:**")
    for s in persona.get("signals", []):
        st.write(f"- {s}")

    dataset_id = st.text_input(
        "Bright Data dataset ID",
        help="The dataset/collector ID configured in your Bright Data account for this source.",
    )
    search_query = st.text_area(
        "Search query",
        value=persona.get("description", ""),
        help="Free-text query passed to the Bright Data dataset trigger.",
    )

    if st.button("Run lead generation", type="primary"):
        if not dataset_id or not search_query:
            st.warning("Provide both a dataset ID and a search query.")
            st.stop()
        with st.spinner("Scraping and qualifying leads... this can take a minute or two."):
            try:
                results = run_pipeline(dataset_id, search_query, persona)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Pipeline failed: {exc}")
                st.stop()

        results = [r for r in results if not r.get("excluded")]
        results.sort(key=lambda r: r.get("score", 0), reverse=True)

        st.success(f"Qualified {len(results)} lead(s).")
        for r in results:
            with st.expander(f"Score {r.get('score', 0)} -- {r['lead_record'].get('name', 'Unknown')}"):
                st.write(f"**Matched signals:** {', '.join(r.get('matched_signals', []))}")
                st.write(f"**Rationale:** {r.get('rationale', '')}")
                st.json(r["lead_record"])


if __name__ == "__main__":
    render_app()
