"""Prompt construction for the open-ended, decentralised agent decision.

One LLM call per agent per cycle. Given the mission (free natural language),
what the asset senses, the shared picture and its peers' messages, the model
reasons, optionally sends messages to coordinate, and chooses one action. No
keyword rules — the model interprets arbitrary orders and maps them to the
action vocabulary itself. Few-shot examples teach the format and good
coordination, not specific missions.
"""

from __future__ import annotations

from typing import Any

from maritime_swarm.ai_control.coordination import SECTORS, sector_center
from maritime_swarm.ai_control.geo import haversine_km
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import ToolContext, ToolRegistry

_SENSOR_BY_TYPE = {"USV": "360° surface radar", "UAV": "downward EO/IR camera"}

_FEWSHOT = """\
EXAMPLES (format only — your situation differs):
{"reasoning":"Alpha took the north, so I'll cover the south-west to avoid overlap.","messages":[{"to":"all","type":"ack","content":"Copy — I'll patrol SW."}],"action":{"tool":"patrol_sector","args":{"sector":"SW"}}}
{"reasoning":"Order is to move 5 km south; proceeding south.","messages":[],"action":{"tool":"move","args":{"direction":"south","distance_km":5}}}
{"reasoning":"Unknown c003 is located and the order is for all to intercept it.","messages":[{"to":"all","type":"proposal","content":"Target c003 located — all intercept."}],"action":{"tool":"investigate_contact","args":{"contact_id":"c003"}}}
{"reasoning":"I have the unreported vessel; order is to shadow at 500 m, so I'll escort and let peers keep coverage.","messages":[{"to":"all","type":"handoff","content":"Engaging c003 at 500 m; you two keep coverage."}],"action":{"tool":"escort_contact","args":{"contact_id":"c003","standoff_m":500}}}
"""


def build_decision_system_prompt(registry: ToolRegistry) -> str:
    return (
        "You are ONE of three autonomous maritime assets operating as a peer team. Each asset "
        "(including you) runs its own reasoning — there is NO commander and no central planner. "
        "You are given a mission in plain language and must accomplish it by REASONING, "
        "COMMUNICATING with your two peers, and ACTING. Coordination must emerge between you.\n\n"
        "STANDING DOCTRINE:\n"
        "- Operations are persistent and continuous: never declare the mission done and never stop "
        "unless explicitly ordered to. After achieving an objective, keep operating sensibly.\n"
        "- Interpret the mission literally and intelligently, however it is phrased. Decompose it, "
        "decide your part, and use the tools to carry it out.\n\n"
        "COORDINATION — THERE IS NO COMMANDER. No node decides for anyone else; you decide ONLY "
        "your OWN next action. The team's division of labour must be AGREED by chatting:\n"
        "- Say what you intend and why (proposal); answer your peers (ack to agree, objection to "
        "disagree WITH a reason and a counter-proposal). Keep talking until you converge.\n"
        "- Do not unilaterally grab a shared task before the team has agreed who does what; but for "
        "an obvious local action only you can take (e.g. only you sense the target), act and tell them.\n"
        "- If, AFTER discussing, you and a peer still both want the same thing, the lower-id asset "
        "(agent_0<agent_1<agent_2) keeps it and the other takes the complementary part — a shared "
        "convention you both apply to break ties, NOT an order from anyone. Respect what peers have "
        "committed to; cover for a peer that has gone silent.\n\n"
        "GROUNDING:\n"
        "- Only use contact ids and POI ids that actually appear in your situation. NEVER invent ids "
        "or act on a contact that does not exist. Prefer symbolic targets (sectors, POI ids, contact "
        "ids) and the 'move'/'go_to_poi' tools over raw coordinates.\n\n"
        "ACTIONS (choose exactly one tool):\n"
        f"{registry.prompt_block()}\n\n"
        "MESSAGE TYPES: proposal (suggest a plan), ack (agree), objection (disagree + counter), "
        "handoff (take/hand over a task), report (flag/annotate a contact), status (info).\n\n"
        "Respond with ONE JSON object only, exactly:\n"
        '{"reasoning":"<1-3 sentences of why>",'
        '"messages":[{"to":"all|agent_0|agent_1|agent_2","type":"<type>","content":"<short text>"}],'
        '"action":{"tool":"<tool name>","args":{...}}}\n'
        "messages may be an empty list. Keep messages short and operational.\n\n"
        + _FEWSHOT
    )


