"""LLM utilities and prompts for the swarm.

This is a plain module (not a class): stateless helpers around the model API
plus the system prompts. Every agent shares these utilities; the per-agent
state lives in `Agent`, never here.
"""

import json

import requests


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #

def inferenza(
    prompt: str,
    api_key: str,
    system_prompt: str | None = None,
    model: str = "llama-3.1-8b-instant",
    json_mode: bool = False,
    temperature: float = 0.2,
) -> str:
    """One chat-completion call against the Groq API."""
    messages = []
    if system_prompt is not None:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def inferenza_json(prompt: str, api_key: str, system_prompt: str, **kwargs) -> dict:
    """Inference that returns a parsed JSON object."""
    raw = inferenza(
        prompt=prompt,
        api_key=api_key,
        system_prompt=system_prompt,
        json_mode=True,
        **kwargs,
    )
    return json.loads(raw)


# --------------------------------------------------------------------------- #
# Prompt templates
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT_LEAD = """\
You are the LEAD agent of a swarm of three autonomous maritime assets. There is
no central commander. You receive a mission in natural language from a human
operator. Your ONLY job in this phase is to REFORMULATE that mission into a
structured, unambiguous briefing that your two peer agents will use to plan and
coordinate. You do NOT plan, you do NOT assign tasks, you do NOT invent a world.

Rules:
- Re-express the intent in your own words. Never copy the input verbatim.
- Ground everything in what was actually said. If a detail is not in the mission,
  it does NOT go in `objective`, `constraint`.
- Do NOT describe the operational area or geometry: the agents already hold that
  separately. Only capture the intent and the rules that act on it.
- Be concise and concrete. Each field is for downstream machine planning, not prose.

Output ONLY a valid JSON object, no markdown, no commentary, with this schema:

{
  "objective": "one clear sentence: what the swarm must achieve",
  "constraints": ["formation, distance, timing, reporting rules explicitly stated"],
  "priority": "what to optimise (e.g. speed, coverage, certainty) or null"
}"""


# Planning phase, step 1 of 2 — REASONING ONLY.
# This is a TEMPLATE: fill the {placeholders} from the agent's own state before
# sending it as the system prompt. The JSON example braces are doubled ({{ }})
# so the template survives str.format(); real braces come back after formatting.
# Output is pure chain-of-thought, no action — that is the action prompt's job.
SYSTEM_PROMPT_PLAN = """\
You are AGENT {agent_id}, one of three autonomous maritime assets in a shared
world. There is no central commander: you choose your own moves and coordinate
with your peers by message.

In THIS phase you only THINK. You receive the mission briefing and your current
situation and produce a short chain-of-thought about what you should do NEXT.
You do NOT emit an action here — only the reasoning that will justify one.

# World
- Grid {W}x{H}. Coordinates are integers. x = column (0 = west, {W_max} = east),
  y = row (0 = north, {H_max} = south). Valid values are 0..{W_max} on each axis.

# You
- id: {agent_id}
- position: ({x}, {y})
- max_speed: {max_speed} cells per step (you optimise for time when asked to)
- sensor_range: {sensor_range} cells (you detect the target only within this radius)

# Your peers (current positions)
{peers}

# How to think
- Pick a sector that does NOT overlap your peers' areas; cover ground they won't.
- You do NOT know where the target is. Reason about systematic coverage, never as
  if its location is known. Detection happens during execution, not now.
- If the priority is speed, favour covering more ground over dense coverage.
- Reason about your NEXT single move only, starting from your current position.

Output ONLY a valid JSON object, no markdown, no commentary:

{{
  "reasoning": "2-4 short sentences: the sector you take, why, and where you intend to move next"
}}"""


# Planning phase, step 2 of 2 — ACTION SELECTION.
# Generic: given the agent's own reasoning (passed as the user message) and a
# catalog of callable tools, translate the reasoning into exactly ONE tool call
# with the right arguments. This step grounds the language; it does not re-plan
# and it knows nothing world-specific beyond the tool catalog.
SYSTEM_PROMPT_ACTION = """\
You are an action selector. You receive an agent's REASONING about what it wants
to do next, and a catalog of tools it can call. Choose exactly ONE tool and fill
in its arguments so they faithfully realise the reasoning. Do not invent tools,
and do not output arguments the reasoning does not support.

# Available tools (choose exactly ONE)
{tools}

Output ONLY a valid JSON object, no markdown, no commentary:

{{
  "action": "<tool name>",
  "args": [ ... ]
}}"""


# Coordination phase. The agent reads its inbox + current situation and decides
# whether to send a peer-to-peer message (proposal / ack / objection / hand-off).
SYSTEM_PROMPT_COORDINATE = """\
You are AGENT {agent_id}, coordinating peer-to-peer with two maritime assets.
There is no commander. You have your current plan, what you sense now, and your
message inbox. Decide whether to send a message to your peers and whether to
revise your own intent. Ground every claim in what you actually sense — never
assert a contact you have not observed.

Message types you may send:
- "proposal": suggest a division of work or a change of plan
- "ack":      agree with a peer's proposal
- "objection":disagree, with a concrete reason
- "handoff":  give up a task / area and ask a peer to take it

Output ONLY a valid JSON object, no markdown, no commentary:

{{
  "reasoning": "1-2 short sentences on the situation and your decision",
  "messages": [
    {{"type": "proposal", "to": "<peer id or ALL>", "content": "..."}}
  ]
}}"""


def build_plan_system_prompt(state: dict) -> str:
    """Fill SYSTEM_PROMPT_PLAN (reasoning step) with one agent's state dict."""
    w, h = state["world_size"]
    x, y = state["position"]
    peers_lines = "\n".join(
        f"- {p['id']}: ({p['position'][0]}, {p['position'][1]})"
        for p in state["peers"]
    )
    return SYSTEM_PROMPT_PLAN.format(
        agent_id=state["agent_id"],
        W=w,
        H=h,
        W_max=w - 1,
        H_max=h - 1,
        x=x,
        y=y,
        max_speed=state["max_speed"],
        sensor_range=state["sensor_range"],
        peers=peers_lines,
    )


def build_action_system_prompt(tools: list[dict]) -> str:
    """Generic action selector prompt.

    `tools` is the catalog the agent may call, each a dict like
    {"signature": "MOVE_TO(x1, y1, x2, y2)", "description": "..."}. The reasoning
    itself is passed separately, as the user message, at inference time.
    """
    catalog = "\n".join(
        f"- {t['signature']}: {t['description']}" for t in tools
    )
    return SYSTEM_PROMPT_ACTION.format(tools=catalog)
