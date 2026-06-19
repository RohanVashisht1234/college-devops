#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

APP_PORT=8000
PROMETHEUS_URL="http://localhost:9090"
GRAFANA_URL="http://localhost:3001"
KIBANA_URL="http://localhost:5600"
VAULT_URL="http://localhost:8200"
APP_URL="http://localhost:${APP_PORT}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

open_url() {
  local url="$1"
  if have open; then
    open "$url" >/dev/null 2>&1 || true
  else
    log "Open manually: $url"
  fi
}

wait_for_url() {
  local url="$1"
  local name="$2"
  local attempts="${3:-30}"
  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "$name is ready: $url"
      return 0
    fi
    sleep 1
  done
  log "$name did not respond yet: $url"
  return 1
}

require_command() {
  if ! have "$1"; then
    log "Missing required command: $1"
    exit 1
  fi
}

log "Checking required commands"
require_command python3
require_command curl

if ! have docker-compose; then
  log "docker-compose is not installed. Install it with: brew install docker-compose"
  exit 1
fi

log "Preparing Python virtual environment"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -r requirements.txt

log "Checking port availability"
PORTS=(3001 9090 9200 5600 8200)
for port in "${PORTS[@]}"; do
  if lsof -ti tcp:"$port" >/dev/null 2>&1; then
    log "WARNING: Port $port is already in use by PID $(lsof -ti tcp:$port | head -1)"
  fi
done

log "Starting monitoring stack: Prometheus and Grafana"
docker-compose -f monitoring/docker-compose.yml up -d

log "Starting logging stack: Elasticsearch, Logstash, Kibana"
docker-compose -f elk/docker-compose.yml up -d

log "Starting Vault"
docker-compose -f vault/docker-compose.yml up -d

log "Starting MedGenome FastAPI app on port ${APP_PORT}"
if lsof -ti tcp:"${APP_PORT}" >/dev/null 2>&1; then
  log "Port ${APP_PORT} is already in use, assuming the app is already running"
else
  mkdir -p .run
  nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT}" > .run/app.log 2>&1 &
  echo "$!" > .run/app.pid
fi

wait_for_url "${APP_URL}/healthz" "MedGenome app" 30 || true
wait_for_url "${PROMETHEUS_URL}/-/ready" "Prometheus" 45 || true
wait_for_url "${GRAFANA_URL}/login" "Grafana" 45 || true
wait_for_url "${VAULT_URL}/v1/sys/health" "Vault" 45 || true
wait_for_url "http://localhost:9200" "Elasticsearch" 60 || true

log "Sending sample structured logs to Logstash"
printf '{"service":"medgenome-api","level":"info","message":"runner demo started","job_id":"MG-RUNNER"}\n' | nc localhost 5000 >/dev/null 2>&1 || true
printf '{"service":"medgenome-api","level":"warn","message":"queue depth high","active_jobs":8}\n' | nc localhost 5000 >/dev/null 2>&1 || true

log "Generating app traffic for Prometheus"
curl -fsS "${APP_URL}/api/summary" >/dev/null 2>&1 || true
curl -fsS -X POST "${APP_URL}/api/simulate" >/dev/null 2>&1 || true
curl -fsS "${APP_URL}/metrics" >/dev/null 2>&1 || true

log "Opening demo pages"
open_url "$APP_URL"
open_url "${APP_URL}/docs"
open_url "${APP_URL}/metrics"
open_url "$PROMETHEUS_URL"
open_url "$GRAFANA_URL"
open_url "$KIBANA_URL"
open_url "$VAULT_URL"

cat <<EOF

MedGenome demo is starting.

App:        ${APP_URL}
API docs:   ${APP_URL}/docs
Metrics:    ${APP_URL}/metrics
Prometheus: ${PROMETHEUS_URL}
Grafana:    ${GRAFANA_URL}      login admin/admin
Kibana:     ${KIBANA_URL}
Vault:      ${VAULT_URL}        token root

App login:
  username: admin
  password: admin

Useful Prometheus queries:
  medgenome_active_jobs
  medgenome_uploads_total
  medgenome_uploaded_bytes_total
  medgenome_datasets_total

To stop Docker services:
  docker-compose -f monitoring/docker-compose.yml down
  docker-compose -f elk/docker-compose.yml down
  docker-compose -f vault/docker-compose.yml down

To stop the app started by this runner:
  kill \$(cat .run/app.pid)

EOF
