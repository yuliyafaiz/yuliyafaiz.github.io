"""Module 5 — Creative Production Board: generation jobs, outputs, comparison, export."""
from __future__ import annotations

import copy
import io
import json
import random
import uuid
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..config import Settings
from ..deps import get_db, get_manager, get_or_404, get_settings_dep, get_store
from ..services import workflow as wf
from ..services.comfy import ComfyError, ComfyUnavailable
from ..services.generation import (
    ComfyManager,
    SubmissionError,
    activity,
    apply_variation,
    prepare_prompt,
    submit_job,
    upload_reference,
)
from ..services.images import MediaStore, compare_images
from .profiles import prompt_fragment

router = APIRouter(tags=["production"])


def _job_out(manager: ComfyManager, j: m.Job, include_prompt: bool = False) -> dict[str, Any]:
    return s.job(j, manager.live.get(j.comfy_prompt_id or ""), include_prompt)


@router.post("/generate", status_code=201)
async def generate(body: s.GenerateIn, db: Session = Depends(get_db), manager: ComfyManager = Depends(get_manager),
                   store: MediaStore = Depends(get_store), settings: Settings = Depends(get_settings_dep)
                   ) -> dict[str, Any]:
    config = get_or_404(db, m.ConsistencyConfig, body.consistency_config_id) if body.consistency_config_id else None
    workflow_id = body.workflow_id or (config.workflow_id if config else None)
    if workflow_id is None:
        raise HTTPException(422, "workflow_id or consistency_config_id is required")
    workflow = get_or_404(db, m.Workflow, workflow_id)
    project_id = body.project_id or (config.project_id if config else None) or workflow.project_id
    project = get_or_404(db, m.Project, project_id) if project_id else None
    if body.campaign_id:
        camp = get_or_404(db, m.Campaign, body.campaign_id)
        if project and camp.project_id != project.id:
            raise HTTPException(422, "campaign does not belong to the project")
    profile = config.profile if config else None

    values = {**(config.values if config else {}), **body.values}
    bindings = {**(config.image_bindings if config else {}), **body.image_bindings}
    if profile and config and config.use_profile_prompt:
        frag = prompt_fragment(s.profile(profile))
        for p in workflow.parameters:
            if p.get("role") in ("positive", "negative") and p["input"] == "text":
                extra = frag["positive"] if p["role"] == "positive" else frag["negative"]
                base = str(values.get(p["key"], p.get("default") or ""))
                if extra and extra not in base:
                    values[p["key"]] = f"{base}, {extra}" if base else extra

    try:
        await manager.client.system_stats()
    except ComfyUnavailable as exc:
        raise HTTPException(503, f"{exc}. Start ComfyUI or update the server URL in Settings.") from exc
    except ComfyError as exc:
        raise HTTPException(502, str(exc)) from exc

    variants = body.variant_values or [{}] * body.variations
    campaign_name = db.get(m.Campaign, body.campaign_id).name if body.campaign_id else None
    batch_id = str(uuid.uuid4())
    rng = random.Random()
    uploads: dict[int, str] = {}
    jobs = []
    for i, variant in enumerate(variants):
        vals = {**values, **variant}
        job = m.Job(project_id=project.id if project else None, campaign_id=body.campaign_id,
                    workflow_id=workflow.id, consistency_config_id=config.id if config else None,
                    batch_id=batch_id, variation_index=i, name=body.name or f"{workflow.name} · v{i + 1}",
                    image_bindings=bindings)
        db.add(job)
        db.flush()
        try:
            prompt = await prepare_prompt(db, manager, store, settings, workflow, vals, bindings, profile, project,
                                          job_id=job.id, campaign=campaign_name, upload_cache=uploads)
        except (SubmissionError, ComfyError) as exc:
            db.rollback()
            code = 422 if isinstance(exc, SubmissionError) else 502
            raise HTTPException(code, f"could not prepare variation {i + 1}: {exc}") from exc
        explicit_seed = any(k in variant for k in wf.seed_keys(prompt))
        seeds = {} if explicit_seed else apply_variation(prompt, i, body.seed_mode, body.base_seed, rng)
        job.parameter_values = {**vals, **seeds}
        await submit_job(db, manager, job, prompt)
        jobs.append(job)
    activity(db, "batch_submitted", f"Batch of {len(jobs)} job(s) submitted with “{workflow.name}”",
             project.id if project else None, "batch", None, batch_id=batch_id)
    db.commit()
    return {"batch_id": batch_id, "jobs": [_job_out(manager, j) for j in jobs]}


