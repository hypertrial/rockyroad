#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

uv run pytest
pnpm --filter @rockyroad/web test
pnpm --filter @rockyroad/web build
docker-compose --profile local config >/dev/null 2>&1 || docker compose --profile local config >/dev/null

echo "Offline smoke prerequisites passed."
echo "To verify the assembled stack with no outbound network:"
echo "  1. Build sample artifacts with rockyroad-data"
echo "  2. docker compose --profile local up --build"
echo "  3. Recreate the stack with compose network internal-only and curl http://127.0.0.1:8080/api/health"