def build_decision_user_prompt(
    obs: Observation, ctx: ToolContext, scene: Scene, mission: str,
    peers: list[dict[str, Any]], shared_contacts: list[dict[str, Any]],
    messages: list[dict[str, Any]], current_task: str | None,
    task_status: str = "idle", silent_peers: list[str] | None = None,
    outbox: list[dict[str, Any]] | None = None,
) -> str:
    """The full state the asset reasons on: per-agent, shared (mission/comms), world."""
    b = scene.bounds
    L = [f"MISSION (verbatim): {mission}", ""]

    # ── per-agent state ───────────────────────────────────────────────────
    L.append("YOUR STATE:")
    L.append(f"  id={ctx.agent_id} name={ctx.agent_name} type={ctx.agent_type} "
             f"sensor={_SENSOR_BY_TYPE.get(ctx.agent_type, 'sensors')} cruise={ctx.cruise_speed_kn:.0f}kn")
    L.append(f"  position={obs.lat:.4f},{obs.lon:.4f} heading={obs.heading:.0f}° speed={obs.speed_kn:.1f}kn")
    L.append(f"  current_task={current_task or 'none'} status={task_status}")
    L.append(f"  contacts_in_range={len(obs.contacts)}")
    L.append("")

    # ── world: area + contacts ────────────────────────────────────────────
    L.append(f"OPERATING AREA (geofence): lat {b.lat_min:.3f}..{b.lat_max:.3f}, lon {b.lon_min:.3f}..{b.lon_max:.3f}.")
    L.append("SECTORS (centre): " + "; ".join(
        f"{s}@{sector_center(b, s)[0]:.3f},{sector_center(b, s)[1]:.3f}" for s in SECTORS))
    if scene.pois:
        L.append("POIs: " + "; ".join(f"{p.id}({p.label})@{p.lat:.3f},{p.lon:.3f}" for p in scene.pois))
    L.append("")
    if obs.contacts:
        L.append("CONTACTS YOU SENSE NOW:")
        for c in obs.contacts:
            d = haversine_km(obs.lat, obs.lon, c.lat, c.lon)
            tag = "SUSPICIOUS(unreported/unknown)" if c.is_suspicious else "benign-AIS"
            L.append(f"  - {c.id} [{tag}] class={c.label} at {c.lat:.4f},{c.lon:.4f} "
                     f"course {c.heading:.0f}° {c.speed_kn:.0f}kn dist {d:.2f}km")
    else:
        L.append("CONTACTS YOU SENSE NOW: none.")
    if shared_contacts:
        L.append("SHARED CONTACTS (reported by peers): " + "; ".join(
            f"{c['id']}({c.get('label','?')}{' FLAGGED' if c.get('flagged') else ''}"
            f"{' REPORTED' if c.get('reported') else ''})@{c['lat']:.3f},{c['lon']:.3f}"
            for c in shared_contacts))
    L.append("")

    # ── shared: team / comms (failure honesty) ────────────────────────────
    L.append("TEAM (peers you can currently hear):")
    if peers:
        for p in peers:
            L.append(f"  - {p['id']} ({p.get('type','?')}) at {p['lat']:.4f},{p['lon']:.4f} "
                     f"task: {p.get('task') or 'unknown'}")
    else:
        L.append("  (none heard yet)")
    if silent_peers:
        L.append(f"SILENT / UNREACHABLE peers (no recent comms — cover for them): {', '.join(silent_peers)}")
    if messages:
        L.append("INBOX (recent messages FROM peers):")
        for m in messages:
            L.append(f"  - {m['sender']} [{m['type']}]: {m['text']}")
    if outbox:
        L.append("YOUR RECENT MESSAGES (what you already told the team):")
        for m in outbox:
            text = m.get("content") or m.get("text") or ""
            L.append(f"  - [{m.get('type', 'status')}→{m.get('to', 'all')}]: {text}")
    L.append("")
    L.append("Decide your OWN next action only. Reason over the state above, talk to your peers to "
             "agree the division of work, and choose one action. JSON only.")
    return "\n".join(L)
