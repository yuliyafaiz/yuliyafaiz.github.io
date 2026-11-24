"""Demo data endpoint."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas as s
from ..deps import get_db, get_manager, get_store
from ..services.comfy import ComfyError
from ..services.demo import seed_jewelry_demo
from ..services.generation import ComfyManager
from ..services.images import MediaStore

router = APIRouter(tags=["demo"])


@router.post("/demo/jewelry", status_code=201)
async def seed(db: Session = Depends(get_db), store: MediaStore = Depends(get_store),
               manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    try:
        oi = await manager.client.object_info()
    except ComfyError:
        oi = None
    p = seed_jewelry_demo(db, store, oi)
    return s.project(p)
