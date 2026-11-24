"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db as dbmod
from . import models as m
from .config import Settings, get_settings
from .routers import (
    comfy,
    consistency,
    custom_nodes,
    dashboard,
    demo,
    jobs,
    profiles,
    projects,
    references,
    workflows,
)
from .services.generation import ComfyManager, Tracker
from .services.images import MediaStore

__version__ = "0.1.0"


def create_app(settings: Settings | None = None, comfy_transport: Any = None) -> FastAPI:
    settings = settings or get_settings()
    settings.data_path.mkdir(parents=True, exist_ok=True)
    dbmod.init_engine(settings.db_url)
    sf = dbmod.session_factory()

    with sf() as db:
        saved = db.get(m.AppSetting, "comfy_url")
        comfy_url = saved.value if saved else settings.comfy_url

    store = MediaStore(settings.media_path)
    manager = ComfyManager(comfy_url, transport=comfy_transport)
    tracker = Tracker(sf, manager, store, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.enable_tracker:
            tracker.start()
        yield
        await tracker.stop()
        await manager.client.aclose()

    app = FastAPI(title="ComfyUI Creative Studio", version=__version__, lifespan=lifespan)
    app.state.settings, app.state.store = settings, store
    app.state.manager, app.state.tracker = manager, tracker
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"],
                       allow_headers=["*"])

    for r in (projects, references, profiles, workflows, consistency, jobs, comfy, custom_nodes,
              dashboard, demo):
        app.include_router(r.router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    dist = settings.resolve(settings.frontend_dist)
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            f = dist / path
            if path and f.is_file() and dist in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    logging.basicConfig(level=logging.INFO)
    return app
