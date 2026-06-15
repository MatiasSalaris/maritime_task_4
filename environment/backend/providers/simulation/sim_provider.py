from __future__ import annotations
import math
import time
import uuid
from models.agent import AgentState, AgentStatus, AgentType, Observation, Position, Action
from models.messages import P2PMessage
from models.world import Contact, ContactStatus, Geofence, POI, WorldState
from providers.base import AbstractPlatformProvider
from providers.simulation.physics import move, distance_km
from providers.simulation.synthetic_ais import initial_contacts
from providers.simulation.scenarios import build_scenario

# ── Demo area: Strait of Sicily ───────────────────────────────────────────────
_BOUNDS = dict(lat_min=37.42, lat_max=37.60, lon_min=15.00, lon_max=15.28)
_SENSOR_RANGE_KM = 12.0
_MAX_HISTORY = 400   # path history points kept per agent
_MIN_HIST_DIST_M = 8 # minimum movement to record a new history point
_AGENT_COLORS = ["#00d4ff", "#00ff88", "#ff8800"]

_UAV_ALTITUDE_M         = 1000.0
_UAV_HALF_FOV_DEG       = 60.0   # camera half-FOV
_UAV_SENSOR_RADIUS_KM   = _UAV_ALTITUDE_M * math.tan(math.radians(_UAV_HALF_FOV_DEG)) / 1000.0  # ≈1.73 km
_USV_SENSOR_RANGE_KM    = 4.0    # radar range — sized for demo area (~25×20 km)