@router.get("/jobs")
def list_jobs(project_id: int | None = None, status: str | None = None, batch_id: str | None = None,
              limit: int = 200, db: Session = Depends(get_db), manager: ComfyManager = Depends(get_manager)
              ) -> list[dict[str, Any]]:
    q = select(m.Job).order_by(m.Job.id.desc()).limit(limit)
    if project_id is not None:
        q = q.where(m.Job.project_id == project_id)
    if status:
        q = q.where(m.Job.status.in_(status.split(",")))
    if batch_id:
        q = q.where(m.Job.batch_id == batch_id)
    return [_job_out(manager, j) for j in db.scalars(q).all()]


@router.get("/jobs/{jid}")
def get_job(jid: int, db: Session = Depends(get_db), manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    return _job_out(manager, get_or_404(db, m.Job, jid), include_prompt=True)


@router.post("/jobs/{jid}/cancel")
async def cancel_job(jid: int, db: Session = Depends(get_db), manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    j = get_or_404(db, m.Job, jid)
    if j.status not in ("submitted", "running"):
        raise HTTPException(409, f"job is {j.status}")
    try:
        where, _ = await manager.client.queue_position(j.comfy_prompt_id or "")
        if where == "pending":
            await manager.client.delete_from_queue(j.comfy_prompt_id or "")
            j.status = "cancelled"
            j.error = {"type": "cancelled", "message": "Removed from the ComfyUI queue"}
            from ..services.generation import now
            j.finished_at = now()
        elif where == "running":
            # The tracker will record "interrupted" once ComfyUI writes the history entry.
            await manager.client.interrupt(j.comfy_prompt_id)
    except ComfyUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    db.commit()
    return _job_out(manager, j)


@router.post("/jobs/{jid}/reproduce", status_code=201)
async def reproduce(jid: int, db: Session = Depends(get_db), manager: ComfyManager = Depends(get_manager),
                    store: MediaStore = Depends(get_store), settings: Settings = Depends(get_settings_dep)
                    ) -> dict[str, Any]:
    """Re-submit the exact API prompt of a previous job (same seeds, same inputs)."""
    src = get_or_404(db, m.Job, jid)
    if not src.submitted_prompt:
        raise HTTPException(409, "job has no submitted prompt to reproduce")
    try:
        for rid in set((src.image_bindings or {}).values()):  # make sure inputs exist on this server
            ref = db.get(m.Reference, rid)
            if ref:
                await upload_reference(manager, store, ref, settings.comfy_upload_subfolder)
    except ComfyUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    j = m.Job(project_id=src.project_id, campaign_id=src.campaign_id, workflow_id=src.workflow_id,
              consistency_config_id=src.consistency_config_id, batch_id=str(uuid.uuid4()),
              name=f"Reproduce of #{src.id}", parameter_values=src.parameter_values,
              image_bindings=src.image_bindings)
    db.add(j)
    db.flush()
    await submit_job(db, manager, j, copy.deepcopy(src.submitted_prompt))
    activity(db, "job_reproduced", f"Job #{src.id} re-submitted as #{j.id}", j.project_id, "job", j.id)
    db.commit()
    return _job_out(manager, j)


# --- outputs ----------------------------------------------------------------------------


@router.get("/outputs")
def list_outputs(project_id: int | None = None, job_id: int | None = None, batch_id: str | None = None,
                 favorite: bool | None = None, selected: bool | None = None, limit: int = 500,
                 db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(m.Output).order_by(m.Output.id.desc()).limit(limit)
    if project_id is not None:
        q = q.where(m.Output.project_id == project_id)
    if job_id is not None:
        q = q.where(m.Output.job_id == job_id)
    if batch_id:
        q = q.join(m.Job).where(m.Job.batch_id == batch_id)
    if favorite is not None:
        q = q.where(m.Output.favorite.is_(favorite))
    if selected is not None:
        q = q.where(m.Output.selected.is_(selected))
    return [s.output(o) for o in db.scalars(q).all()]


@router.get("/outputs/{oid}")
def get_output(oid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return s.output(get_or_404(db, m.Output, oid))


@router.patch("/outputs/{oid}")
def update_output(oid: int, body: s.OutputPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    o = get_or_404(db, m.Output, oid)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(o, k, v)
    if data.get("selected"):
        activity(db, "output_selected", f"Output #{o.id} selected as final", o.project_id, "output", o.id)
    db.commit()
    return s.output(o)


@router.get("/outputs/{oid}/file")
def output_file(oid: int, db: Session = Depends(get_db), store: MediaStore = Depends(get_store)) -> FileResponse:
    o = get_or_404(db, m.Output, oid)
    return FileResponse(store.path("outputs", o.stored_name), filename=o.comfy_filename or o.stored_name)


@router.get("/outputs/{oid}/thumb")
def output_thumb(oid: int, db: Session = Depends(get_db), store: MediaStore = Depends(get_store)) -> FileResponse:
    o = get_or_404(db, m.Output, oid)
    return FileResponse(store.thumb_path("outputs", o.stored_name), media_type="image/webp",
                        headers={"Cache-Control": "max-age=86400"})


@router.get("/outputs/{oid}/metadata")
def output_metadata(oid: int, db: Session = Depends(get_db)) -> Response:
    o = get_or_404(db, m.Output, oid)
    record = {**o.meta, "api_prompt": o.job.submitted_prompt}
    return Response(json.dumps(record, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="output_{o.id}_metadata.json"'})


@router.post("/outputs/export")
def export_outputs(body: s.ExportIn, db: Session = Depends(get_db), store: MediaStore = Depends(get_store)) -> Response:
    buf = io.BytesIO()
    manifest = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for oid in body.output_ids:
            o = get_or_404(db, m.Output, oid)
            ext = o.stored_name.rsplit(".", 1)[-1]
            base = f"output_{o.id:05d}"
            z.write(store.path("outputs", o.stored_name), f"{base}.{ext}")
            z.writestr(f"{base}.metadata.json", json.dumps(o.meta, indent=2))
            z.writestr(f"{base}.workflow_api.json", json.dumps(o.job.submitted_prompt, indent=2))
            manifest.append({"output_id": o.id, "file": f"{base}.{ext}", "selected": o.selected,
                             "favorite": o.favorite, "rating": o.rating, "job_id": o.job_id})
        z.writestr("manifest.json", json.dumps({"schema": "creative-studio/export@1", "outputs": manifest}, indent=2))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="creative_studio_export.zip"'})


@router.post("/outputs/{oid}/compare")
def compare(oid: int, body: s.CompareIn, db: Session = Depends(get_db), store: MediaStore = Depends(get_store)
            ) -> dict[str, Any]:
    """Heuristic similarity between an output and references/other outputs.

    Signals: SSIM (structure), colour-histogram correlation, perceptual hash. Useful
    for spotting drift; not a guarantee that a product or identity was preserved.
    """
    o = get_or_404(db, m.Output, oid)
    src = store.path("outputs", o.stored_name)
    results = []
    for rid in body.reference_ids:
        r = get_or_404(db, m.Reference, rid)
        results.append({"kind": "reference", "id": rid, "title": r.title,
                        **compare_images(src, store.path("references", r.stored_name))})
    for other in body.output_ids:
        o2 = get_or_404(db, m.Output, other)
        results.append({"kind": "output", "id": other, **compare_images(src, store.path("outputs", o2.stored_name))})
    return {"output_id": oid, "results": results,
            "note": "Heuristic signals only; review visually. Generated scenes can legitimately differ from a "
                    "reference in composition while preserving the product."}
