#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

SERVICE_NAME="${SERVICE_NAME:-ai-tracker}"
BRANCH="${BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
RUN_SYNC="${RUN_SYNC:-0}"
RUN_DIGEST="${RUN_DIGEST:-0}"

cd "${REPO_DIR}"

timestamp() {
  date +"%Y-%m-%d-%H%M%S"
}

log() {
  printf "\n[%s] %s\n" "$(date +"%F %T")" "$1"
}

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Error: .venv/bin/python not found. Create the virtualenv on the server first."
  exit 1
fi

if [[ -f "ai_tracker.db" ]]; then
  backup_path="ai_tracker.db.bak-$(timestamp)"
  log "Backing up SQLite database to ${backup_path}"
  cp "ai_tracker.db" "${backup_path}"
fi

log "Pulling latest code from origin/${BRANCH}"
git pull --ff-only origin "${BRANCH}"

log "Installing/updating Python dependencies"
".venv/bin/pip" install -e .

log "Restarting ${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

log "Checking ${SERVICE_NAME} status"
sudo systemctl --no-pager --full status "${SERVICE_NAME}"

log "Waiting for health check"
for _ in {1..15}; do
  if curl -fsS "${HEALTH_URL}" >/dev/null; then
    log "Health check passed: ${HEALTH_URL}"
    break
  fi
  sleep 2
done

if ! curl -fsS "${HEALTH_URL}" >/dev/null; then
  echo "Health check failed: ${HEALTH_URL}"
  echo "Recent logs:"
  sudo journalctl -u "${SERVICE_NAME}" -n 100 --no-pager
  exit 1
fi

if [[ "${RUN_SYNC}" == "1" ]]; then
  log "Triggering source sync"
  curl -fsS -X POST "http://127.0.0.1:8000/api/sources/sync"
  printf "\n"
fi

if [[ "${RUN_DIGEST}" == "1" ]]; then
  log "Generating latest digest"
  curl -fsS -X POST "http://127.0.0.1:8000/api/digests/generate"
  printf "\n"
fi

log "Deploy complete"
