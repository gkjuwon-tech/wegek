"""WEGEK backend — FastAPI application entrypoint.

Serves the orchestration API, the live job WebSocket, generated sites as static
files, and (in production) the built studio frontend.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import jobs, ws
from .store import get_store

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    get_store()  # init DB
    yield


app = FastAPI(
    title="WEGEK — AI 3D Website Factory",
    description="Natural language → production-quality 3D scrollytelling website.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(ws.router)

# Generated sites served statically (each job under /sites/{id}/index.html)
app.mount("/sites", StaticFiles(directory=str(settings.sites_dir), html=True), name="sites")


@app.get("/api")
async def api_root() -> JSONResponse:
    return JSONResponse({"name": "WEGEK", "docs": "/docs", "health": "/api/health"})


# Serve built frontend if present (production single-container deployment)
_frontend_dist = settings.data_dir.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="studio")
else:

    @app.get("/")
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "name": "WEGEK — AI 3D Website Factory",
                "studio": "run the frontend dev server (npm run dev in /frontend)",
                "api_health": "/api/health",
                "docs": "/docs",
            }
        )
