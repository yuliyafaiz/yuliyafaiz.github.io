"""Module 3 — Workflow Manager."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..deps import get_db, get_manager, get_or_404
from ..services import workflow as wf
from ..services.comfy import ComfyError
from ..services.generation import ComfyManager, activity

router = APIRouter(tags=["workflows"])


async def _object_info(manager: ComfyManager) -> dict[str, Any] | None:
    try:
        return await manager.client.object_info()
    except ComfyError:
        return None


def _analyse(w: m.Workflow, object_info: dict[str, Any] | None) -> None:
    if w.api_json is not None:
        w.node_types = wf.api_node_types(w.api_json)
        w.models = wf.api_models(w.api_json)
        w.parameters = wf.discover_parameters(w.api_json, object_info)
    else:
        w.node_types = wf.ui_node_types(w.original_json)
        w.models = wf.ui_models(w.original_json)
        w.parameters = []


@router.get("/workflow-categories")
def categories() -> list[str]:
    return s.WORKFLOW_CATEGORIES


@router.get("/workflows")
def list_workflows(project_id: int | None = None, category: str | None = None, templates: bool | None = None,
                   db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(m.Workflow).order_by(m.Workflow.updated_at.desc())
    if project_id is not None:
        q = q.where(m.Workflow.project_id == project_id)
    if category:
        q = q.where(m.Workflow.category == category)
    if templates is not None:
        q = q.where(m.Workflow.is_template.is_(templates))
    return [s.workflow(w) for w in db.scalars(q).all()]


async def import_workflow_data(db: Session, manager: ComfyManager, body: s.WorkflowImport) -> m.Workflow:
    try:
        fmt = wf.detect_format(body.data)
    except wf.WorkflowFormatError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.category not in s.WORKFLOW_CATEGORIES:
        raise HTTPException(422, f"category must be one of {s.WORKFLOW_CATEGORIES}")
    data = wf.unwrap(body.data)
    w = m.Workflow(name=body.name, description=body.description, category=body.category,
                   project_id=body.project_id, is_template=body.is_template, source_format=fmt,
                   original_json=body.data, api_json=data if fmt == "api" else None,
                   api_source="imported" if fmt == "api" else None)
    oi = await _object_info(manager)
    if fmt == "ui" and oi is not None:
        try:
            api, warnings = wf.convert_ui_to_api(data, oi)
            w.api_json, w.api_source, w.conversion_warnings = api, "converted", warnings
        except wf.WorkflowFormatError as exc:
            w.conversion_warnings = [str(exc)]
    elif fmt == "ui":
        w.conversion_warnings = ["ComfyUI was not reachable, so the UI workflow could not be converted. "
                                 "Connect ComfyUI and use “Convert”, or attach an Export (API) file."]
    _analyse(w, oi)
    db.add(w)
    db.flush()
    activity(db, "workflow_imported", f"Workflow “{w.name}” imported ({fmt} format)", w.project_id, "workflow", w.id)
    db.commit()
    return w


@router.post("/workflows", status_code=201)
async def import_workflow(body: s.WorkflowImport, db: Session = Depends(get_db),
                          manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    return s.workflow(await import_workflow_data(db, manager, body), full=True)


@router.post("/workflows/upload", status_code=201)
async def upload_workflow(file: UploadFile = File(...), name: str = Form(""), category: str = Form("product_photography"),
                          description: str = Form(""), project_id: int | None = Form(None),
                          is_template: bool = Form(False), db: Session = Depends(get_db),
                          manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    try:
        data = json.loads(await file.read())
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, "file is not valid JSON") from exc
    body = s.WorkflowImport(name=name or (file.filename or "workflow").rsplit(".", 1)[0], data=data,
                            category=category, description=description, project_id=project_id,
                            is_template=is_template)
    return s.workflow(await import_workflow_data(db, manager, body), full=True)


@router.get("/workflows/{wid}")
def get_workflow(wid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    w = get_or_404(db, m.Workflow, wid)
    d = s.workflow(w, full=True)
    d["methods"] = wf.detect_methods(w.node_types)
    return d


@router.patch("/workflows/{wid}")
def update_workflow(wid: int, body: s.WorkflowPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    w = get_or_404(db, m.Workflow, wid)
    data = body.model_dump(exclude_unset=True)
    if "category" in data and data["category"] not in s.WORKFLOW_CATEGORIES:
        raise HTTPException(422, "invalid category")
    if "parameters" in data:
        api = w.api_json or {}
        for p in data["parameters"]:
            nid, inp = p.get("node_id"), p.get("input")
            if not nid or nid not in api or inp not in api[nid]["inputs"] or wf.is_link(api[nid]["inputs"][inp]):
                raise HTTPException(422, f"parameter {p.get('key')} does not reference a literal input")
            p["key"] = f"{nid}.{inp}"
            p.setdefault("label", p["key"])
            p.setdefault("type", "text")
            p.setdefault("group", "custom")
    for k, v in data.items():
        setattr(w, k, v)
    db.commit()
    return get_workflow(wid, db)


@router.delete("/workflows/{wid}", status_code=204)
def delete_workflow(wid: int, db: Session = Depends(get_db)) -> None:
    db.delete(get_or_404(db, m.Workflow, wid))
    db.commit()


@router.post("/workflows/{wid}/convert")
async def convert(wid: int, db: Session = Depends(get_db), manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    w = get_or_404(db, m.Workflow, wid)
    if w.source_format != "ui":
        raise HTTPException(409, "workflow is already in API format")
    oi = await _object_info(manager)
    if oi is None:
        raise HTTPException(503, "ComfyUI is not reachable; /object_info is required for conversion")
    try:
        api, warnings = wf.convert_ui_to_api(wf.unwrap(w.original_json), oi)
    except wf.WorkflowFormatError as exc:
        raise HTTPException(422, str(exc)) from exc
    w.api_json, w.api_source, w.conversion_warnings = api, "converted", warnings
    _analyse(w, oi)
    db.commit()
    return get_workflow(wid, db)


@router.post("/workflows/{wid}/api-json")
async def attach_api_json(wid: int, body: s.ApiJsonIn, db: Session = Depends(get_db),
                          manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    """Attach an "Export (API)" file to a workflow imported in UI format."""
    w = get_or_404(db, m.Workflow, wid)
    try:
        if wf.detect_format(body.data) != "api":
            raise HTTPException(422, "expected API-format JSON (Workflow → Export (API) in ComfyUI)")
    except wf.WorkflowFormatError as exc:
        raise HTTPException(422, str(exc)) from exc
    w.api_json, w.api_source, w.conversion_warnings = wf.unwrap(body.data), "imported", []
    _analyse(w, await _object_info(manager))
    db.commit()
    return get_workflow(wid, db)


@router.post("/workflows/{wid}/rediscover")
async def rediscover(wid: int, db: Session = Depends(get_db), manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    w = get_or_404(db, m.Workflow, wid)
    _analyse(w, await _object_info(manager))
    db.commit()
    return get_workflow(wid, db)


@router.get("/workflows/{wid}/dependencies")
async def dependencies(wid: int, db: Session = Depends(get_db), manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    w = get_or_404(db, m.Workflow, wid)
    oi = await _object_info(manager)
    report = wf.check_dependencies(w.api_json, w.node_types, oi)
    report["structure_issues"] = wf.validate_structure(w.api_json, oi) if (oi and w.api_json) else []
    report["node_types"] = w.node_types
    report["models"] = w.models
    report["methods"] = wf.detect_methods(w.node_types)
    report["ready"] = bool(report["checked"] and w.api_json is not None and not report["missing_nodes"]
                           and not report["missing_models"]
                           and not any(i["severity"] == "error" for i in report["structure_issues"]))
    return report


@router.get("/workflows/{wid}/inputs")
def literal_inputs(wid: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    w = get_or_404(db, m.Workflow, wid)
    return wf.literal_inputs(w.api_json or {})


@router.get("/workflows/{wid}/download")
def download(wid: int, which: str = "api", db: Session = Depends(get_db)) -> Response:
    w = get_or_404(db, m.Workflow, wid)
    data = w.api_json if which == "api" else w.original_json
    if data is None:
        raise HTTPException(404, "no API-format JSON for this workflow")
    fname = f"{w.name.replace(' ', '_')}_{which}.json"
    return Response(json.dumps(data, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/workflows/{wid}/duplicate", status_code=201)
def duplicate(wid: int, project_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    src = get_or_404(db, m.Workflow, wid)
    w = m.Workflow(name=f"{src.name} (copy)", description=src.description, category=src.category,
                   project_id=project_id if project_id is not None else src.project_id, is_template=False,
                   source_format=src.source_format, original_json=src.original_json, api_json=src.api_json,
                   api_source=src.api_source, conversion_warnings=src.conversion_warnings,
                   parameters=src.parameters, node_types=src.node_types, models=src.models)
    db.add(w)
    db.commit()
    return s.workflow(w)
