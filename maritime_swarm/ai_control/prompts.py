"""Prompt construction for LLM-driven tool selection."""

from __future__ import annotations

from maritime_swarm.ai_control.geo import haversine_km
from maritime_swarm.ai_control.observation import Observation
from maritime_swarm.ai_control.scene import Scene
from maritime_swarm.ai_control.tools import ToolContext, ToolRegistry

_SENSOR_BY_TYPE = {
    "USV": "360° surface radar",
    "UAV": "downward-looking EO/IR camera",
}


def build_system_prompt(registry: ToolRegistry) -> str:
    """The fixed role + tool contract for an autonomous maritime asset."""
    return (
        "You are the autonomous command logic for a single maritime asset operating as part "
        "of a three-vehicle patrol swarm in the Strait of Sicily. On each decision you choose "
        "EXACTLY ONE tool to execute next, based on your mission and what your sensors currently see.\n\n"
        "STANDING DOCTRINE (always applies):\n"
        "- This is a PERSISTENT, CONTINUOUS operation. The mission has NO end state. It is a "
        "standing tasking, not a one-shot goal.\n"
        "- NEVER consider the mission 'complete' and NEVER stop operating. Even after you have "
        "achieved the stated objective (e.g. all contacts identified, an area swept), you KEEP "
        "GOING: resume patrolling, maintain area coverage, and periodically re-verify the picture.\n"
        "- Only stop if the operator explicitly orders it (e.g. return to base / standby). Absent "
        "such an order, always pick a tool that keeps you active.\n"
        "- Keep moving and stay useful; do not loiter in one spot. Use hold_position only briefly "
        "and only to observe something specific.\n\n"
        "Available tools:\n"
        f"{registry.prompt_block()}\n\n"
        "Decision policy:\n"
        "- Prioritise investigating contacts that are UNKNOWN or flagged/suspicious.\n"
        "- Commercial/fishing AIS contacts are normally benign; do not chase them unless ordered.\n"
        "- When nothing of interest is sensed, PATROL: pick a NEW go_to waypoint inside the "
        "operating area that improves coverage — somewhere different from where you are now, so the "
        "swarm keeps sweeping the whole area over time.\n"
        "- After finishing any task, immediately choose the next patrol/coverage action; do not idle.\n"
        "- Stay inside the operating-area bounds.\n\n"
        "Respond with a SINGLE JSON object and nothing else, in exactly this form:\n"
        '{"reasoning": "<one short sentence>", "tool": "<tool name>", "args": {<arguments>}}'
    )


def build_user_prompt(obs: Observation, ctx: ToolContext, scene: Scene, mission: str) -> str:
    """The live situation for this agent on this decision."""
    b = scene.bounds
    lines: list[str] = []
    lines.append(f"MISSION: {mission}")
    lines.append("")
    lines.append(
        f"YOU ARE: {ctx.agent_name} ({ctx.agent_id}), a {ctx.agent_type} with {_SENSOR_BY_TYPE.get(ctx.agent_type, 'sensors')}; "
        f"cruise speed {ctx.cruise_speed_kn:.0f} kn."
    )
    lines.append(
        f"OPERATING AREA (stay inside): lat {b.lat_min:.3f}..{b.lat_max:.3f}, lon {b.lon_min:.3f}..{b.lon_max:.3f}."
    )
    if scene.pois:
        poi_txt = "; ".join(f"{p.label} @ {p.lat:.3f},{p.lon:.3f}" for p in scene.pois)
        lines.append(f"POINTS OF INTEREST: {poi_txt}.")
    lines.append("")
    lines.append(
        f"CURRENT STATE: position {obs.lat:.4f}, {obs.lon:.4f}; heading {obs.heading:.0f}°; speed {obs.speed_kn:.1f} kn."
    )

    if obs.contacts:
        lines.append("CONTACTS IN SENSOR RANGE:")
        for c in obs.contacts:
            dist = haversine_km(obs.lat, obs.lon, c.lat, c.lon)
            tag = "SUSPICIOUS" if c.is_suspicious else "benign"
            lines.append(
                f"  - id={c.id} [{tag}] class={c.label} pos={c.lat:.4f},{c.lon:.4f} "
                f"course={c.heading:.0f}° spd={c.speed_kn:.0f}kn dist={dist:.2f}km"
            )
    else:
        lines.append("CONTACTS IN SENSOR RANGE: none.")

    lines.append("")
    lines.append("Choose the single best next tool. Respond with the JSON object only.")
    return "\n".join(lines)
