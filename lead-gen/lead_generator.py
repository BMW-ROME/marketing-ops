"""
lead-gen/lead_generator.py

Bright Data AI Lead Generator (phase 1 of the tool stack -- see ../TOOLS.md).

Uses Bright Data's Scraper Studio Collection API (/dca/trigger + /dca/dataset)
to run a published collector against target inputs, then scores each result
against the Ideal Customer Profile in icp.yaml using a LOCAL Ollama model via
LangChain, and surfaces a ranked, outreach-ready lead list via Streamlit.

Qualification runs entirely on local Ollama models (e.g. phi4-mini,
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
    - At least one model pulled, e.g.: `ollama pull phi4-mini`

Usage:
    streamlit run lead_generator.py          # interactive UI (http://localhost:8501)
    python lead_generator.py --urls 'site.com' --limit 15 --output out.csv   # headless CLI
"""

import argparse
import csv
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import streamlit as st
import yaml
from dotenv import load_dotenv

load_dotenv()

BRIGHT_DATA_API_TOKEN = os.environ.get("BRIGHT_DATA_API_TOKEN", "")
BRIGHT_DATA_COLLECTOR_ID = os.environ.get("BRIGHT_DATA_COLLECTOR_ID", "")
DEFAULT_ICP_CONFIG_PATH = str(Path(__file__).resolve().parent / "icp.yaml")
ICP_CONFIG_PATH = os.environ.get("ICP_CONFIG_PATH", DEFAULT_ICP_CONFIG_PATH)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi4-mini:latest")

BRIGHT_DATA_TRIGGER_URL = "https://api.brightdata.com/dca/trigger"
BRIGHT_DATA_DATASET_URL = "https://api.brightdata.com/dca/dataset"
BRIGHT_DATA_POLL_INTERVAL_SECONDS = 5
BRIGHT_DATA_POLL_TIMEOUT_SECONDS = 300  # batch jobs can take several minutes
BRIGHT_DATA_MAX_RETRIES = 3

TERMINAL_SNAPSHOT_STATUSES = {"failed", "error", "cancelled"}

REVIEW_HEADER = [
    "company", "website", "contact_name", "contact_role",
    "contact_email_or_linkedin", "segment", "icp_score", "icp_fit_notes",
    "source", "human_approved", "personalization_note", "demo_link_used",
    "first_contact_date", "follow_up_date", "reply_status", "quote_sent_date",
    "outcome", "revenue", "loss_reason",
]
EXTRA_HEADER = ["matched_signals", "excluded", "parse_error", "lead_record_json"]


