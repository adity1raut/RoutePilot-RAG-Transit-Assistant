"""RoutePilot FastAPI application.

Run from the backend/ folder:  uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.rag.llm import model_name
from app.rag.pipeline import RAGPipeline
from app.rag.vectorstore import VectorStore, build_index
from app.schemas import ChatRequest, ChatResponse, DayType, HealthResponse, IngestResponse
from app.services.transport import TransportData, day_type_for

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("routepilot")

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    transport = TransportData(settings.data_dir)
    store = VectorStore(settings)
    if store.count() == 0:
        log.info("Vector store is empty - running ingestion pipeline")
        log.info("Indexed %s", build_index(settings, store))
    app.state.settings = settings
    app.state.transport = transport
    app.state.store = store
    app.state.pipeline = RAGPipeline(settings, transport, store)
    log.info("RoutePilot ready - LLM provider: %s, %d chunks indexed", app.state.pipeline.provider, store.count())
    yield


app = FastAPI(title="RoutePilot API", version="1.0.0", lifespan=lifespan,
              description="Public Transport Information Assistant using Retrieval-Augmented Generation")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])


def _transport() -> TransportData:
    return app.state.transport


def _stop(name: str) -> str:
    stop = _transport().resolve_stop(name)
    if not stop:
        raise HTTPException(404, f"Unknown stop '{name}'")
    return stop


@app.get("/api/health", response_model=HealthResponse)
def health():
    settings = app.state.settings
    return HealthResponse(
        status="ok",
        provider=app.state.pipeline.provider,
        model=model_name(settings) if app.state.pipeline.llm else None,
        embedding_model=settings.embedding_model,
        chunks_indexed=app.state.store.count(),
        routes=len(_transport().route_numbers),
        stops=len(_transport().stops),
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Transport Q&A: RAG answer with cited sources."""
    history = [turn.model_dump() for turn in request.history]
    return await run_in_threadpool(app.state.pipeline.answer, request.question, history, request.top_k)


@app.get("/api/stops")
def stops() -> list[str]:
    return _transport().stops


@app.get("/api/routes")
def routes() -> list[dict]:
    return _transport().route_summaries()


@app.get("/api/map")
def network_map() -> dict:
    """Stop coordinates and route stop sequences for drawing the network map."""
    return _transport().map_data()


@app.get("/api/routes/{route_no}/timetable")
def timetable(route_no: str, day_type: DayType | None = None, direction: Literal["Up", "Down"] | None = None):
    """Timetable search for one route."""
    table = _transport().timetable(route_no, day_type, direction)
    if not table:
        raise HTTPException(404, f"No timetable found for route '{route_no}'")
    return table


@app.get("/api/journeys")
def journeys(source: str, destination: str, day_type: DayType | None = None):
    """Route information: direct or one-transfer journeys between two stops."""
    src, dst = _stop(source), _stop(destination)
    if src == dst:
        raise HTTPException(422, "Source and destination are the same stop")
    now = datetime.now()
    day = day_type or day_type_for(now)
    found = _transport().find_journeys(src, dst, day, now)
    return {"source": src, "destination": dst, "day_type": day, "journeys": [j.to_dict() for j in found]}


@app.get("/api/fares")
def fares(source: str, destination: str):
    """Fare information between two stops (fares are the same on every day type)."""
    src, dst = _stop(source), _stop(destination)
    if src == dst:
        raise HTTPException(422, "Source and destination are the same stop")
    options = [
        {
            "routes": [leg.route_no for leg in j.legs],
            "bus_types": [leg.bus_type for leg in j.legs],
            "via": [leg.alight for leg in j.legs[:-1]],
            "stops_travelled": sum(leg.stops_travelled for leg in j.legs),
            "fare": j.fare,
        }
        for j in _transport().find_journeys(src, dst, "Weekday")
    ]
    return {"source": src, "destination": dst, "options": options}


@app.get("/api/fare-chart")
def fare_chart() -> list[dict]:
    return _transport().fare_chart.to_dict(orient="records")


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest():
    """Re-run the preprocessing pipeline after changing files in data/raw."""
    settings = app.state.settings
    stats = await run_in_threadpool(build_index, settings, app.state.store)
    app.state.transport = TransportData(settings.data_dir)
    app.state.pipeline.transport = app.state.transport
    return stats


# Serve the built React frontend (npm run build) from the same server, if present.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
