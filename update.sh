#!/usr/bin/env bash
# Run from any directory: /path/to/kassensturz/update.sh [--https] [--encrypted] [--external-proxy]
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
compose_files=(-f compose.yaml)
encrypted=false
external_proxy=false
[[ ! -f .external-proxy-deployment ]] || external_proxy=true
for option in "$@"; do
  case "$option" in
    --external-proxy) external_proxy=true ;;
    --https) ;; # HTTPS is now the default; preserve the existing invocation.
    --encrypted) compose_files+=(-f compose.encrypted.yaml); encrypted=true ;;
    *) echo "Usage: $0 [--https] [--encrypted] [--external-proxy]" >&2; exit 1 ;;
  esac
done

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
if [[ "$encrypted" == false ]] && { [[ -f .encrypted-deployment ]] || grep -Eq '^[[:space:]]*ENCRYPTED_DATA_DIR[[:space:]]*=[[:space:]]*[^[:space:]#]+' .env; }; then
  echo "Encryption is configured. Run update.sh --encrypted; refusing to switch to plaintext storage." >&2
  exit 1
fi
git pull --ff-only origin server
# Validate before stopping/replacing the currently running application.
if [[ "${DATA_ENCRYPTION_KEY_FILE:-}" != "" ]]; then
  echo "Configure encryption through --encrypted and .env file paths, not a shell key value." >&2
  exit 1
fi
# Local deployment settings stay outside tracked source files.
if [[ -f compose.server-local.yaml ]]; then
  compose_files+=(-f compose.server-local.yaml)
elif [[ "$external_proxy" == true ]]; then
  echo "External proxy mode requires compose.server-local.yaml with a loopback app port mapping." >&2
  exit 1
fi
docker compose "${compose_files[@]}" config --quiet
if [[ "$external_proxy" == true ]]; then touch .external-proxy-deployment; fi
if [[ "$encrypted" == true ]]; then touch .encrypted-deployment; fi
# Build first so a failed build leaves the running app available.
if [[ "$external_proxy" == true ]]; then
  docker compose "${compose_files[@]}" build app
  docker compose "${compose_files[@]}" up -d --no-deps --wait --wait-timeout 120 app
  docker compose "${compose_files[@]}" ps app
else
  docker compose "${compose_files[@]}" build
  docker compose "${compose_files[@]}" up -d --wait --wait-timeout 120
  docker compose "${compose_files[@]}" ps
fi
echo "Kassensturz is ready at commit $(git rev-parse --short HEAD). Refresh your browser."
