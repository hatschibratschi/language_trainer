#!/usr/bin/env bash
# Parla in the test setup, the one the browser tests (tests/ui) use:
#   http://127.0.0.1:7871, fresh empty data directory, no login,
#   Ollama and parla-speech pointed at a dead port ("Mac Mini off").
# Run it yourself to look at the test app in your browser; stop with Ctrl-C.
set -euo pipefail
cd "$(dirname "$0")/.."

DEAD=http://127.0.0.1:9  # nothing listens there
export GRADIO_SERVER_NAME=127.0.0.1
export GRADIO_SERVER_PORT=7871
export PARLA_DATA_DIR="${PARLA_TEST_DATA:-$(mktemp -d -t parla-test)}"
export PARLA_OPEN_BROWSER="${PARLA_OPEN_BROWSER:-1}"
export OLLAMA_HOST=$DEAD PARLA_SPEECH_HOST=$DEAD
unset PARLA_ORIGIN

echo "Parla test setup: http://127.0.0.1:7871  (data: $PARLA_DATA_DIR)"
exec uv run --quiet python -m parla.app
