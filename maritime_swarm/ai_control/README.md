# AI Control Layer

The **brain** side of the maritime swarm. It drives the agents in the world
model (`environment/backend`) using **real LLM output**, via a first-class
**Tool** abstraction. It is kept strictly separate from the world model: it
imports none of the simulator and talks only over the world model's public
WebSocket + REST contract.

## How it works

```
 world model (environment/backend)            AI control (this package)
 ───────────────────────────────              ─────────────────────────
  ws/agent/{id}  ──observation──►  WorldModelClient ──► AgentBrain
                                                          │
                                            (idle / new contact?)
                                                          │  build prompt
                                                          ▼
                                                       Planner ── LLM ──► {tool, args, reasoning}
                                                          │
                                            ToolRegistry.build(tool, args)
                                                          │
  apply_action  ◄────action────   WorldModelClient ◄── Tool.step(obs)  (each tick)
```

1. **Observation** (10 Hz) → parsed into a typed `Observation`.
2. When the agent is **idle** (or a new suspicious contact appears), the
   **Planner** asks the LLM to choose one tool. The reasoning is streamed back
   as a `cot_chunk` (shown in the frontend thought bubbles).
3. The chosen **Tool** is validated + built by the `ToolRegistry`, then executed
   tick-by-tick: each `step(obs)` returns a world action (heading/speed/path)
   until the tool reports `DONE`/`FAILED`.

## Tools

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `go_to` | `go_to(lat, lon)` | Transit to a waypoint (clamped to the operating area); stop on arrival. |
| `investigate_contact` | `investigate_contact(contact_id)` | Close on a sensed contact to identify it; tracks it as it moves. |
| `hold_position` | `hold_position(seconds)` | Stop and observe for a while. |

Adding a tool = subclass `Tool` (declare `name`/`description`/`parameters`,
implement `build` + `step`) and register it in `navigation_tools.default_registry`.

## Running

### Docker (recommended) — starts automatically

The AI layer is wired into both compose files as the `ai` service, so it boots
together with the world model and frontend:

```bash
# put your key in the repo-root .env (GROQ_API_KEY=...), then:
docker compose -f environment/docker-compose.dev.yml up   # dev (frontend on :5173)
docker compose -f environment/docker-compose.yml up        # prod (frontend on :3000)
```

The `ai` container reads `GROQ_API_KEY` (and optional `GROQ_MODEL` / `MISSION`)
from the repo-root `.env`. Quoted values are tolerated. With no key it falls
back to the offline heuristic planner.

### Standalone process

The world model must already be running.

```bash
# from the repo root
export GROQ_API_KEY=sk-...            # real LLM decisions (Groq)
pip install -r maritime_swarm/ai_control/requirements.txt
python -m maritime_swarm.ai_control
```

Or the one-shot script that boots the world model + frontend and then the brains:

```bash
export GROQ_API_KEY=sk-...
./run_simulation.sh
```

Watch it at <http://localhost:5173> (dev) or <http://localhost:3000> (prod).

### Live missions

Type/change the mission in the frontend at any time. The brains watch the
mission in their observation stream and **re-plan immediately** when it changes —
no restart needed. Mission precedence at startup: `MISSION` env > the mission
already set in the world > the built-in default patrol order.

### Environment variables

| Var | Default | Meaning |
|-----|---------|---------|
| `GROQ_API_KEY` / `API_KEY` | – | LLM key. **Omit to run the offline heuristic planner.** |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Model name. |
| `WORLD_HTTP_URL` | `http://localhost:8000` | World model REST base. |
| `WORLD_WS_URL` | `ws://localhost:8000` | World model WS base. |
| `MISSION` | patrol order | Mission text given to the swarm. |
| `THINK_INTERVAL` | `4` | Min seconds between LLM calls per agent. |
| `FAKE_LLM` | `0` | Force the heuristic planner (offline testing). |

Without a key the `HeuristicPlanner` runs the exact same loop deterministically
(investigate suspicious contacts, otherwise patrol) so the simulation still
works offline and in tests.
