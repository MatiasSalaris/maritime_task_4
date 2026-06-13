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

from maritime_swarm.ai_control.coordination import SECTORS
from maritime_swarm.ai_control.geo import haversine_km
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import ToolContext, ToolRegistry

_SENSOR_BY_TYPE = {"USV": "360° surface radar", "UAV": "downward EO/IR camera"}

def build_decision_system_prompt(registry: ToolRegistry) -> str:
    return (
        "You are ONE of three peer maritime assets — NO commander. You decide ONLY your own next "
        "action; the team divides work by CHATTING until you agree.\n"
        "Rules: persistent ops — never stop unless ordered. Interpret the mission however phrased and "
        "use tools for your part. State intent (proposal); answer peers (ack, or objection+counter). "
        "Don't grab a shared task before agreeing, but act alone on what only you can do. If you and a "
        "peer want the same thing, the LOWER id keeps it and the other takes the complement. Respect "
        "commitments; cover a silent peer. Only use contact/POI ids shown to you — never invent ids.\n\n"
        "ACTIONS (pick exactly one):\n"
        f"{registry.compact_block()}\n\n"
        "MSG TYPES: proposal, ack, objection, handoff, report, status.\n"
        'Reply with ONE JSON object only: {"reasoning":"<1-2 sentences>","messages":[{"to":"all|agent_0|agent_1|agent_2","type":"<type>","content":"<short>"}],"action":{"tool":"<name>","args":{...}}}'
        "  (messages may be []).\n"
        'EXAMPLE: {"reasoning":"Alpha took north; I take SW to avoid overlap.","messages":[{"to":"all","type":"ack","content":"Copy, I take SW."}],"action":{"tool":"patrol_sector","args":{"sector":"SW"}}}'
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
    L.append(f"SECTORS for patrol_sector: {', '.join(SECTORS)}.")
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
