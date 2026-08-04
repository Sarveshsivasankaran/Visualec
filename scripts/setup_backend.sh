#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
test -f .env || cp .env.example .env
echo "Backend ready. Run: uvicorn app.main:app --reload"
