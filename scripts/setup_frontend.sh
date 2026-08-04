#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
npm install
test -f .env || cp .env.example .env
echo "Frontend ready. Run: npm run dev"
