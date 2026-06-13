"""One autonomous asset, driven by its own LLM instance.

An Agent holds the per-agent state (position, heading, current task, plan,
inbox/outbox, last reasoning) and exposes the phases of its loop. The LEAD is
just the agent that receives the mission first and re-broadcasts a briefing — it
does NOT command its peers.

Skeleton only: method bodies are TODO. The LLM utilities and prompts live in
`swarm.llm`.
"""

from swarm import llm  # noqa: F401  (used by the implementation)


class Agent:
    def __init__(
        self,
        agent_id: str,
        position: tuple[int, int],
        max_speed: int = 2,
        sensor_range: int = 2,
        is_lead: bool = False,
    ):
        self.id = agent_id
        self.pos = list(position)
        self.heading = 0.0
        self.max_speed = max_speed
        self.sensor_range = sensor_range
        self.is_lead = is_lead

        # Mission / task state
        self.briefing: dict | None = None
        self.plan: list[dict] = []

        # Coordination state
        self.inbox: list[dict] = []
        self.outbox: list[dict] = []

        # What the spectator view reads
        self.last_reasoning: str = ""
        self.last_observation: dict | None = None

        # Failure honesty
        self.alive = True

    # ----------------------------------------------------------------- #
    # LEAD phase
    # ----------------------------------------------------------------- #
    def reformulate_mission(self, mission: str, api_key: str) -> dict:
        """LEAD only: turn natural-language intent into a structured briefing."""
        raise NotImplementedError  # TODO

    # ----------------------------------------------------------------- #
    # Planning phase
    # ----------------------------------------------------------------- #
    def make_plan(self, briefing: dict, peers: list["Agent"], world_size, api_key: str) -> dict:
        """Turn the shared briefing + own state into a concrete plan."""
        raise NotImplementedError  # TODO

    # ----------------------------------------------------------------- #
    # Coordination phase
    # ----------------------------------------------------------------- #
    def coordinate(self, api_key: str) -> list[dict]:
        """Read the inbox + situation, maybe emit peer-to-peer messages."""
        raise NotImplementedError  # TODO

    # ----------------------------------------------------------------- #
    # Perception
    # ----------------------------------------------------------------- #
    def perceive(self, world) -> dict:
        """Pull what the world lets this agent observe right now."""
        raise NotImplementedError  # TODO