def _is_placeholder_token(value: str) -> bool:
    return bool(value) and value.startswith("your_")


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
    if _is_placeholder_token(token):
        raise RuntimeError(
            "BRIGHT_DATA_API_TOKEN still contains the template placeholder "
            "('your_bright_data_api_token_here'). Copy the real rotated token "
            "into lead-gen/.env -- never a placeholder."
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
    start = time.monotonic()

    while time.monotonic() - start < timeout:
        resp = None
        last_exc: Optional[Exception] = None
        for attempt in range(BRIGHT_DATA_MAX_RETRIES):
            try:
                resp = requests.get(
                    BRIGHT_DATA_DATASET_URL,
                    params={"id": snapshot_id},
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                last_exc = None
                break
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                status = resp.status_code if resp is not None else 0
                if 400 <= status < 500:
                    # Non-retryable client error (401, 403, 404, ...)
                    raise
                time.sleep(2 ** attempt)  # backoff: 1s, 2s, 4s
        if last_exc is not None:
            raise last_exc

        body = resp.json()
        if isinstance(body, list):
            return body
        if isinstance(body, dict) and body.get("status") in TERMINAL_SNAPSHOT_STATUSES:
            raise RuntimeError(
                f"Bright Data snapshot {snapshot_id} ended in terminal status "
                f"'{body.get('status')}': {body.get('error') or body}"
            )
        time.sleep(poll_interval)

    raise TimeoutError(f"Bright Data snapshot {snapshot_id} not ready after {timeout}s")


@st.cache_data(ttl=10, show_spinner=False)
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
    Builds a LangChain LCEL chain backed by a LOCAL Ollama model that scores a
    scraped lead record against the ICP signals and returns a structured
    qualification verdict.

    Uses Ollama's JSON mode (format="json") rather than with_structured_output's
    json_schema method, since json_schema support varies across locally-hosted
    models -- JSON mode + explicit prompt formatting instructions is the more
    portable approach across whatever model you have pulled (phi4-mini, llama3.1,
    qwen2.5, mistral, etc.).

    LCEL (prompt | llm | StrOutputParser) is used instead of the deprecated
    LangChain LLMChain, which was removed from the main package in langchain 1.x.
    """
    from langchain_ollama import ChatOllama
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    llm = ChatOllama(
        model=model,
        base_url=base_url,
        temperature=0,
        format="json",  # JSON mode: constrains output to valid JSON
    )

    prompt = ChatPromptTemplate.from_template(
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
    )
    return prompt | llm | StrOutputParser()


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
    inputs = {
        "persona_label": persona.get("label", ""),
        "persona_signals": signals_text,
        "lead_record": json.dumps(lead_record, default=str)[:4000],
    }

    raw = _invoke_qualification(chain, inputs)
    result = _parse_qualification(raw)
    if result is None:
        # Retry once -- local models can transiently emit non-JSON.
        result = _parse_qualification(_invoke_qualification(chain, inputs))

    if result is None:
        return {
            "score": 0,
            "matched_signals": [],
            "rationale": f"Failed to parse local model output: {raw[:200]}",
            "excluded": False,
            "parse_error": True,
            "persona_label": persona.get("label", ""),
            "lead_record": lead_record,
        }

    try:
        score = int(result.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    result["score"] = max(0, min(100, score))
    if not isinstance(result.get("matched_signals"), list):
        result["matched_signals"] = []
    if not isinstance(result.get("rationale"), str):
        result["rationale"] = str(result.get("rationale", ""))
    result["excluded"] = bool(result.get("excluded", False))
    result["parse_error"] = False
    result["persona_label"] = persona.get("label", "")
    result["lead_record"] = lead_record
    return result


def _invoke_qualification(chain, inputs: Dict[str, str]) -> str:
    """Invokes the LCEL chain, returning the raw model string."""
    return chain.invoke(inputs)


def _parse_qualification(raw: str) -> Optional[Dict[str, Any]]:
    """Parses raw model output into a dict, or None if it is not valid JSON."""
    try:
        parsed = json.loads(_strip_code_fences(raw))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def run_pipeline(
    collector_id: str,
    inputs: List[Dict[str, Any]],
    persona: Dict[str, Any],
    model: str = OLLAMA_MODEL,
) -> List[Dict[str, Any]]:
    """End-to-end: trigger scrape -> poll -> qualify each record locally via Ollama."""
    snapshot_id = trigger_bright_data_scrape(collector_id, inputs)
    records = poll_bright_data_snapshot(snapshot_id)
    chain = _get_qualification_chain(model)
    return [qualify_lead(r, persona, chain) for r in records]


@st.cache_resource
def _get_qualification_chain(model: str, base_url: str = OLLAMA_BASE_URL):
    """Cached qualification chain keyed by model/base_url so rebuilds are cheap."""
    return build_qualification_chain(model=model, base_url=base_url)


@st.cache_data(ttl=10, show_spinner=False)
def list_local_ollama_models(base_url: str = OLLAMA_BASE_URL) -> List[str]:
    """Returns model names currently pulled in the local Ollama instance."""
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except requests.RequestException:
        return []


def _normalize_url(value: str) -> str:
    """Strips whitespace and defaults missing schemes to https://."""
    value = value.strip()
    if not value:
        return ""
    if "://" not in value:
        return f"https://{value}"
    return value


def _parse_input_lines(raw_text: str, split_commas: bool = False) -> List[Dict[str, Any]]:
    """
    Parses a block of lines (Streamlit textarea, --urls, --inputs-file) into the
    input objects Bright Data expects. Normalizes URLs (adds https:// if the
    scheme is missing), dedupes, and drops blank lines.

    Defaults to the {"url": ...} shape -- adjust if your collector's input
    schema uses different field names.
    """
    if split_commas:
        raw_text = raw_text.replace(",", "\n")

    seen = set()
    inputs: List[Dict[str, Any]] = []
    for line in raw_text.splitlines():
        url = _normalize_url(line)
        if not url or url.lower() in seen:
            continue
        seen.add(url.lower())
        inputs.append({"url": url})
    return inputs


def _parse_inputs_textarea(raw_text: str) -> List[Dict[str, Any]]:
    """Backwards-compatible alias for _parse_input_lines."""
    return _parse_input_lines(raw_text)


def _pick(record: Dict[str, Any], keys: List[str], default: str = "") -> str:
    """Returns the first non-empty value from record for the candidate keys."""
    for key in keys:
        value = record.get(key)
        if value in (None, ""):
            continue
        return str(value)
    return default


def _result_to_row(result: Dict[str, Any]) -> List[str]:
    """Flattens one qualification result into a review-template-compatible CSV row."""
    rec = result.get("lead_record", {})
    return [
        _pick(rec, ["name", "company", "company_name", "account_name", "business_name"]),
        _pick(rec, ["url", "website", "domain", "link", "site"]),
        _pick(rec, ["contact_name", "person", "first_name"]),
        _pick(rec, ["contact_role", "role", "job_title", "position", "title", "occupation"]),
        _pick(rec, ["email", "contact_email", "linkedin", "linkedin_url", "linkedin_profile"]),
        result.get("persona_label", ""),
        str(result.get("score", 0)),
        result.get("rationale", ""),
        _pick(rec, ["source", "input_url", "source_url"]),
        "",  # human_approved
        "",  # personalization_note
        "",  # demo_link_used
        "",  # first_contact_date
        "",  # follow_up_date
        "",  # reply_status
        "",  # quote_sent_date
        "",  # outcome
        "",  # revenue
        "",  # loss_reason
        "; ".join(result.get("matched_signals", [])),
        str(bool(result.get("excluded", False))),
        str(bool(result.get("parse_error", False))),
        json.dumps(rec, default=str),
    ]


def _write_leads_csv(results: List[Dict[str, Any]], path: str) -> None:
    """Writes qualification results to a CSV matching LEAD_REVIEW_TEMPLATE.csv."""
    out_dir = Path(path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(REVIEW_HEADER + EXTRA_HEADER)
        for result in results:
            writer.writerow(_result_to_row(result))


def _leads_csv_bytes(results: List[Dict[str, Any]]) -> str:
    """Returns qualification results as a CSV string (for the UI download button)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(REVIEW_HEADER + EXTRA_HEADER)
    for result in results:
        writer.writerow(_result_to_row(result))
    return buf.getvalue()


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
    if _is_placeholder_token(BRIGHT_DATA_API_TOKEN):
        st.error(
            "BRIGHT_DATA_API_TOKEN is still the template placeholder "
            "('your_bright_data_api_token_here'). Set the real rotated token "
            "in lead-gen/.env -- never leave a placeholder."
        )
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
            "`ollama pull phi4-mini` first."
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

    pipeline_running = st.session_state.get("pipeline_running", False)
    if st.button("Run lead generation", type="primary", disabled=pipeline_running):
        inputs = _parse_inputs_textarea(inputs_text)
        if not collector_id or not inputs:
            st.warning("Provide both a Collector ID and at least one input URL.")
            st.stop()
        st.session_state["pipeline_running"] = True
        try:
            with st.status(
                f"Scraping via Bright Data and qualifying locally with {selected_model}...",
                expanded=True,
            ) as status:
                try:
                    results = run_pipeline(collector_id, inputs, persona, model=selected_model)
                    status.update(label="Qualification complete.", state="complete")
                except Exception as exc:  # noqa: BLE001
                    status.update(label=f"Pipeline failed: {exc}", state="error")
                    st.session_state["pipeline_running"] = False
                    st.stop()
        finally:
            st.session_state["pipeline_running"] = False

        results = [r for r in results if not r.get("excluded")]
        results.sort(key=lambda r: r.get("score", 0), reverse=True)

        parse_failures = [r for r in results if r.get("parse_error")]
        if parse_failures:
            st.warning(
                f"{len(parse_failures)} row(s) could not be parsed by the local model "
                "and were kept with score 0 (see 'parse_error' column in the CSV)."
            )

        st.success(f"Qualified {len(results)} lead(s) using local model: {selected_model}")
        st.download_button(
            "Download lead list (CSV)",
            data=_leads_csv_bytes(results),
            file_name=f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
        for r in results:
            record_label = r["lead_record"].get("name") or r["lead_record"].get("url", "Unknown")
            with st.expander(f"Score {r.get('score', 0)} -- {record_label}"):
                if r.get("parse_error"):
                    st.warning("Local model output could not be parsed as JSON.")
                st.write(f"**Matched signals:** {', '.join(r.get('matched_signals', []))}")
                st.write(f"**Rationale:** {r.get('rationale', '')}")
                st.json(r["lead_record"])


def run_cli(args: argparse.Namespace) -> None:
    """Headless pipeline: trigger scrape -> poll -> qualify -> write CSV."""
    token = args.token or os.environ.get("BRIGHT_DATA_API_TOKEN", BRIGHT_DATA_API_TOKEN)
    collector_id = args.collector_id or os.environ.get(
        "BRIGHT_DATA_COLLECTOR_ID", BRIGHT_DATA_COLLECTOR_ID
    )

    if not token:
        raise SystemExit("BRIGHT_DATA_API_TOKEN is not set. Add it to lead-gen/.env.")
    if _is_placeholder_token(token):
        raise SystemExit(
            "BRIGHT_DATA_API_TOKEN is still the template placeholder. "
            "Set the real rotated token in lead-gen/.env."
        )
    if not collector_id:
        raise SystemExit(
            "No Collector ID provided. Pass --collector-id or set "
            "BRIGHT_DATA_COLLECTOR_ID in lead-gen/.env."
        )
    if _is_placeholder_token(collector_id):
        raise SystemExit(
            "BRIGHT_DATA_COLLECTOR_ID is still the template placeholder "
            "(your_collector_id_here). Set your real Collector ID."
        )

    raw_inputs = args.urls or ""
    if args.inputs_file:
        raw_inputs += "\n" + Path(args.inputs_file).read_text(encoding="utf-8")
    if not raw_inputs.strip():
        raw_inputs = os.environ.get("BRIGHT_DATA_INPUT_URLS", "")
    inputs = _parse_input_lines(raw_inputs, split_commas=True)
    if not inputs:
        raise SystemExit(
            "No input URLs provided. Pass --urls 'example.com,other.com', "
            "--inputs-file FILE, or set BRIGHT_DATA_INPUT_URLS in .env."
        )

    icp = load_icp()
    personas = icp.get("target_personas", [])
    label = args.persona or (personas[0]["label"] if personas else "")
    persona = next((p for p in personas if p["label"] == label), None)
    if persona is None:
        raise SystemExit(f"Persona '{label}' not found in icp.yaml.")

    model = args.model or OLLAMA_MODEL
    print(
        f"Triggering Bright Data scrape for {len(inputs)} input(s), "
        f"persona '{label}', model '{model}' ..."
    )
    results = run_pipeline(collector_id, inputs, persona, model=model)

    results = [r for r in results if not r.get("excluded")]
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    if args.limit:
        results = results[: args.limit]

    output = args.output or str(
        Path("output") / f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    _write_leads_csv(results, output)
    parse_errors = sum(1 for r in results if r.get("parse_error"))
    print(
        f"Qualified {len(results)} lead(s) (excluded filtered; "
        f"parse errors: {parse_errors}). CSV written to {output}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lead_generator.py",
        description=(
            "Bright Data AI Lead Generator: scrape via Scraper Studio, qualify "
            "locally via Ollama against icp.yaml, write a ranked CSV."
        ),
    )
    parser.add_argument("--collector-id", default=None, help="Bright Data Collector ID (c_...).")
    parser.add_argument("--persona", default=None, help="ICP persona label (default: first in icp.yaml).")
    parser.add_argument("--urls", default=None, help="Comma-separated input URLs.")
    parser.add_argument("--inputs-file", default=None, help="File with one input URL per line.")
    parser.add_argument("--limit", type=int, default=None, help="Max results to write (default: all).")
    parser.add_argument("--output", default=None, help="Output CSV path (default: output/leads_<timestamp>.csv).")
    parser.add_argument("--model", default=None, help="Ollama model for qualification (default: OLLAMA_MODEL).")
    parser.add_argument("--token", default=None, help="Bright Data API token (prefer .env).")

    args, _ = parser.parse_known_args()

    cli_requested = any(
        value is not None
        for value in (
            args.collector_id,
            args.persona,
            args.urls,
            args.inputs_file,
            args.limit,
            args.output,
            args.model,
            args.token,
        )
    )

    if cli_requested:
        run_cli(args)
    else:
        render_app()


if __name__ == "__main__":
    main()
