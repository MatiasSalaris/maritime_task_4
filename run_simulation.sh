#!/usr/bin/env bash
#
# Run the full maritime simulation from scratch:
#   1. boot the world model + frontend + AI controller (Docker)
#   2. wait for the world model to be healthy
#   3. follow AI logs
#
# Watch it at http://localhost:5173
#
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE="environment/docker-compose.dev.yml"

echo "▶ Bringing up the world model + frontend ..."
docker compose -f "$COMPOSE" up -d --build

echo "▶ Waiting for the world model to be healthy ..."
for _ in $(seq 1 60); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "  world model is up."
    break
  fi
  sleep 1
done

echo "▶ Frontend: http://localhost:5173"
echo "▶ Backend:  http://localhost:8000"
echo "▶ Following AI logs (Ctrl+C stops log view; containers keep running) ..."
docker compose -f "$COMPOSE" logs -f ai
