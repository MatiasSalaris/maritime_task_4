from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.world_state import WorldStateEngine

# Global engine reference — set during app lifespan startup
engine: "WorldStateEngine | None" = None
