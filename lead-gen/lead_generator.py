"""
lead-gen/lead_generator.py

Bright Data AI Lead Generator (phase 1 of the tool stack -- see ../TOOLS.md).

Uses Bright Data's Scraper Studio Collection API (/dca/trigger + /dca/dataset)
to run a published collector against target inputs, then scores each result
against the Ideal Customer Profile in icp.yaml using a LOCAL Ollama model via
LangChain, and surfaces a ranked, outreach-ready lead list via Streamlit.

Qualification runs entirely on local Ollama models (e.g. llama3.1:8b,
qwen2.5:7b) -- no OpenAI dependency, no per-token cost, no data leaving the
local machine for the qualification step. Only the Bright Data scrape step
calls an external API.

API REFERENCE (see https://docs.brightdata.com/datasets/scraper-studio/quickstart):
    1. POST /dca/trigger?collector={collector_id}&queue_next=1
       Body: JSON array of input objects matching the collector's input
       schema (commonly a "url" field, but can be any field the collector
       defines). Response: {"collection_id": "j_..."}
    2. GET /dca/dataset?id={collection_id}
       Poll until the response is a JSON array (not a status object like
       {"status": "building"}). That array is the scraped dataset.

    NOTE: the trigger response field is called "collection_id", but every
    other endpoint refers to the same value as "snapshot_id" -- they are the
    same string under two names. This module uses "snapshot_id" internally
    for consistency with the rest of the codebase.

PREREQUISITES:
    - A Bright Data account with a payment method on file
    - An API token from https://brightdata.com/cp/setting (Account Settings -> API Tokens)
    - A Collector ID (starts with "c_") from a scraper built in Bright Data's
      Scraper Studio (CLI, AI Agent, or IDE) -- NOT a raw "dataset_id" as
      earlier drafts of this file assumed. Build one at
      https://brightdata.com/cp/scrapers before running this app.

SECURITY NOTE:
    BRIGHT_DATA_API_TOKEN is read from environment variables (via .env,
    never committed) or Streamlit secrets. Never hardcode credentials in
    this file. If a token is ever pasted into a chat, notebook, or
    committed by mistake, rotate it immediately at
    https://brightdata.com/cp/setting.

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
BRIGHT_DATA_COLLECTOR_ID = os.environ.get("BRIGHT_DATA_COLLECTOR_ID", "")
ICP_CONFIG_PATH = os.environ.get("ICP_CONFIG_PATH", "./icp.yaml")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

BRIGHT_DATA_TRIGGER_URL = "https://api.brightdata.com/dca/trigger"
BRIGHT_DATA_DATASET_URL = "https://api.brightdata.com/dca/dataset"
BRIGHT_DATA_POLL_INTERVAL_SECONDS = 5
BRIGHT_DATA_POLL_TIMEOUT_SECONDS = 300  # batch jobs can take several minutes
BRIGHT_DATA_MAX_RETRIES = 3


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
    collector_id: str,
    inputs: List[Dict[str, Any]],
    token: str = BRIGHT_DATA_API_TOKEN,
) -> str:
    """
    Triggers a Bright Data Scraper Studio collector run and returns the
    snapshot_id (returned by the API as "collection_id") used to poll for
    results.

    collector_id: the Bright Data Collector ID (starts with "c_"), from a
                  scraper you built in Scraper Studio -- NOT a free-text
                  query. Build one at https://brightdata.com/cp/scrapers.
    inputs: list of input objects matching the collector's input schema.
            Most collectors expect [{"url": "..."}], but check the
            collector's "Inputs" tab for the exact schema it was built with.
    """
    if not token:
        raise RuntimeError(
            "BRIGHT_DATA_API_TOKEN is not set. Add it to lead-gen/.env "
            "(see .env.template) -- never hardcode it in source."
        )
    if not collector_id:
        raise RuntimeError(
            "No Collector ID provided. Build a collector in Bright Data's "
            "Scraper Studio (https://brightdata.com/cp/scrapers) and use "
            "its ID (starts with 'c_')."
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = f"{BRIGHT_DATA_TRIGGER_URL}?collector={collector_id}&queue_next=1"

    last_exc: Optional[Exception] = None
    for attempt in range(BRIGHT_DATA_MAX_RETRIES):
        try:
            resp = requests.post(url, headers=headers, json=inputs, timeout=30)
            if resp.status_code == 401:
                raise RuntimeError(
                    "401 Unauthorized -- BRIGHT_DATA_API_TOKEN is missing, "
                    "malformed, or revoked. Re-copy from "
                    "https://brightdata.com/cp/setting"
                )
            if resp.status_code == 404:
                raise RuntimeError(
                    f"404 Not Found -- Collector ID '{collector_id}' does not "
                    "exist or your account lacks access. Re-copy the ID from "
                    "https://brightdata.com/cp/scrapers"
                )
            if resp.status_code == 422:
                raise RuntimeError(
                    "422 Unprocessable Entity -- input objects don't match "
                    "this collector's input schema. Check the 'Inputs' tab "
                    "of your collector in Scraper Studio."
                )
            resp.raise_for_status()
            data = resp.json()
            snapshot_id = data.get("collection_id")
            if not snapshot_id:
                raise RuntimeError(f"Bright Data trigger response missing collection_id: {data}")
            return snapshot_id
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)  # exponential backoff: 1s, 2s, 4s
                continue
            raise
    raise RuntimeError(f"Bright Data trigger failed after {BRIGHT_DATA_MAX_RETRIES} attempts: {last_exc}")


def poll_bright_data_snapshot(
    snapshot_id: str,
    token: str = BRIGHT_DATA_API_TOKEN,
    poll_interval: int = BRIGHT_DATA_POLL_INTERVAL_SECONDS,
    timeout: int = BRIGHT_DATA_POLL_TIMEOUT_SECONDS,
) -> List[Dict[str, Any]]:
    """
    Polls /dca/dataset until the snapshot is ready, then returns the scraped
    records. The endpoint returns a status object (e.g. {"status": "building"})
    while in progress, and a JSON array when ready.
    """
    headers = {"Authorization": f"Bearer {token}"}
    elapsed = 0

    while elapsed < timeout:
        resp = requests.get(
            BRIGHT_DATA_DATASET_URL, params={"id": snapshot_id}, headers=headers, timeout=30
        )
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, list):
            return body
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
    collector_id: str,
    inputs: List[Dict[str, Any]],
    persona: Dict[str, Any],
    model: str = OLLAMA_MODEL,
) -> List[Dict[str, Any]]:
    """End-to-end: trigger scrape -> poll -> qualify each record locally via Ollama."""
    snapshot_id = trigger_bright_data_scrape(collector_id, inputs)
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


def _parse_inputs_textarea(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parses the Streamlit textarea (one URL per line) into the input objects
    Bright Data expects. Defaults to {"url": ...} shape -- adjust if your
    collector's input schema uses different field names.
    """
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    return [{"url": line} for line in lines]