class SimulatedPlatformProvider(AbstractPlatformProvider):

    def __init__(self) -> None:
        self.agents: list[AgentState] = self._init_agents()
        self.contacts: list[Contact] = initial_contacts()
        self.pois: list[POI] = self._init_pois()
        self.geofences: list[Geofence] = self._init_geofences()
        self.mission: str | None = None
        self.doctrine: str | None = None
        self.aor: dict | None = None
        self.world_time: float = time.time()
        self._nato_counter: int = 0
        self._pending_events: list[dict] = []

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_agents(self) -> list[AgentState]:
        return [
            AgentState(
                id="agent_0", name="Alpha", type=AgentType.USV,
                position=Position(lat=37.505, lon=15.07),
                heading=45, speed_kn=8.0,
                sensor_range_km=_USV_SENSOR_RANGE_KM, altitude_m=0.0,
            ),
            AgentState(
                id="agent_1", name="Bravo", type=AgentType.USV,
                position=Position(lat=37.490, lon=15.16),
                heading=180, speed_kn=8.0,
                sensor_range_km=_USV_SENSOR_RANGE_KM, altitude_m=0.0,
            ),
            AgentState(
                id="agent_2", name="Charlie", type=AgentType.UAV,
                position=Position(lat=37.545, lon=15.17),
                heading=270, speed_kn=8.0,
                sensor_range_km=_UAV_SENSOR_RADIUS_KM, altitude_m=_UAV_ALTITUDE_M,
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
        self._run_sensor_detection(dt)

    async def get_observation(
        self, agent_id: str, inbox: list[P2PMessage]
    ) -> Observation | None:
        agent = self._agent(agent_id)
        if agent is None:
            return None

        visible = [
            c.model_dump()
            for c in self.contacts
            if distance_km(agent.position, c.position) <= agent.sensor_range_km
        ]
        # The human's order goes ONLY to the lead asset (the entry point, by
        # convention the lowest-id agent). Peers receive no mission text — they
        # learn the working intent from the lead's peer-to-peer briefing. This is
        # the "natural-language mission interface to the leader, propagated to the
        # peers" model: no agent but the lead ever sees the raw order.
        mission = self.mission if agent_id == self._leader_id() else None
        return Observation(
            agent_id=agent_id,
            position=agent.position,
            heading=agent.heading,
            speed_kn=agent.speed_kn,
            contacts_in_range=visible,
            messages_inbox=[m.model_dump() for m in inbox],
            world_time=self.world_time,
            mission=mission,
            pois=[p.model_dump() for p in self.pois],
            aor=self.aor,
        )

    def _leader_id(self) -> str | None:
        """The entry-point asset that receives the human's order (lowest id)."""
        return min((a.id for a in self.agents), default=None)

    async def apply_action(self, agent_id: str, action: dict) -> None:
        agent = self._agent(agent_id)
        if agent is None:
            return
        parsed = Action.model_validate(action)
        if parsed.heading is not None:
            agent.heading = parsed.heading % 360
        if parsed.speed_kn is not None:
            agent.speed_kn = max(0.0, min(100.0, parsed.speed_kn))
        if parsed.planned_path is not None:
            agent.planned_path = parsed.planned_path
        if parsed.current_task is not None:
            agent.current_task = parsed.current_task
        if parsed.warp_to is not None:
            # Only record history if we've moved far enough (avoids flooding)
            ref = agent.path_history[-1] if agent.path_history else agent.position
            if distance_km(ref, parsed.warp_to) * 1000 >= _MIN_HIST_DIST_M:
                agent.path_history.append(Position(lat=agent.position.lat, lon=agent.position.lon))
                if len(agent.path_history) > _MAX_HISTORY:
                    agent.path_history = agent.path_history[-_MAX_HISTORY:]
            agent.position = parsed.warp_to

    async def get_world_state(self) -> WorldState:
        sensor_footprints = {
            agent.id: self._sensor_footprint_polygon(agent)
            for agent in self.agents
        }
        detection_events = list(self._pending_events)
        self._pending_events.clear()

        return WorldState(
            time=self.world_time,
            agents=list(self.agents),
            contacts=list(self.contacts),
            pois=list(self.pois),
            geofences=list(self.geofences),
            mission=self.mission,
            doctrine=self.doctrine,
            aor=self.aor,
            sensor_footprints=sensor_footprints,
            detection_events=detection_events,
        )

    async def set_doctrine(self, code: str) -> None:
        self.doctrine = code

    async def set_aor(self, geojson: dict | None) -> None:
        self.aor = geojson

    async def set_mission(self, mission: str) -> None:
        self.mission = mission

    async def set_agent_connected(self, agent_id: str, connected: bool) -> None:
        agent = self._agent(agent_id)
        if agent:
            agent.connected = connected
            if not connected:
                agent.cot_text = ""

    async def reset(self) -> None:
        # Restart from scratch: return every agent to its spawn pose and stop it,
        # while preserving identity and any live WS connection. Contacts and
        # mission state are rebuilt fresh so a new simulation starts clean.
        spawn = {a.id: a for a in self._init_agents()}
        for agent in self.agents:
            base = spawn.get(agent.id)
            if base is not None:
                agent.position = Position(lat=base.position.lat, lon=base.position.lon)
                agent.heading = base.heading
            agent.speed_kn = 0.0          # stop physics until new orders arrive
            agent.status = AgentStatus.OPERATIONAL
            agent.path_history = []
            agent.planned_path = []
            agent.cot_text = ''
            agent.current_task = None
        self.contacts = initial_contacts()
        self.mission = None
        self._detection_state: dict[str, str] = {}
        self._pending_events.clear()
        self._nato_counter = 0

    async def load_scenario(self, scenario_id: str) -> dict:
        """Reconfigure the world for a chosen scenario and set its mission.

        Resets agents to spawn, rebuilds the contacts/POIs/operating-area from
        the scenario definition, and returns the scenario's natural-language
        mission for the lead asset.
        """
        await self.reset()
        sc = build_scenario(scenario_id)
        self.contacts = sc["contacts"]
        self.pois = sc["pois"]   # only scenarios that define POIs show any (no demo fallback)
        self.aor = sc["aor"]
        self.mission = sc["mission"]
        # Spread the agents out for a randomised scenario so they don't all
        # start clustered (the 'open sea' picture has no fixed formation).
        if scenario_id == "random":
            import random
            b = _BOUNDS
            for agent in self.agents:
                agent.position = Position(
                    lat=round(random.uniform(b["lat_min"], b["lat_max"]), 4),
                    lon=round(random.uniform(b["lon_min"], b["lon_max"]), 4))
        return {"scenario": scenario_id, "mission": self.mission}

    async def update_agent_cot(self, agent_id: str, chunk: str) -> None:
        agent = self._agent(agent_id)
        if agent:
            agent.cot_text += chunk
            # Keep a rolling window of recent chain-of-thought (newline-separated
            # thoughts). Trim from the front on a line boundary so the oldest
            # visible thought stays whole.
            if len(agent.cot_text) > 6000:
                trimmed = agent.cot_text[-6000:]
                nl = trimmed.find("\n")
                agent.cot_text = trimmed[nl + 1:] if nl != -1 else trimmed

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _agent(self, agent_id: str) -> AgentState | None:
        return next((a for a in self.agents if a.id == agent_id), None)

    def _sensor_footprint_polygon(self, agent: AgentState) -> list[list[float]]:
        """Compute a 32-point circle polygon around agent position with sensor_range_km radius.
        Returns a closed ring of [lon, lat] pairs (first == last)."""
        lat = agent.position.lat
        lon = agent.position.lon
        r = agent.sensor_range_km

        lat_rad = math.radians(lat)
        dlat = r / 111.32
        dlon = r / (111.32 * math.cos(lat_rad)) if math.cos(lat_rad) != 0 else r / 111.32

        num_points = 32
        ring = []
        for i in range(num_points):
            angle = math.radians(i * 360.0 / num_points)
            pt_lon = lon + dlon * math.cos(angle)
            pt_lat = lat + dlat * math.sin(angle)
            ring.append([pt_lon, pt_lat])
        # Close the ring
        ring.append(ring[0])
        return ring

    def _run_sensor_detection(self, dt: float) -> None:
        """Check each contact against all agent sensor ranges and update detection state."""
        for contact in self.contacts:
            detecting_agents = []
            for agent in self.agents:
                if distance_km(agent.position, contact.position) <= agent.sensor_range_km:
                    detecting_agents.append(agent.id)

            prev_status = contact.status

            if detecting_agents:
                # First detection: assign NATO track ID
                if prev_status == ContactStatus.UNKNOWN:
                    self._nato_counter += 1
                    n = self._nato_counter
                    if contact.flagged:
                        nato_id = f"TGT-{n:03d}"
                    elif contact.mmsi:
                        nato_id = f"AIS-{n:03d}"
                    else:
                        nato_id = f"UNK-{n:03d}"
                    contact.nato_id = nato_id
                    contact.first_seen = self.world_time
                    self._pending_events.append({
                        "contact_id": contact.id,
                        "nato_id": nato_id,
                        "position": {"lon": contact.position.lon, "lat": contact.position.lat},
                        "time": self.world_time,
                    })

                contact.detecting_agents = detecting_agents
                contact.status = ContactStatus.ACTIVE
                contact.last_seen = self.world_time
                contact.last_known_position = Position(lat=contact.position.lat, lon=contact.position.lon)

            else:
                contact.detecting_agents = []
                if prev_status == ContactStatus.ACTIVE:
                    contact.status = ContactStatus.GHOST
                elif prev_status == ContactStatus.UNKNOWN:
                    contact.status = ContactStatus.UNKNOWN  # no change

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

            if not bounced and agent.speed_kn > 0:
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
