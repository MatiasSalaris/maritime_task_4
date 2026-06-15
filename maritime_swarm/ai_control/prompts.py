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

ACTION_SENTINEL = "###ACTION###"

_FEWSHOT = """\
EXAMPLES (format only — your situation differs). Reasoning prose FIRST, then the sentinel, then ONE JSON object:

Alpha took the north, so the south-west is the gap. My plan: cover SW for the patrol split. I'll head there and tell the team.
###ACTION###
{"plan":"Patrol SW sector (agreed split: Alpha N, Bravo SW). Done when SW swept; then re-coordinate.","messages":[{"to":"all","type":"ack","content":"Copy — I'll patrol SW."}],"action":{"tool":"patrol_sector","args":{"sector":"SW"}}}

I arrived at my escort station; feedback says I'm 480 m off the vessel, order is 500 m, close enough. Now I just keep station.
###ACTION###
{"plan":"Step 2/2: hold 500 m escort station off the vessel and match its track.","messages":[],"action":{"tool":"hold_position","args":{"seconds":30}}}
"""

_OUTPUT_FORMAT = (
    "OUTPUT FORMAT — follow EXACTLY:\n"
    "1. First, think out loud in 2-4 SHORT sentences of plain prose (your visible chain-of-thought): "
    "what changed since last turn, where you are against your plan, and what you'll do now.\n"
    f"2. Then a line containing ONLY the sentinel: {ACTION_SENTINEL}\n"
    "3. Then ONE JSON object, exactly:\n"
    '   {"plan":"<your updated short plan>",'
    '"messages":[{"to":"all|agent_0|agent_1|agent_2","type":"<type>","content":"<short text>"}],'
    '"action":{"tool":"<tool name>","args":{...}}}\n'
    "`plan` is yours to carry forward — keep it short (role, current objective+target, which mission "
    "step you're on, how you'll know it's done). messages may be empty. Output nothing after the JSON.\n\n"
)

_LEADER_ROLE = (
    "YOUR ROLE — LEAD ASSET (entry point): the human's order is delivered to YOU ALONE; your peers "
    "never see the raw text. When the order is new or has CHANGED, interpret it and brief the team: "
    "send an 'intent' message to 'all' re-expressing it in your own operational words — never verbatim. "
    "Your peers act on your briefing. You stay a peer for who-does-what: you PROPOSE, never command.\n\n"
)

_PEER_ROLE = (
    "YOUR ROLE — PEER ASSET: you do NOT receive the human's order. Your working intent is what the "
    "LEAD briefed over the bus (the 'intent' message). Negotiate as an equal — object with a "
    "counter-proposal if a better split exists, otherwise ack and commit.\n\n"
)


def build_decision_system_prompt(registry: ToolRegistry, is_leader: bool = False) -> str:
    return (
        "You are ONE of three autonomous maritime assets operating as a peer team — there is NO "
        "commander and no central planner. You accomplish the mission by REASONING, COMMUNICATING "
        "with your two peers, and ACTING. Coordination must emerge between you.\n\n"
        + (_LEADER_ROLE if is_leader else _PEER_ROLE)
        + "HOW YOU OPERATE:\n"
        "- KEEP A PLAN. You maintain your own short plan and carry it forward turn to turn. Each turn "
        "you are shown the plan you wrote last time and WHAT HAPPENED SINCE (did you move, where you "
        "are vs your target, peer distances). Judge progress against your plan, update it, and act to "
        "advance it. When your current step is done, move the plan to the next step — don't sit idle "
        "while the mission has more to do.\n"
        "- COMPOSE PRIMITIVES. The tools are primitives (move, go_to, patrol a sector, go to a POI, "
        "hold). There is no dedicated tool for every order — achieve higher-level intent by sequencing "
        "primitives across turns, using the feedback to tell when each step is complete.\n"
        "- COORDINATE, DON'T COMMAND. You decide ONLY your own next action. Say what you intend "
        "(proposal), answer peers (ack / objection-with-counter / handoff); converge on a division of "
        "work, then commit and execute your part. If you and a peer want the same thing, the lower-id "
        "asset (agent_0<agent_1<agent_2) keeps it and the other takes the complementary part. Cover "
        "for a peer that has gone silent.\n"
        "- STAY GROUNDED. Only use contact/POI ids that actually appear below; never invent them or "
        "act on something that isn't there. Bind every spatial word in the order ('the area', 'the "
        "perimeter', 'north', 'rendezvous') to the geometry given below.\n\n"
        "ACTIONS (choose exactly one tool):\n"
        f"{registry.prompt_block()}\n\n"
        "MESSAGE TYPES: intent (lead re-expresses the mission for the team), proposal (suggest a "
        "plan), ack (agree), objection (disagree + counter), handoff (take/hand over a task), "
        "report (flag/annotate a contact), status (info).\n\n"
        + _OUTPUT_FORMAT
        + _FEWSHOT
    )


