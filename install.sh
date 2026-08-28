#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

if ! command -v pdftotext >/dev/null 2>&1; then
    echo "WARNING: pdftotext not found (poppler-utils). PDF extraction will fail." >&2
    echo "  Debian/Ubuntu: sudo apt-get install poppler-utils" >&2
fi

echo "Setting up venv..."
python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

# Everything that's per-person/per-deployment lives in .env, and only there --
# per env var, or interactively here. Nothing gets written into the repo
# (.env is gitignored).
ENV_FILE="${PROJECT_ROOT}/.env"
if [ -f "$ENV_FILE" ]; then
    echo ".env already exists, leaving it as-is."
else
    : "${LLM_BASE_URL:=}"
    : "${LLM_API_KEY:=}"
    : "${LLM_MODEL_NAME:=local-devstral-small2}"

    if [ -z "$LLM_BASE_URL" ]; then
        read -r -p "LLM base URL (e.g. https://your-endpoint.example.com/v1): " LLM_BASE_URL
    fi
    if [ -z "$LLM_API_KEY" ]; then
        read -r -s -p "API key: " LLM_API_KEY
        echo
    fi

    cat > "$ENV_FILE" <<EOF
LLM_BASE_URL=${LLM_BASE_URL}
LLM_API_KEY=${LLM_API_KEY}
LLM_MODEL_NAME=${LLM_MODEL_NAME}
EOF
    echo "Wrote ${ENV_FILE}"
fi

echo
echo "Setup complete. Activate with: source venv/bin/activate"
echo "Or run the CLI directly, e.g.:"
echo "  ./venv/bin/python src/pipeline.py diff --old fixtures/contract_v1.pdf --new fixtures/contract_v2.pdf"
echo
echo "Run the test suite with:"
echo "  ./venv/bin/pytest -s tests/"
