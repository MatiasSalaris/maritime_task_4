"""Prompt construction for the two LLM roles.

- STRATEGIC (leader): interpret the natural-language mission and propose a
  division of labour across the named assets — "interpreted and re-expressed".
- TACTICAL (every agent): given my assignment and what I sense right now, decide
  whether to react to a contact (investigate / report) or stay on my baseline.

Both are deliberately small, grounded prompts: they enumerate the real assets,
sectors, POIs and sensed contacts so the model binds to world state.
"""

from __future__ import annotations

from typing import Any

from maritime_swarm.ai_control.coordination import SECTORS
from maritime_swarm.ai_control.geo import haversine_km
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import ToolContext

_SENSOR_BY_TYPE = {"USV": "360° surface radar", "UAV": "downward EO/IR camera"}


def _roster_block(members: list[dict[str, Any]]) -> str:
    lines = []
    for m in members:
        me = " (you)" if m.get("is_self") else ""
        lines.append(
            f"  - {m['id']}{me}: {m.get('name', m['id'])}, {m.get('type', '?')}, "
            f"at {m['lat']:.4f},{m['lon']:.4f}"
        )
    return "\n".join(lines)


def _scene_block(scene: Scene) -> str:
    b = scene.bounds
    lines = [
        f"OPERATING AREA: lat {b.lat_min:.3f}..{b.lat_max:.3f}, lon {b.lon_min:.3f}..{b.lon_max:.3f}.",
        f"SECTORS available for patrol_sector: {', '.join(SECTORS)}.",
    ]
    if scene.pois:
        lines.append("POINTS OF INTEREST: " + "; ".join(
            f"{p.id} ({p.label}) @ {p.lat:.3f},{p.lon:.3f}" for p in scene.pois))
    return "\n".join(lines)


# ── STRATEGIC (leader) ─────────────────────────────────────────────────────────
def strategist_system_prompt() -> str:
    return (
        "You are the LEAD asset of a three-vehicle autonomous maritime swarm. You have just "
        "received a mission in natural language. Interpret it and propose how the team should "
        "divide the work — you are not a commander, your peers may object, but give a clear plan.\n\n"
        "Assignment kinds you can give each asset (one per asset):\n"
        '  - {"kind":"patrol_sector","sector":"NW|NE|SW|SE|CENTER"}  — patrol/cover a sector\n'
        '  - {"kind":"investigate","contact_id":"<id>"}             — close on a known contact\n'
        '  - {"kind":"escort","contact_id":"<id>","standoff_m":500,"bearing_deg":<0-360>}\n'
        '  - {"kind":"visit_pois","poi_ids":["poi_1","poi_2"],"rendezvous":"poi_3"}\n'
        '  - {"kind":"rendezvous","poi_id":"<id>"}\n'
        '  - {"kind":"hold"}\n\n'
        "Guidance:\n"
        "- Bind to the assets, sectors, POIs and contacts you are given. Do NOT invent ids.\n"
        "- Only use 'investigate'/'escort' with a SPECIFIC contact id from KNOWN CONTACTS. "
        "If the mission is to find/locate/follow a vessel that is NOT yet in KNOWN CONTACTS, "
        "assign patrol_sector to SEARCH — assets switch to following it automatically once one finds it.\n"
        "- Spread coverage: for a patrol, give different sectors to different assets.\n"
        "- For escort/formation, give each asset a different bearing_deg around the contact.\n"
        "- For sequential POIs, share the ordered list; converge on the rendezvous if asked.\n"
        "- Respect stated constraints and priority.\n\n"
        "Respond with ONE JSON object only:\n"
        '{"reasoning":"<one sentence>","brief":{"objective":"<...>","constraints":["..."],'
        '"priority":"<text or null>"},"allocation":{"<agent_id>":{<assignment>}, ...}}'
    )


def strategist_user_prompt(
    mission: str, members: list[dict[str, Any]], scene: Scene,
    contacts: list[dict[str, Any]], engaged: dict[str, str] | None = None,
) -> str:
    lines = [f"MISSION: {mission}", "", "TEAM TO ALLOCATE:", _roster_block(members), "", _scene_block(scene)]
    if engaged:
        lines.append("ALREADY ENGAGED (do NOT reassign these — they are committed): " +
                     "; ".join(f"{aid}={label}" for aid, label in engaged.items()))
    if contacts:
        lines.append("KNOWN CONTACTS: " + "; ".join(
            f"{c['id']}({c.get('label','?')}{',FLAGGED' if c.get('flagged') else ''})" for c in contacts))
    lines.append("")
    lines.append(
        "Produce the brief and an allocation assigning every asset in TEAM TO ALLOCATE. "
        "Cover the whole operating area with the assets you have, even if some are engaged elsewhere. JSON only."
    )
    return "\n".join(lines)


