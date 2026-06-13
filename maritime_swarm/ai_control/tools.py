"""The Tool abstraction — the core of the AI control layer.

A *Tool* is a discrete capability the LLM can invoke, e.g. ``go_to(lat, lon)``.
The flow is:

1. The LLM returns a structured call ``{"tool": <name>, "args": {...}}``.
2. :meth:`ToolRegistry.build` validates the name and arguments and constructs a
   live :class:`Tool` instance.
3. Each world tick, :meth:`Tool.step` is called with the latest
   :class:`Observation` and returns a :class:`ToolInvocation` — the concrete
   action to send to the world model plus a status. The tool runs until it
   reports ``DONE`` or ``FAILED``.

Tools translate high-level intent into the world model's low-level action
schema (``heading`` / ``speed_kn`` / ``planned_path`` / ``current_task``). They
never touch the simulator directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from maritime_swarm.ai_control.geo import clamp
from maritime_swarm.ai_control.observation import Observation


class ToolError(ValueError):
    """Raised when a tool call cannot be built from the given arguments."""


@dataclass
class Bounds:
    """Operating-area bounding box. Tools clamp targets to stay inside it."""

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def clamp_point(self, lat: float, lon: float, inset: float = 0.02) -> tuple[float, float]:
        """Clamp a point inside the box, with a small inset off the edges.

        The inset keeps agents from sitting exactly on a boundary, where the
        world model's reflective bounds would otherwise make them jitter.
        """
        lat_pad = (self.lat_max - self.lat_min) * inset
        lon_pad = (self.lon_max - self.lon_min) * inset
        return (
            clamp(lat, self.lat_min + lat_pad, self.lat_max - lat_pad),
            clamp(lon, self.lon_min + lon_pad, self.lon_max - lon_pad),
        )

    def center(self) -> tuple[float, float]:
        return ((self.lat_min + self.lat_max) / 2, (self.lon_min + self.lon_max) / 2)


@dataclass
class ToolContext:
    """Per-agent execution context shared with every tool the agent runs."""

    agent_id: str
    agent_name: str
    agent_type: str            # "USV" | "UAV"
    cruise_speed_kn: float
    arrival_km: float = 0.3
    bounds: Bounds | None = None


class ToolStatus(str, Enum):
    RUNNING = "running"   # still working; keep calling step()
    DONE = "done"         # completed successfully
    FAILED = "failed"     # cannot proceed (e.g. target lost)


@dataclass
class ToolInvocation:
    """One step's result: an optional world action plus the tool's status."""

    action: dict[str, Any] | None
    status: ToolStatus
    note: str = ""

    @property
    def finished(self) -> bool:
        return self.status is not ToolStatus.RUNNING


class Tool(ABC):
    """Base class for all tools.

    Subclasses declare ``name``, ``description`` and ``parameters`` (a small
    JSON-schema-like mapping used to document the tool to the LLM), implement
    :meth:`build` to validate/parse arguments, and :meth:`step` to advance.
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    # param_name -> {"type": str, "description": str, "required": bool}
    parameters: ClassVar[dict[str, dict[str, Any]]] = {}

    # ── Schema / documentation ────────────────────────────────────────────
    @classmethod
    def schema(cls) -> dict[str, Any]:
        """Machine-readable schema (handy for prompts or function-calling)."""
        return {
            "name": cls.name,
            "description": cls.description,
            "parameters": cls.parameters,
        }

    @classmethod
    def signature(cls) -> str:
        """Human-readable call signature, e.g. ``go_to(lat, lon)``."""
        return f"{cls.name}({', '.join(cls.parameters.keys())})"

    # ── Lifecycle ─────────────────────────────────────────────────────────
    @classmethod
    @abstractmethod
    def build(cls, args: dict[str, Any], ctx: ToolContext) -> "Tool":
        """Validate ``args`` and return a ready-to-run instance.

        Raise :class:`ToolError` for missing or malformed arguments.
        """

    @abstractmethod
    def step(self, obs: Observation, ctx: ToolContext) -> ToolInvocation:
        """Advance one tick and return the action to apply + a status."""

    @abstractmethod
    def describe(self) -> str:
        """Short one-line summary of the active instance (for logs/UI)."""


# ── helpers for argument validation ──────────────────────────────────────────
def require_number(args: dict[str, Any], key: str) -> float:
    if key not in args or args[key] is None:
        raise ToolError(f"missing required argument '{key}'")
    try:
        return float(args[key])
    except (TypeError, ValueError) as exc:
        raise ToolError(f"argument '{key}' must be a number, got {args[key]!r}") from exc


def require_str(args: dict[str, Any], key: str) -> str:
    if key not in args or args[key] is None:
        raise ToolError(f"missing required argument '{key}'")
    value = str(args[key]).strip()
    if not value:
        raise ToolError(f"argument '{key}' must be a non-empty string")
    return value


class ToolRegistry:
    """A named collection of tools the LLM is allowed to call."""

    def __init__(self) -> None:
        self._tools: dict[str, type[Tool]] = {}

    def register(self, tool_cls: type[Tool]) -> type[Tool]:
        if not tool_cls.name:
            raise ValueError(f"{tool_cls.__name__} has no 'name'")
        self._tools[tool_cls.name] = tool_cls
        return tool_cls

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def get(self, name: str) -> type[Tool]:
        if name not in self._tools:
            raise ToolError(
                f"unknown tool '{name}'. Available: {', '.join(self._tools) or '(none)'}"
            )
        return self._tools[name]

    def build(self, name: str, args: dict[str, Any] | None, ctx: ToolContext) -> Tool:
        return self.get(name).build(args or {}, ctx)

    def prompt_block(self) -> str:
        """Render the toolset as documentation for an LLM system prompt."""
        lines: list[str] = []
        for tool_cls in self._tools.values():
            lines.append(f"- {tool_cls.signature()}: {tool_cls.description}")
            for pname, spec in tool_cls.parameters.items():
                req = "" if spec.get("required", True) else " (optional)"
                lines.append(
                    f"    • {pname} ({spec.get('type', 'any')}){req}: {spec.get('description', '')}"
                )
        return "\n".join(lines)
