"""Shared FastAPI dependencies and helpers."""
from __future__ import annotations

from typing import Any, TypeVar

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .config import Settings
from .db import get_db  # noqa: F401  (re-export)
from .services.generation import ComfyManager, Tracker
from .services.images import MediaStore

T = TypeVar("T")


def get_store(request: Request) -> MediaStore:
    return request.app.state.store


def get_manager(request: Request) -> ComfyManager:
    return request.app.state.manager


def get_tracker(request: Request) -> Tracker:
    return request.app.state.tracker


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_or_404(db: Session, model: type[T], id_: Any, name: str | None = None) -> T:
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{name or model.__name__} {id_} not found")
    return obj
