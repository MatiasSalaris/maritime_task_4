"""AI control layer for the maritime world model.

This package is the *brain* side of the system. It is deliberately kept
**separate from the world model** (``environment/backend``): it never imports
the simulator, it only talks to it over the world model's public contract —
WebSocket observations/actions and the REST mission/reset endpoints.

The central abstraction is the :class:`~maritime_swarm.ai_control.tools.Tool`.
An LLM emits a structured tool call such as ``go_to(lat, lon)``; the matching
tool is validated, instantiated, and then *executed* tick-by-tick against the
world model until it completes.
"""

from maritime_swarm.ai_control.tools import (
    Tool,
    ToolContext,
    ToolInvocation,
    ToolRegistry,
    ToolStatus,
    ToolError,
    Bounds,
)
from maritime_swarm.ai_control.navigation_tools import default_registry

__all__ = [
    "Tool",
    "ToolContext",
    "ToolInvocation",
    "ToolRegistry",
    "ToolStatus",
    "ToolError",
    "Bounds",
    "default_registry",
]
