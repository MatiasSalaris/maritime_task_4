from __future__ import annotations
import math
import time
import uuid
from models.agent import AgentState, AgentStatus, AgentType, Observation, Position, Action
from models.messages import P2PMessage
from models.world import Contact, Geofence, POI, WorldState
from providers.base import AbstractPlatformProvider
from providers.simulation.physics import move, distance_km
from providers.simulation.synthetic_ais import initial_contacts

# ── Demo area: Strait of Sicily ───────────────────────────────────────────────
_BOUNDS = dict(lat_min=37.42, lat_max=37.60, lon_min=15.00, lon_max=15.28)
_SENSOR_RANGE_KM = 12.0
_MAX_HISTORY = 120   # path history points kept per agent
_AGENT_COLORS = ["#00d4ff", "#00ff88", "#ff8800"]


class SimulatedPlatformProvider(AbstractPlatformProvider):

    def __init__(self) -> None:
        self.agents: list[AgentState] = self._init_agents()
        self.contacts: list[Contact] = initial_contacts()
        self.pois: list[POI] = self._init_pois()
        self.geofences: list[Geofence] = self._init_geofences()
        self.mission: str | None = None
        self.world_time: float = time.time()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_agents(self) -> list[AgentState]:
        return [
            AgentState(
                id="agent_0", name="Alpha", type=AgentType.USV,
                position=Position(lat=37.505, lon=15.07),
                heading=45, speed_kn=8.0,
            ),
            AgentState(
                id="agent_1", name="Bravo", type=AgentType.USV,
                position=Position(lat=37.490, lon=15.16),
                heading=180, speed_kn=8.0,
            ),
            AgentState(
                id="agent_2", name="Charlie", type=AgentType.USV,
                position=Position(lat=37.545, lon=15.17),
                heading=270, speed_kn=8.0,
            ),
        ]

    def _init_pois(self) -> list[POI]:
        return [
            POI(id="poi_1", position=Position(lat=37.555, lon=15.22), label="POI Alpha"),
            POI(id="poi_2", position=Position(lat=37.445, lon=15.06), label="POI Bravo"),
            POI(id="poi_3", position=Position(lat=37.510, lon=15.19), label="POI Charlie"),
        ]

    def _init_geofences(self) -> list[Geofence]:
        b = _BOUNDS
        return [
            Geofence(
                id="patrol_area", type="patrol_area",
                coordinates=[
                    Position(lat=b["lat_min"], lon=b["lon_min"]),
                    Position(lat=b["lat_max"], lon=b["lon_min"]),
                    Position(lat=b["lat_max"], lon=b["lon_max"]),
                    Position(lat=b["lat_min"], lon=b["lon_max"]),
                ],
            )
        ]

    # ── AbstractPlatformProvider implementation ───────────────────────────────

    async def tick(self, dt: float) -> None:
        self.world_time += dt
        self._move_agents(dt)
        self._move_contacts(dt)

    async def get_observation(
        self, agent_id: str, inbox: list[P2PMessage]
    ) -> Observation | None:
        agent = self._agent(agent_id)
        if agent is None:
            return None

        visible = [
            c.model_dump()
            for c in self.contacts
            if distance_km(agent.position, c.position) <= _SENSOR_RANGE_KM
        ]
        return Observation(
            agent_id=agent_id,
            position=agent.position,
            heading=agent.heading,
            speed_kn=agent.speed_kn,
            contacts_in_range=visible,
            messages_inbox=[m.model_dump() for m in inbox],
            world_time=self.world_time,
            mission=self.mission,
        )

    async def apply_action(self, agent_id: str, action: dict) -> None:
        agent = self._agent(agent_id)
        if agent is None:
            return
        parsed = Action.model_validate(action)
        if parsed.heading is not None:
            agent.heading = parsed.heading % 360
        if parsed.speed_kn is not None:
            agent.speed_kn = max(0.0, min(25.0, parsed.speed_kn))
        if parsed.planned_path is not None:
            agent.planned_path = parsed.planned_path
        if parsed.current_task is not None:
            agent.current_task = parsed.current_task

    async def get_world_state(self) -> WorldState:
        return WorldState(
            time=self.world_time,
            agents=list(self.agents),
            contacts=list(self.contacts),
            pois=list(self.pois),
            geofences=list(self.geofences),
            mission=self.mission,
        )

    async def set_mission(self, mission: str) -> None:
        self.mission = mission

    async def set_agent_connected(self, agent_id: str, connected: bool) -> None:
        agent = self._agent(agent_id)
        if agent:
            agent.connected = connected
            if not connected:
                agent.cot_text = ""

    async def update_agent_cot(self, agent_id: str, chunk: str) -> None:
        agent = self._agent(agent_id)
        if agent:
            agent.cot_text += chunk
            # Keep buffer bounded
            if len(agent.cot_text) > 2000:
                agent.cot_text = agent.cot_text[-2000:]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _agent(self, agent_id: str) -> AgentState | None:
        return next((a for a in self.agents if a.id == agent_id), None)

    def _move_agents(self, dt: float) -> None:
        b = _BOUNDS
        for agent in self.agents:
            if agent.status == AgentStatus.SILENT:
                continue

            new_pos = move(agent.position, agent.heading, agent.speed_kn, dt)

            # Bounce off patrol area boundaries
            bounced = False
            if not (b["lat_min"] < new_pos.lat < b["lat_max"]):
                agent.heading = (180 - agent.heading) % 360
                bounced = True
            if not (b["lon_min"] < new_pos.lon < b["lon_max"]):
                agent.heading = (360 - agent.heading) % 360
                bounced = True

            if not bounced:
                agent.position = new_pos
                agent.path_history.append(Position(lat=new_pos.lat, lon=new_pos.lon))
                if len(agent.path_history) > _MAX_HISTORY:
                    agent.path_history = agent.path_history[-_MAX_HISTORY:]

    def _move_contacts(self, dt: float) -> None:
        for c in self.contacts:
            c.position = move(c.position, c.heading, c.speed_kn, dt)
            # Wrap-around within a slightly larger area so contacts stay visible
            if not (37.38 < c.position.lat < 37.65):
                c.heading = (180 - c.heading) % 360
            if not (14.90 < c.position.lon < 15.35):
                c.heading = (360 - c.heading) % 360
