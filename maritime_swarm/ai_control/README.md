# AI Control Layer

The **brain** side of the swarm: a decentralised, **open-ended LLM** coordination
layer for the three maritime assets in the world model (`environment/backend`).
It is kept strictly separate from the world model — it imports none of the
simulator and talks only over the public WebSocket + REST contract. There is
**no central planner and no keyword rules**: each asset reasons for itself and
the team coordinates over the world model's message bus (which the frontend
renders).

## How it works

Each asset runs its own loop. Every ~10 s (or on an event — a new message, a new
contact, a mission change), it makes **one LLM call** with the full situation and
gets back reasoning + coordination messages + a single action:

```
 observation (10 Hz) ─► SwarmView (shared picture: peers, contacts, messages)
                              │
                 every ~10s / on event
                              ▼
   one LLM call:  mission (free text) + what I sense + peers + their messages
                              │
                 ┌────────────┴─────────────┐
        reasoning (CoT)   messages (P2P)   action (one tool)
                              │
        apply_action / send P2P  →  world model (visible on the map + log)
```

- **Open-ended:** the model interprets *any* order ("patrol & report", "follow
  it at 500 m", "everybody intercept the unknown vessel", "go 5 km south",
  "investigate the three POIs then rendezvous") and maps it to tools itself.
  There are no `if mission contains "south"` rules — a few-shot prompt teaches
  the format and good coordination, not specific missions.
- **Decentralised:** no leader, no central allocation. Agents announce intent
  and read each other's messages; convergence comes from a social convention in
  the prompt (lower-id breaks ties; respect a peer's announced commitment; don't
  duplicate) — "coherence without a commander."
- **Grounded:** tools validate their arguments against the live observation /
  shared picture, so an agent can't act on a contact or POI that doesn't exist.

## Action vocabulary (tools)

`move(direction, km)` · `go_to(lat,lon)` · `go_to_poi(id)` · `patrol_sector(NW/NE/SW/SE/CENTER)` ·
`investigate_contact(id)` · `report_contact(id, class, rationale)` · `escort_contact(id, standoff_m, bearing)` ·
`visit_pois([ids], rendezvous)` · `rendezvous(poi)` · `hold_position(s)`

The model composes these to satisfy arbitrary missions. Symbolic targets
(sectors, POI ids, contact ids) and relative `move` keep a small model accurate.

## Running

Auto-starts as the `ai` service in both compose files; put your key in the
repo-root `.env` (`GROQ_API_KEY=...`) and `docker compose up`. Or standalone:
`python -m maritime_swarm.ai_control`. Without a key it uses an offline
heuristic decider.

| Var | Default | Meaning |
|-----|---------|---------|
| `GROQ_API_KEY`/`API_KEY` | – | LLM key |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | model — set to `llama-3.3-70b-versatile` for stronger reasoning if your key's rate limits allow |
| `WORLD_HTTP_URL` / `WORLD_WS_URL` | localhost:8000 | world model |
| `MISSION` | – | override (else adopts the world's mission) |
| `FAKE_LLM` | `0` | force the offline heuristic decider |

## Where the swarm breaks (honest limits)

- **LLM rate limits dominate.** Three agents reasoning concurrently exceed
  Groq's free-tier tokens/minute, especially on the 70B model — decisions get
  `429`'d. The loop handles it (staggered starts, a ~25 s backoff, and the agent
  keeps its current action), but under heavy load the effective decision cadence
  stretches and coordination slows. A higher-rate key (or local serving via
  Ollama) removes this; the 8B default stays responsive.
- **Small-model judgement.** `llama-3.1-8b-instant` keeps the swarm responsive
  but occasionally mis-phrases a plan or picks a blunt tool; the grounding and
  the few-shot conventions catch the worst. A 70B model is visibly sharper when
  the rate limits allow it.
- **Convergence is social, not guaranteed.** With no commander, two agents can
  briefly contend for the same task before the lower-id convention settles it;
  pathological oscillation is possible (and shown rather than hidden).
- **Shared picture staleness.** Peer awareness is only as fresh as the last
  status heartbeat (~4 s); a peer is treated as silent after ~12 s.
- **Very novel phrasings** may map to a sensible default rather than the exact
  intent — there is no hard guarantee, by design (open-ended over brittle).
