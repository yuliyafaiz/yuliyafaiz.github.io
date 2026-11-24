"""Module 4 — Consistency Manager.

An integration layer over existing conditioning nodes (IPAdapter, ControlNet,
inpainting, img2img, profile loaders). It does not reimplement any algorithm: it
stores *which* reference images feed *which* workflow inputs and *which*
weights/strengths were used, so a configuration can be re-run and reused.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..deps import get_db, get_or_404
from ..services import workflow as wf

router = APIRouter(tags=["consistency"])

METHOD_INFO = {
    "inpaint": "Masked regeneration. With ImageCompositeMasked the original product pixels are pasted back, "
               "which is the strongest guarantee of product fidelity available in a diffusion pipeline.",
    "img2img": "Starts from an encoded reference image; denoise controls how far the result may drift.",
    "ipadapter": "Image-prompt adapter (ComfyUI_IPAdapter_plus). Transfers style/subject features; does not "
                 "guarantee exact geometry or stone placement.",
    "faceid": "Face-identity adapters (IPAdapter FaceID / InstantID / PuLID). Require insightface; several "
              "of these models are licensed for non-commercial use only.",
    "controlnet": "Structural guidance (canny/depth/lineart/pose) from a reference image.",
    "openpose": "Pose guidance via an OpenPose map (needs comfyui_controlnet_aux preprocessors).",
    "style_model": "Style/Redux conditioning from a reference image.",
    "reference_profile": "Creative Studio profile loader nodes: load profile references and prompt fragments.",
}


def _validate(db: Session, workflow: m.Workflow, bindings: dict[str, int], values: dict[str, Any]) -> None:
    params = {p["key"]: p for p in workflow.parameters}
    for key, rid in bindings.items():
        if params.get(key, {}).get("type") != "image":
            raise HTTPException(422, f"{key} is not an image parameter of this workflow")
        get_or_404(db, m.Reference, rid)
    for key in values:
        if key not in params:
            nid, _, inp = key.partition(".")
            if not workflow.api_json or nid not in workflow.api_json or inp not in workflow.api_json[nid]["inputs"]:
                raise HTTPException(422, f"{key} is not an input of this workflow")


@router.get("/consistency/methods")
def methods() -> dict[str, str]:
    return METHOD_INFO


@router.get("/consistency/plan/{workflow_id}")
def plan(workflow_id: int, profile_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Describe what a workflow can be conditioned with and suggest reference bindings."""
    w = get_or_404(db, m.Workflow, workflow_id)
    image_params = [p for p in w.parameters if p["type"] == "image"]
    cond_params = [p for p in w.parameters if p.get("group") in ("conditioning", "models")
                   or p.get("input") == "denoise"]
    suggestions: dict[str, int] = {}
    if profile_id is not None:
        prof = get_or_404(db, m.Profile, profile_id)
        by_role: dict[str, list[int]] = {}
        for pi in prof.images:
            by_role.setdefault(pi.role, []).append(pi.reference_id)
        ordered = by_role.get("primary", []) + by_role.get("face", []) + by_role.get("detail", []) + \
            [r for role, ids in by_role.items() if role not in ("primary", "face", "detail") for r in ids]
        for p, rid in zip(image_params, ordered):
            suggestions[p["key"]] = rid
    found = wf.detect_methods(w.node_types)
    return {"workflow_id": w.id, "methods": [{"key": k, "info": METHOD_INFO.get(k, "")} for k in found],
            "image_parameters": image_params, "conditioning_parameters": cond_params,
            "suggested_bindings": suggestions,
            "profile_loader_nodes": [nid for nid, n in (w.api_json or {}).items()
                                     if n["class_type"] in ("CS_ProductProfileLoader", "CS_CharacterProfileLoader")]}


@router.get("/consistency")
def list_configs(project_id: int | None = None, profile_id: int | None = None,
                 db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(m.ConsistencyConfig).order_by(m.ConsistencyConfig.updated_at.desc())
    if project_id is not None:
        q = q.where(m.ConsistencyConfig.project_id == project_id)
    if profile_id is not None:
        q = q.where(m.ConsistencyConfig.profile_id == profile_id)
    return [s.consistency(c) for c in db.scalars(q).all()]


@router.post("/consistency", status_code=201)
def create_config(body: s.ConsistencyIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    w = get_or_404(db, m.Workflow, body.workflow_id)
    if body.profile_id:
        get_or_404(db, m.Profile, body.profile_id)
    _validate(db, w, body.image_bindings, body.values)
    c = m.ConsistencyConfig(**body.model_dump(), methods=wf.detect_methods(w.node_types))
    db.add(c)
    db.commit()
    db.refresh(c)
    return s.consistency(c)


@router.get("/consistency/{cid}")
def get_config(cid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return s.consistency(get_or_404(db, m.ConsistencyConfig, cid))


@router.patch("/consistency/{cid}")
def update_config(cid: int, body: s.ConsistencyPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_or_404(db, m.ConsistencyConfig, cid)
    data = body.model_dump(exclude_unset=True)
    _validate(db, c.workflow, data.get("image_bindings", c.image_bindings), data.get("values", c.values))
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    return s.consistency(c)


@router.delete("/consistency/{cid}", status_code=204)
def delete_config(cid: int, db: Session = Depends(get_db)) -> None:
    db.delete(get_or_404(db, m.ConsistencyConfig, cid))
    db.commit()
