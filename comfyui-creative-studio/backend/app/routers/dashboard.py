"""Dashboard aggregate endpoint."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..deps import get_db, get_manager
from ..services.generation import ComfyManager

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    projects = db.scalars(select(m.Project).where(m.Project.status == "active")
                          .order_by(m.Project.updated_at.desc()).limit(6)).all()
    active = db.scalars(select(m.Job).where(m.Job.status.in_(("submitted", "running")))
                        .order_by(m.Job.id.desc())).all()
    recent_outputs = db.scalars(select(m.Output).order_by(m.Output.id.desc()).limit(12)).all()
    fav_refs = db.scalars(select(m.Reference).where(m.Reference.favorite.is_(True))
                          .order_by(m.Reference.id.desc()).limit(8)).all()
    shortcuts = db.scalars(select(m.Workflow).where(m.Workflow.api_json.is_not(None))
                           .order_by(m.Workflow.updated_at.desc()).limit(6)).all()
    activity = db.scalars(select(m.Activity).order_by(m.Activity.id.desc()).limit(12)).all()
    count = lambda model: db.scalar(select(func.count()).select_from(model)) or 0  # noqa: E731
    return {
        "stats": {"projects": count(m.Project), "references": count(m.Reference), "profiles": count(m.Profile),
                  "workflows": count(m.Workflow), "jobs": count(m.Job), "outputs": count(m.Output)},
        "recent_projects": [s.project(p) for p in projects],
        "active_jobs": [s.job(j, manager.live.get(j.comfy_prompt_id or "")) for j in active],
        "recent_outputs": [s.output(o, with_meta=False) for o in recent_outputs],
        "favorite_references": [s.reference(r) for r in fav_refs],
        "workflow_shortcuts": [s.workflow(w) for w in shortcuts],
        "activity": [s.activity(a) for a in activity],
    }
