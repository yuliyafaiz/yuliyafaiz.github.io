"""Module 2b — Character and Product Profiles."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..deps import get_db, get_or_404
from ..services.generation import activity

router = APIRouter(tags=["profiles"])

# Suggested attribute fields per profile kind (free-form keys are also allowed).
ATTRIBUTE_FIELDS = {
    "product": ["shape", "material", "finish", "color", "stones", "stone_setting", "dimensions", "brand_style"],
    "character": ["age_range", "hair", "eyes", "skin", "build", "distinctive_features", "wardrobe_style"],
}


def prompt_fragment(p: dict[str, Any]) -> dict[str, str]:
    """Deterministic text fragments derived from a profile.

    The same algorithm is implemented in the custom node package
    (``cs_nodes/profiles.py``) so prompts match whether built here or in ComfyUI.
    Text alone does not make an image consistent; it complements image conditioning.
    """
    parts: list[str] = []
    if p.get("description"):
        parts.append(p["description"].strip().rstrip("."))
    attrs = p.get("attributes") or {}
    for k in sorted(attrs):
        v = attrs[k]
        if v not in (None, "", []):
            v = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
            parts.append(f"{k.replace('_', ' ')}: {v}")
    preserve = [d.strip() for d in p.get("preserve_details") or [] if d.strip()]
    if preserve:
        parts.append("preserve exactly: " + "; ".join(preserve))
    negative = ""
    if p.get("kind") == "product":
        negative = "deformed product, altered design, extra stones, missing stones, warped metal, wrong proportions"
    elif p.get("kind") == "character":
        negative = "different person, inconsistent face, altered facial features"
    return {"positive": ", ".join(parts), "negative": negative}


@router.get("/profiles/attribute-fields")
def attribute_fields() -> dict[str, Any]:
    return {"fields": ATTRIBUTE_FIELDS, "image_roles": s.PROFILE_IMAGE_ROLES}


@router.get("/profiles")
def list_profiles(kind: str | None = None, project_id: int | None = None,
                  db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(m.Profile).order_by(m.Profile.updated_at.desc())
    if kind:
        q = q.where(m.Profile.kind == kind)
    if project_id is not None:
        q = q.where(m.Profile.projects.any(m.Project.id == project_id))
    return [s.profile(p) for p in db.scalars(q).all()]


@router.post("/profiles", status_code=201)
def create_profile(body: s.ProfileIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    data = body.model_dump()
    pids = data.pop("project_ids")
    p = m.Profile(**data)
    for pid in pids:
        p.projects.append(get_or_404(db, m.Project, pid))
    db.add(p)
    db.flush()
    for pid in pids:
        activity(db, "profile_created", f"{p.kind.title()} profile “{p.name}” created", pid, "profile", p.id)
    db.commit()
    return s.profile(p)


@router.get("/profiles/{pid}")
def get_profile(pid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, m.Profile, pid)
    d = s.profile(p)
    d["prompt_fragment"] = prompt_fragment(d)
    return d


@router.patch("/profiles/{pid}")
def update_profile(pid: int, body: s.ProfilePatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, m.Profile, pid)
    data = body.model_dump(exclude_unset=True)
    if (pids := data.pop("project_ids", None)) is not None:
        p.projects = [get_or_404(db, m.Project, i) for i in pids]
    if (wids := data.pop("workflow_ids", None)) is not None:
        p.workflows = [get_or_404(db, m.Workflow, i) for i in wids]
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    return get_profile(pid, db)


@router.delete("/profiles/{pid}", status_code=204)
def delete_profile(pid: int, db: Session = Depends(get_db)) -> None:
    db.delete(get_or_404(db, m.Profile, pid))
    db.commit()


@router.post("/profiles/{pid}/images", status_code=201)
def add_image(pid: int, body: s.ProfileImageIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, m.Profile, pid)
    get_or_404(db, m.Reference, body.reference_id)
    if body.role not in s.PROFILE_IMAGE_ROLES:
        raise HTTPException(422, f"role must be one of {s.PROFILE_IMAGE_ROLES}")
    if any(i.reference_id == body.reference_id and i.role == body.role for i in p.images):
        raise HTTPException(409, "image already in profile with this role")
    p.images.append(m.ProfileImage(reference_id=body.reference_id, role=body.role, position=len(p.images)))
    db.commit()
    return get_profile(pid, db)


@router.delete("/profiles/{pid}/images/{image_id}")
def remove_image(pid: int, image_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, m.Profile, pid)
    p.images[:] = [i for i in p.images if i.id != image_id]
    db.commit()
    return get_profile(pid, db)


@router.get("/profiles/{pid}/export")
def export_profile(pid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """JSON accepted by the CS_*ProfileLoader nodes' ``profile_json`` input.

    ``image_files`` is filled in at submission time once images are uploaded to ComfyUI.
    """
    p = get_or_404(db, m.Profile, pid)
    d = s.profile(p)
    return {"id": p.id, "kind": p.kind, "name": p.name, "description": p.description,
            "category": p.category, "attributes": p.attributes, "preserve_details": p.preserve_details,
            "notes": p.notes, "images": [{"reference_id": i["reference"]["id"], "role": i["role"],
                                          "sha256": i["reference"]["sha256"]} for i in d["images"]],
            "image_files": {}}
