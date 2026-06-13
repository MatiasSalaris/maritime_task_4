# AI Control Layer

The **brain** side of the swarm: a decentralised, LLM-driven coordination layer
for the three maritime assets in the world model (`environment/backend`). It is
kept strictly separate from the world model — it imports none of the simulator
and talks only over the public WebSocket + REST contract. There is **no central
planner**: coordination emerges peer-to-peer over the world model's message bus,
which is also what the frontend renders.

## Architecture

```
 world model (WebSocket + REST)            AI control (this package)
 ──────────────────────────────           ─────────────────────────
  observation (10 Hz) ───────►  WorldModelClient ──► AgentBrain ── SwarmView (shared picture)
                                                       │
                          ┌────────────────────────────┼─────────────────────────────┐
                          │ STRATEGIC (leader only)     │ TACTICAL (every agent)       │
                          │ Strategist.plan(): interpret│ Tactician.decide_reactive(): │
                          │ mission → brief + allocation│ react to a sensed contact    │
                          └────────────────────────────┼─────────────────────────────┘
                                                       │
                       baseline task (deterministic) + reactive tool (LLM-chosen)
  apply_action ◄── action ── WorldModelClient ◄── Tool.step(obs)   (each tick)
  p2p messages ◄── proposal / ack / status / report ──┘   (visible negotiation)
```

Two LLM roles, both small open-weight models via Groq:

- **Strategist** (run by the *leader* — the lowest-id live asset, the entry
  point for the human's mission): interprets the natural-language mission into a
  structured brief `{objective, constraints, priority}` and proposes a division
  of labour (`allocation`: each asset → an assignment). Broadcast as a P2P
  `proposal`. Peers `ack` (or the plan is adjusted). If the leader goes silent,
  the next asset takes over — no privileged node.
- **Tactician** (every agent): the assigned **baseline task** runs
  deterministically (patrol a sector, escort, visit POIs…); the tactician LLM is
  consulted only to *react* to what an asset senses — investigate a contact, or
  report it with a rationale — then the agent returns to its task.

### Convergence without a commander

The negotiation is LLM-driven and visible (proposals/acks on the bus). To
guarantee it actually *converges* — the brief's "coherence without a commander"
tension — every agent also runs an **identical, deterministic de-confliction**
(`coordination.deconflict`) locally over the shared picture. Same inputs + same
rule ⇒ the same allocation in every agent, with no central authority. The LLM
provides the legible argument; the backstop guarantees no deadlock/oscillation.

### Grounding

Tools validate their arguments against the live observation + shared picture at
build time (`navigation_tools`): you cannot `investigate_contact` or
`report_contact` an id that isn't sensed or known. Symbolic targets (sectors,
POI ids, contact ids) are used instead of raw lat/lon so the small model can't
drift. This is the "acting on fluent nonsense" guard.

## Tools

| Tool | Purpose |
|------|---------|
| `patrol_sector(sector)` | continuously sweep a quadrant/centre — patrol baseline |
| `go_to(lat, lon)` / `go_to_poi(poi_id)` | transit to a point / named POI |
| `investigate_contact(contact_id)` | close on a known contact to identify it |
| `report_contact(contact_id, classification, rationale)` | broadcast an anomaly report |
| `escort_contact(contact_id, standoff_m, bearing_deg)` | hold a formation slot (Scenario C) |
| `visit_pois(poi_ids, rendezvous?)` | sequential POIs then converge (Scenario D) |
| `rendezvous(poi_id)` | converge on a point |
| `hold_position(seconds)` | stop and observe |

Assignments map to baseline tools; the tactician picks `investigate` / `report`
reactively. Missions are **persistent** — see [persistent operations](../../).

## Running

The AI layer auto-starts as the `ai` service in both compose files; put your key
in the repo-root `.env` (`GROQ_API_KEY=...`) and `docker compose up`. Or run
standalone: `python -m maritime_swarm.ai_control` (see env vars below). Without a
key it falls back to deterministic heuristic strategist + tactician.

| Var | Default | Meaning |
|-----|---------|---------|
| `GROQ_API_KEY`/`API_KEY` | – | LLM key (quoted values tolerated) |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | model |
| `WORLD_HTTP_URL` / `WORLD_WS_URL` | localhost:8000 | world model |
| `MISSION` | – | override (else adopts the world's mission) |
| `FAKE_LLM` | `0` | force the offline heuristic planners |

## Where the swarm breaks (honest limits)

- **LLM rate limits.** Three agents on a free-tier key hit `429 Too Many
  Requests` under load. Handled gracefully — the agent logs it and stays on its
  baseline task — but heavy reactive bursts can drop individual decisions. A
  bigger budget or local serving (Ollama) removes this.
- **Small-model judgement.** `llama-3.1-8b-instant` occasionally mis-allocates
  or mis-classifies; the deterministic de-confliction and grounding catch the
  worst cases, but a 70B model is visibly better. Symbolic targets hide most
  spatial-reasoning errors.
- **Negotiation depth.** Convergence currently leans on the deterministic
  backstop rather than rich multi-round objection/counter-proposal; true
  argument is shallow (propose → ack), by design, for reliability on the clock.
- **Shared-picture staleness.** Peer awareness is only as fresh as the last
  `status` broadcast (every few seconds); a peer is declared silent after ~9 s.
  Fast-moving contacts can be briefly out of date across the team.
- **Redundant reactions.** Two assets can momentarily both react to the same new
  contact before the report propagates; they de-duplicate once it is reported,
  but not instantaneously.
- **Tail-chase limits.** An asset only marginally faster than a contact closes
  slowly; identification therefore completes at a fraction of sensor range
  rather than on physical contact.