# ── TACTICAL (every agent) ─────────────────────────────────────────────────────
def tactical_system_prompt() -> str:
    return (
        "You are an autonomous maritime asset executing your assigned task within a swarm. "
        "Your baseline task runs automatically. Your job here is to decide whether something "
        "you can SENSE warrants breaking off to react, then return to your task.\n\n"
        "Choose ONE action:\n"
        '  - {"action":"continue"}  — nothing warrants reacting; stay on the assigned task.\n'
        '  - {"action":"investigate","contact_id":"<id>"}  — close on a sensed contact to identify it.\n'
        '  - {"action":"report","contact_id":"<id>","classification":"ANOMALY|SUSPICIOUS|BENIGN",'
        '"rationale":"<one sentence from the evidence>"}  — report a contact to the team.\n'
        '  - {"action":"escort","contact_id":"<id>","standoff_m":500}  — follow/shadow a contact at a '
        "standoff distance. Use this when the mission tells you to FOLLOW, SHADOW, ESCORT or TRACK a "
        "vessel and you have identified a qualifying one.\n\n"
        "Rules:\n"
        "- Only reference contact ids that appear in CONTACTS IN RANGE (or JUST IDENTIFIED). Never invent one.\n"
        "- Investigate UNKNOWN/flagged contacts before acting; commercial/fishing AIS contacts are usually benign.\n"
        "- If the mission says to FIND AND FOLLOW an unreported vessel, escort it once identified "
        "(use the distance it specifies, e.g. 500 m).\n"
        "- Otherwise honour the mission's reporting criterion if one is given.\n\n"
        'Respond with ONE JSON object only: {"reasoning":"<one sentence>","action":"...", ...}'
    )


def tactical_user_prompt(
    obs: Observation, ctx: ToolContext, mission: str, brief: dict[str, Any] | None,
    assignment_label: str, peers: list[dict[str, Any]], focus: dict[str, Any] | None = None,
) -> str:
    lines = [f"MISSION: {mission}"]
    if brief:
        if brief.get("objective"):
            lines.append(f"OBJECTIVE: {brief['objective']}")
        if brief.get("constraints"):
            lines.append("CONSTRAINTS: " + "; ".join(brief["constraints"]))
        if brief.get("priority"):
            lines.append(f"PRIORITY: {brief['priority']}")
    lines.append("")
    lines.append(f"YOU ARE: {ctx.agent_name} ({ctx.agent_id}), {ctx.agent_type} "
                 f"with {_SENSOR_BY_TYPE.get(ctx.agent_type, 'sensors')}.")
    lines.append(f"YOUR ASSIGNED TASK: {assignment_label}.")
    lines.append(f"YOUR POSITION: {obs.lat:.4f}, {obs.lon:.4f}.")
    if peers:
        lines.append("PEERS: " + "; ".join(
            f"{p['id']}={p.get('assignment_label', '?')}" for p in peers))
    lines.append("")
    if obs.contacts:
        lines.append("CONTACTS IN RANGE:")
        for c in obs.contacts:
            dist = haversine_km(obs.lat, obs.lon, c.lat, c.lon)
            tag = "SUSPICIOUS" if c.is_suspicious else "benign"
            lines.append(
                f"  - id={c.id} [{tag}] class={c.label} dist={dist:.2f}km "
                f"course={c.heading:.0f}° spd={c.speed_kn:.0f}kn"
            )
    else:
        lines.append("CONTACTS IN RANGE: none.")
    if focus:
        lines.append("")
        lines.append(
            f"JUST IDENTIFIED — decide whether to report it now: id={focus.get('id')} "
            f"class={focus.get('label', '?')} flagged={focus.get('flagged', False)}. "
            "If it matches the mission's reporting criterion, choose action 'report'."
        )
    lines.append("")
    lines.append("Decide your reaction. JSON only.")
    return "\n".join(lines)
