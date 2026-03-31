"""Observability KPI Reporting Application -- FastAPI entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as api_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("observability_kpi")

# ---------------------------------------------------------------------------
# Application metadata
# ---------------------------------------------------------------------------
APP_TITLE = "Observability KPI Reporting API"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = (
    "Enterprise API for computing and reporting observability KPIs "
    "across Mimir, Loki, Tempo, Pyroscope, and Grafana pillars."
)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown hooks)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting %s v%s", APP_TITLE, APP_VERSION)
    yield
    logger.info("Shutting down %s", APP_TITLE)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    lifespan=lifespan,
)

# -- CORS (permissive for development; tighten for production) ---------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Routers ----------------------------------------------------------------
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Root health check (convenience -- canonical one lives at /api/v1/health)
# ---------------------------------------------------------------------------
@app.get("/", tags=["root"], summary="Root health probe")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": APP_TITLE, "version": APP_VERSION}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