def build_decision_user_prompt(
    obs: Observation, ctx: ToolContext, scene: Scene, mission: str,
    peers: list[dict[str, Any]], shared_contacts: list[dict[str, Any]],
    messages: list[dict[str, Any]], current_task: str | None,
    task_status: str = "idle", silent_peers: list[str] | None = None,
    outbox: list[dict[str, Any]] | None = None, is_leader: bool = False,
    plan: str | None = None, feedback: str | None = None,
) -> str:
    """The full state the asset reasons on: per-agent, shared (mission/comms), world."""
    b = scene.bounds
    mission_label = (
        "MISSION ORDER (from the human — interpret and brief your peers, do NOT relay verbatim)"
        if is_leader
        else "TEAM INTENT (as briefed to you by the lead asset)"
    )
    L = [f"{mission_label}: {mission}", ""]

    # ── your plan (carried from last turn) + what happened since ──────────
    L.append(f"YOUR PLAN (from last turn — update it): {plan or '(none yet — make one)'}")
    if feedback:
        L.append(f"SINCE YOUR LAST DECISION: {feedback}")
    L.append("")

    # ── per-agent state ───────────────────────────────────────────────────
    L.append("YOUR STATE:")
    L.append(f"  id={ctx.agent_id} name={ctx.agent_name} type={ctx.agent_type} "
             f"sensor={_SENSOR_BY_TYPE.get(ctx.agent_type, 'sensors')} cruise={ctx.cruise_speed_kn:.0f}kn")
    L.append(f"  position={obs.lat:.4f},{obs.lon:.4f} heading={obs.heading:.0f}° speed={obs.speed_kn:.1f}kn")
    L.append(f"  current_task={current_task or 'none'} status={task_status}")
    L.append(f"  contacts_in_range={len(obs.contacts)}")
    L.append("")

    # ── world: area + contacts ────────────────────────────────────────────
    L.append(f"OPERATING AREA (bounding box): lat {b.lat_min:.3f}..{b.lat_max:.3f}, lon {b.lon_min:.3f}..{b.lon_max:.3f}.")
    if scene.area_corners:
        L.append("AREA BOUNDARY (the marked area — corners in order; its edges are the 'perimeter'): "
                 + "; ".join(f"({lat:.3f},{lon:.3f})" for lat, lon in scene.area_corners))
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
    L.append("TEAM (peers you can currently hear — distances are FROM YOU):")
    if peers:
        for p in peers:
            dist_km = haversine_km(obs.lat, obs.lon, p["lat"], p["lon"])
            dist_str = f"{dist_km * 1000:.0f} m" if dist_km < 1.0 else f"{dist_km:.1f} km"
            L.append(f"  - {p['id']} ({p.get('type','?')}) at {p['lat']:.4f},{p['lon']:.4f} "
                     f"— {dist_str} from you — task: {p.get('task') or 'unknown'}")
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
    L.append("Update your plan in light of what happened since last turn, then choose ONE action that "
             "advances it. Reason briefly, coordinate with peers as needed.")
    return "\n".join(L)
