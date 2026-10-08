#!/usr/bin/env bash
# Run from any directory: /path/to/kassensturz/update.sh [--https]
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
compose_file=compose.yaml
case "${1:-}" in
  "") ;;
  --https) compose_file=compose.https.yaml ;;
  *) echo "Usage: $0 [--https]" >&2; exit 1 ;;
esac
if (( $# > 1 )); then
  echo "Usage: $0 [--https]" >&2
  exit 1
fi

if [[ "$(git branch --show-current)" != server ]]; then
  echo "Switch to the server branch before updating." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Commit or move local source changes before updating." >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "Copy .env.example to .env and set APP_PASSWORD before updating." >&2
  exit 1
fi

docker compose version >/dev/null
docker info >/dev/null
git pull --ff-only origin server
docker compose -f "$compose_file" config --quiet
# Build first so a failed build leaves the running app available.
docker compose -f "$compose_file" build
docker compose -f "$compose_file" up -d --wait --wait-timeout 120
docker compose -f "$compose_file" ps
echo "Kassensturz is ready at commit $(git rev-parse --short HEAD). Refresh your browser."
