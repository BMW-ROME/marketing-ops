"""
lead-gen/lead_generator.py

Bright Data AI Lead Generator (phase 1 of the tool stack -- see ../TOOLS.md).

Scrapes B2B company/contact data via Bright Data's scraping API, scores
each result against the Ideal Customer Profile in icp.yaml using a LOCAL
Ollama model via LangChain, and surfaces a ranked, outreach-ready lead list
via Streamlit.

Qualification runs entirely on local Ollama models (e.g. llama3.1:8b,
qwen2.5:7b) -- no OpenAI dependency, no per-token cost, no data leaving the
local machine for the qualification step. Only the Bright Data scrape step
calls an external API.

SECURITY NOTE:
    BRIGHT_DATA_API_TOKEN is read from environment variables (via .env,
    never committed) or Streamlit secrets. Never hardcode credentials in
    this file. If a token is ever pasted into a chat, notebook, or
    committed by mistake, rotate it immediately in the Bright Data
    dashboard.

Requirements:
    - Ollama installed and running locally (default: http://localhost:11434)
    - At least one model pulled, e.g.: `ollama pull llama3.1:8b`

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
ICP_CONFIG_PATH = os.environ.get("ICP_CONFIG_PATH", "./icp.yaml")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

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


def check_ollama_available(base_url: str = OLLAMA_BASE_URL) -> bool:
    """Quick health check that Ollama is running locally before wasting a scrape call."""
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=3)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def build_qualification_chain(
    model: str = OLLAMA_MODEL,
    base_url: str = OLLAMA_BASE_URL,
):
    """
    Builds a LangChain LLMChain backed by a LOCAL Ollama model that scores a
    scraped lead record against the ICP signals and returns a structured
    qualification verdict.

    Uses Ollama's JSON mode (format="json") rather than with_structured_output's
    json_schema method, since json_schema support varies across locally-hosted
    models -- JSON mode + explicit prompt formatting instructions is the more
    portable approach across whatever model you have pulled (llama3.1, qwen2.5,
    mistral, etc.).
    """
    from langchain_ollama import ChatOllama
    from langchain.prompts import PromptTemplate
    from langchain.chains import LLMChain

    llm = ChatOllama(
        model=model,
        base_url=base_url,
        temperature=0,
        format="json",  # JSON mode: constrains output to valid JSON
    )

    prompt = PromptTemplate(
        input_variables=["persona_label", "persona_signals", "lead_record"],
        template=(
            "You are qualifying a scraped B2B lead against an Ideal Customer "
            "Profile persona. Respond with ONLY a valid JSON object, no other "
            "text, no markdown code fences.\n\n"
            "Persona: {persona_label}\n"
            "Signals that indicate a strong fit:\n{persona_signals}\n\n"
            "Lead record (raw scraped data):\n{lead_record}\n\n"
            "Return a JSON object with exactly these fields:\n"
            '  "score": integer 0-100 (100 = perfect fit)\n'
            '  "matched_signals": list of signal strings that this lead matches\n'
            '  "rationale": one or two sentence explanation\n'
            '  "excluded": true or false -- true if this lead matches an exclusion criterion\n'
        ),
    )
    return LLMChain(llm=llm, prompt=prompt)


def _strip_code_fences(text: str) -> str:
    """Local models sometimes wrap JSON in ```json ... ``` even when told not to."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def qualify_lead(
    lead_record: Dict[str, Any],
    persona: Dict[str, Any],
    chain,
) -> Dict[str, Any]:
    """Runs a single lead record through the local qualification chain for one persona."""
    signals_text = "\n".join(f"- {s}" for s in persona.get("signals", []))
    raw = chain.run(
        persona_label=persona.get("label", ""),
        persona_signals=signals_text,
        lead_record=json.dumps(lead_record, default=str)[:4000],
    )
    cleaned = _strip_code_fences(raw)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        result = {
            "score": 0,
            "matched_signals": [],
            "rationale": f"Failed to parse local model output: {raw[:200]}",
            "excluded": False,
        }
    result["persona_label"] = persona.get("label", "")
    result["lead_record"] = lead_record
    return result


def run_pipeline(
    dataset_id: str,
    search_query: str,
    persona: Dict[str, Any],
    model: str = OLLAMA_MODEL,
) -> List[Dict[str, Any]]:
    """End-to-end: trigger scrape -> poll -> qualify each record locally via Ollama."""
    snapshot_id = trigger_bright_data_scrape(dataset_id, search_query)
    records = poll_bright_data_snapshot(snapshot_id)
    chain = build_qualification_chain(model=model)
    return [qualify_lead(r, persona, chain) for r in records]


def list_local_ollama_models(base_url: str = OLLAMA_BASE_URL) -> List[str]:
    """Returns model names currently pulled in the local Ollama instance."""
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except requests.RequestException:
        return []


def render_app():
    st.set_page_config(page_title="Lead Generator (Bright Data + Local Ollama)", layout="wide")
    st.title("Voice-Acting Brand -- Lead Generator")
    st.caption(
        "Phase 1 of the lead-gen tool stack (see marketing-ops/TOOLS.md). "
        "Scrapes via Bright Data; qualifies locally via Ollama (no OpenAI, no per-token cost)."
    )

    if not BRIGHT_DATA_API_TOKEN:
        st.error("Missing BRIGHT_DATA_API_TOKEN. Set it in lead-gen/.env before running.")
        st.stop()

    if not check_ollama_available():
        st.error(
            f"Cannot reach Ollama at {OLLAMA_BASE_URL}. Make sure Ollama is running "
            "(`ollama serve` or the Ollama desktop app) before using this tool."
        )
        st.stop()

    available_models = list_local_ollama_models()
    if not available_models:
        st.warning(
            "Ollama is reachable but no models are pulled. Run e.g. "
            "`ollama pull llama3.1:8b` first."
        )
        st.stop()

    default_index = (
        available_models.index(OLLAMA_MODEL) if OLLAMA_MODEL in available_models else 0
    )
    selected_model = st.sidebar.selectbox(
        "Local Ollama model (for qualification)", available_models, index=default_index
    )

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
        with st.spinner(
            f"Scraping via Bright Data and qualifying locally with {selected_model}... "
            "this can take a minute or two."
        ):
            try:
                results = run_pipeline(dataset_id, search_query, persona, model=selected_model)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Pipeline failed: {exc}")
                st.stop()

        results = [r for r in results if not r.get("excluded")]
        results.sort(key=lambda r: r.get("score", 0), reverse=True)

        st.success(f"Qualified {len(results)} lead(s) using local model: {selected_model}")
        for r in results:
            with st.expander(f"Score {r.get('score', 0)} -- {r['lead_record'].get('name', 'Unknown')}"):
                st.write(f"**Matched signals:** {', '.join(r.get('matched_signals', []))}")
                st.write(f"**Rationale:** {r.get('rationale', '')}")
                st.json(r["lead_record"])


if __name__ == "__main__":
    render_app()
