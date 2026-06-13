#!/usr/bin/env bash
#
# Run the full maritime simulation from scratch:
#   1. boot the world model + frontend (Docker)
#   2. wait for the world model to be healthy
#   3. launch the AI control layer (real LLM if GROQ_API_KEY is set)
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

echo "▶ Installing AI control dependencies (host) ..."
python3 -m pip install -q -r maritime_swarm/ai_control/requirements.txt

if [ -z "${GROQ_API_KEY:-}${API_KEY:-}" ]; then
  echo "⚠  No GROQ_API_KEY set — the AI layer will use the offline heuristic planner."
  echo "   Export GROQ_API_KEY=... for real LLM decisions."
fi

echo "▶ Launching AI control (Ctrl+C to stop) ..."
exec python3 -m maritime_swarm.ai_control
