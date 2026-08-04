#!/usr/bin/env bash
set -euo pipefail
trap 'kill 0' EXIT
(cd "$(dirname "$0")/../backend" && .venv/bin/uvicorn app.main:app --reload) &
(cd "$(dirname "$0")/../frontend" && npm run dev) &
wait
