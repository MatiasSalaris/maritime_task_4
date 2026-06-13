from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from engine import app_state
from engine.world_state import WorldStateEngine
from api.ws_frontend import router as ws_frontend_router
from api.ws_agents import router as ws_agents_router
from api.rest import router as rest_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)


def _build_provider():
    if settings.provider == "hardware":
        from providers.hardware.hw_provider import HardwarePlatformProvider
        return HardwarePlatformProvider()
    from providers.simulation.sim_provider import SimulatedPlatformProvider
    return SimulatedPlatformProvider()


@asynccontextmanager
async def lifespan(app: FastAPI):
    provider = _build_provider()
    engine = WorldStateEngine(provider)
    app_state.engine = engine
    task = asyncio.create_task(engine.run())
    logger.info("Simulation engine started (provider=%s)", settings.provider)
    yield
    engine.stop()
    task.cancel()


app = FastAPI(title="Swarm-of-Three Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_frontend_router, prefix="/ws")
app.include_router(ws_agents_router, prefix="/ws")
app.include_router(rest_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "provider": settings.provider}
