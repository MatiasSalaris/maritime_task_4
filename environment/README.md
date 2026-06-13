# Swarm of Three — Simulation Engine

Maritime simulation engine for the Mirai hackathon challenge.
Python backend · MapLibre GL frontend · Docker.

---

## Running

### Production — one command, everything containerised

```bash
docker compose up --build
```

Open **http://localhost:3000**

### Development — hot reload on every save

```bash
docker compose -f docker-compose.dev.yml up --build
```

| Service  | URL                        |
|----------|---------------------------|
| Frontend | http://localhost:5173      |
| Backend  | http://localhost:8000      |
| API docs | http://localhost:8000/docs |

Both the Python backend and the Vite frontend restart automatically when you save a file.

---

## Switching to real hardware

Set `PROVIDER=hardware` in `docker-compose.yml` (or the environment):

```yaml
environment:
  - PROVIDER=hardware
```

Then fill in `backend/providers/hardware/hw_provider.py`.
Nothing else in the stack changes.

---

## REST API

| Method | Path                           | Description                  |
|--------|--------------------------------|------------------------------|
| POST   | `/api/mission`                 | Set initial mission text      |
| POST   | `/api/mission/change`          | Mid-mission intent change     |
| GET    | `/api/state`                   | Full world state snapshot     |
| GET    | `/api/messages?n=50`           | Last N P2P messages           |
| POST   | `/api/agents/{id}/status`      | Force agent status (sim comm disruption) |

## WebSocket endpoints

| Path              | Direction          | Purpose                     |
|-------------------|--------------------|-----------------------------|
| `/ws/frontend`    | Server → browser   | World state at ~10 Hz       |
| `/ws/agent/{id}`  | Bidirectional      | LLM agent ↔ sim             |

### Agent protocol (JSON frames)

**Engine → agent**
```json
{ "type": "observation", "payload": { "position": {...}, "contacts_in_range": [...], "messages_inbox": [...], "mission": "..." } }
```

**Agent → engine**
```json
{ "type": "action",       "payload": { "heading": 90, "speed_kn": 10, "current_task": "Patrol sector W" } }
{ "type": "p2p_message",  "payload": { "to": "agent_1", "msg_type": "proposal", "content": {...}, "reasoning": "..." } }
{ "type": "cot_chunk",    "payload": { "chunk": "I should take the western sector because..." } }
```

`msg_type` values: `proposal` | `ack` | `objection` | `handoff` | `status`

---

## Map overlays

Switch in the top-right corner of the map:

| Name        | Source                     | Best for           |
|-------------|----------------------------|--------------------|
| Tactical    | Stadia Dark + OpenSeaMap   | Demo (default)     |
| Nautical    | OSM + OpenSeaMap           | Familiar charts    |
| Satellite   | Esri World Imagery         | Ground truth       |
| Bathymetric | Stadia Watercolor + seamarks | Ocean ops context |

---

## Project layout

```
environment/
├── backend/
│   ├── main.py                  FastAPI app + lifespan
│   ├── config.py                Settings (env vars)
│   ├── models/                  Pydantic schemas
│   ├── engine/                  World state engine + WS manager
│   ├── providers/
│   │   ├── base.py              AbstractPlatformProvider interface
│   │   ├── simulation/          Physics, synthetic AIS
│   │   └── hardware/            Stub for real platforms
│   └── api/                     WS + REST route handlers
├── frontend/
│   └── src/
│       ├── map/                 MapLibre layers + overlays
│       ├── ui/                  Svelte components
│       ├── store/               Reactive world state
│       └── ws/                  WebSocket client
├── docker-compose.yml           Production
├── docker-compose.dev.yml       Development (hot reload)
├── Dockerfile.backend
├── Dockerfile.backend.dev
├── Dockerfile.frontend
└── nginx.conf                   Prod reverse proxy
```