def render_app():
    st.set_page_config(page_title="Lead Generator (Bright Data + Local Ollama)", layout="wide")
    st.title("Voice-Acting Brand -- Lead Generator")
    st.caption(
        "Phase 1 of the lead-gen tool stack (see marketing-ops/TOOLS.md). "
        "Scrapes via Bright Data Scraper Studio; qualifies locally via Ollama."
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

    collector_id = st.text_input(
        "Bright Data Collector ID",
        value=BRIGHT_DATA_COLLECTOR_ID,
        help=(
            "The Collector ID (starts with 'c_') from a scraper you built in "
            "Bright Data's Scraper Studio (https://brightdata.com/cp/scrapers). "
            "Not a free-text search query -- Scraper Studio collectors are "
            "built against a specific input schema (commonly a list of URLs)."
        ),
    )
    inputs_text = st.text_area(
        "Input URLs (one per line)",
        help=(
            "Most collectors expect a list of target URLs. If your collector "
            "uses a different input schema (e.g. a search keyword field), "
            "adjust _parse_inputs_textarea() to match."
        ),
        height=150,
    )

    if st.button("Run lead generation", type="primary"):
        inputs = _parse_inputs_textarea(inputs_text)
        if not collector_id or not inputs:
            st.warning("Provide both a Collector ID and at least one input URL.")
            st.stop()
        with st.spinner(
            f"Scraping via Bright Data and qualifying locally with {selected_model}... "
            "this can take a minute or more for batch jobs."
        ):
            try:
                results = run_pipeline(collector_id, inputs, persona, model=selected_model)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Pipeline failed: {exc}")
                st.stop()

        results = [r for r in results if not r.get("excluded")]
        results.sort(key=lambda r: r.get("score", 0), reverse=True)

        st.success(f"Qualified {len(results)} lead(s) using local model: {selected_model}")
        for r in results:
            record_label = r["lead_record"].get("name") or r["lead_record"].get("url", "Unknown")
            with st.expander(f"Score {r.get('score', 0)} -- {record_label}"):
                st.write(f"**Matched signals:** {', '.join(r.get('matched_signals', []))}")
                st.write(f"**Rationale:** {r.get('rationale', '')}")
                st.json(r["lead_record"])


if __name__ == "__main__":
    render_app()
