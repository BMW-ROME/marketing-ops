#!/bin/sh
# Waits for the Ollama service to be reachable before starting Streamlit.
# The app hard-stops at startup if Ollama is unreachable (lead_generator.py).
set -e

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://ollama:11434}"

echo "Waiting for Ollama at ${OLLAMA_BASE_URL} ..."
until curl -sf -o /dev/null "${OLLAMA_BASE_URL}/api/tags"; do
  sleep 2
done
echo "Ollama is up. Starting app."

exec "$@"