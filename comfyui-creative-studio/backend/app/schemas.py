"""Request schemas (Pydantic) and response serializers."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from . import models as m

REFERENCE_CATEGORIES = [
    "character", "face", "product", "jewelry", "clothing", "style", "lighting",
    "composition", "background", "location", "pose", "camera_angle",
]
WORKFLOW_CATEGORIES = [
    "product_photography", "jewelry_campaign", "fashion_editorial", "character_generation",
    "background_generation", "image_enhancement", "inpainting", "image_to_video",
    "batch_generation", "utility",
]
PROFILE_IMAGE_ROLES = ["primary", "face", "detail", "angle", "material", "style", "other"]


# --- requests -----------------------------------------------------------------------


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    client: str = ""
    template_key: str | None = None
    meta: dict[str, Any] = {}


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    client: str | None = None
    meta: dict[str, Any] | None = None
    cover_reference_id: int | None = None


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class CampaignPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    status: Literal["active", "archived"] | None = None


class IdList(BaseModel):
    ids: list[int]


class ReferencePatch(BaseModel):
    title: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    description: str | None = None
    favorite: bool | None = None


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    project_id: int | None = None
    reference_ids: list[int] = []


class CollectionPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    reference_ids: list[int] | None = None  # full ordered replacement


class ProfileIn(BaseModel):
    kind: Literal["character", "product"]
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = ""
    attributes: dict[str, Any] = {}
    preserve_details: list[str] = []
    generation_settings: dict[str, Any] = {}
    notes: str = ""
    project_ids: list[int] = []


class ProfilePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    attributes: dict[str, Any] | None = None
    preserve_details: list[str] | None = None
    generation_settings: dict[str, Any] | None = None
    notes: str | None = None
    project_ids: list[int] | None = None
    workflow_ids: list[int] | None = None


class ProfileImageIn(BaseModel):
    reference_id: int
    role: str = "primary"


class WorkflowImport(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    data: dict[str, Any]
    description: str = ""
    category: str = "product_photography"
    project_id: int | None = None
    is_template: bool = False


class WorkflowPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    project_id: int | None = None
    is_template: bool | None = None
    parameters: list[dict[str, Any]] | None = None


class ApiJsonIn(BaseModel):
    data: dict[str, Any]


class ConsistencyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    workflow_id: int
    profile_id: int | None = None
    project_id: int | None = None
    image_bindings: dict[str, int] = {}
    values: dict[str, Any] = {}
    use_profile_prompt: bool = True


class ConsistencyPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    profile_id: int | None = None
    project_id: int | None = None
    image_bindings: dict[str, int] | None = None
    values: dict[str, Any] | None = None
    use_profile_prompt: bool | None = None


class GenerateIn(BaseModel):
    workflow_id: int | None = None
    consistency_config_id: int | None = None
    project_id: int | None = None
    campaign_id: int | None = None
    name: str = ""
    values: dict[str, Any] = {}
    image_bindings: dict[str, int] = {}
    variations: int = Field(default=1, ge=1, le=32)
    seed_mode: Literal["fixed", "increment", "random"] = "increment"
    base_seed: int | None = None
    # Optional explicit per-variation parameter overrides (length defines variation count).
    variant_values: list[dict[str, Any]] = []


class OutputPatch(BaseModel):
    favorite: bool | None = None
    selected: bool | None = None
    rating: int | None = Field(default=None, ge=0, le=5)
    note: str | None = None


class ExportIn(BaseModel):
    output_ids: list[int] = Field(min_length=1)


class CompareIn(BaseModel):
    reference_ids: list[int] = []
    output_ids: list[int] = []


class ComfySettingsIn(BaseModel):
    comfy_url: str = Field(pattern=r"^https?://")


# --- serializers ------------------------------------------------------------------------


def dt(v: Any) -> str | None:
    return v.isoformat() if v else None


def reference(r: m.Reference) -> dict[str, Any]:
    return {
        "id": r.id, "title": r.title or r.original_name, "original_name": r.original_name,
        "mime": r.mime, "width": r.width, "height": r.height, "has_alpha": r.has_alpha,
        "sha256": r.sha256, "palette": r.palette, "category": r.category, "tags": r.tags,
        "description": r.description, "favorite": r.favorite, "created_at": dt(r.created_at),
        "file_url": f"/api/references/{r.id}/file", "thumb_url": f"/api/references/{r.id}/thumb",
        "project_ids": [p.id for p in r.projects],
    }


def campaign(c: m.Campaign) -> dict[str, Any]:
    return {"id": c.id, "project_id": c.project_id, "name": c.name, "description": c.description,
            "status": c.status, "created_at": dt(c.created_at)}


def project(p: m.Project, counts: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "id": p.id, "name": p.name, "description": p.description, "client": p.client,
        "status": p.status, "template_key": p.template_key, "meta": p.meta,
        "cover_reference_id": p.cover_reference_id,
        "cover_url": f"/api/references/{p.cover_reference_id}/thumb" if p.cover_reference_id else None,
        "campaigns": [campaign(c) for c in p.campaigns],
        "created_at": dt(p.created_at), "updated_at": dt(p.updated_at),
        "counts": counts or {},
    }


def profile(p: m.Profile) -> dict[str, Any]:
    return {
        "id": p.id, "kind": p.kind, "name": p.name, "description": p.description,
        "category": p.category, "attributes": p.attributes, "preserve_details": p.preserve_details,
        "generation_settings": p.generation_settings, "notes": p.notes,
        "images": [{"id": i.id, "role": i.role, "position": i.position, "reference": reference(i.reference)}
                   for i in p.images],
        "workflow_ids": [w.id for w in p.workflows],
        "project_ids": [pr.id for pr in p.projects],
        "created_at": dt(p.created_at), "updated_at": dt(p.updated_at),
    }


def workflow(w: m.Workflow, full: bool = False) -> dict[str, Any]:
    d = {
        "id": w.id, "name": w.name, "description": w.description, "category": w.category,
        "project_id": w.project_id, "is_template": w.is_template, "source_format": w.source_format,
        "executable": w.api_json is not None, "api_source": w.api_source,
        "conversion_warnings": w.conversion_warnings, "parameters": w.parameters,
        "node_types": w.node_types, "models": w.models, "node_count": len(w.api_json or {}) or
        len((w.original_json or {}).get("nodes", [])),
        "created_at": dt(w.created_at), "updated_at": dt(w.updated_at),
    }
    if full:
        d["original_json"], d["api_json"] = w.original_json, w.api_json
    return d


def consistency(c: m.ConsistencyConfig) -> dict[str, Any]:
    return {
        "id": c.id, "name": c.name, "description": c.description, "workflow_id": c.workflow_id,
        "workflow_name": c.workflow.name if c.workflow else None,
        "profile_id": c.profile_id, "profile_name": c.profile.name if c.profile else None,
        "project_id": c.project_id, "methods": c.methods, "image_bindings": c.image_bindings,
        "values": c.values, "use_profile_prompt": c.use_profile_prompt,
        "created_at": dt(c.created_at), "updated_at": dt(c.updated_at),
    }


def output(o: m.Output, with_meta: bool = True) -> dict[str, Any]:
    d = {
        "id": o.id, "job_id": o.job_id, "project_id": o.project_id, "width": o.width, "height": o.height,
        "node_id": o.node_id, "comfy_filename": o.comfy_filename, "favorite": o.favorite,
        "selected": o.selected, "rating": o.rating, "note": o.note, "created_at": dt(o.created_at),
        "file_url": f"/api/outputs/{o.id}/file", "thumb_url": f"/api/outputs/{o.id}/thumb",
    }
    if with_meta:
        d["meta"] = o.meta
    else:
        g = (o.meta or {}).get("generation", {})
        d["summary"] = {k: g.get(k) for k in ("seed", "steps", "cfg", "sampler", "scheduler")}
    return d


def job(j: m.Job, live: dict[str, Any] | None = None, include_prompt: bool = False) -> dict[str, Any]:
    progress = dict(j.progress or {})
    if live and j.status in ("submitted", "running"):
        for k in ("value", "max", "node"):
            if live.get(k) is not None:
                progress[k] = live[k]
    d = {
        "id": j.id, "project_id": j.project_id, "campaign_id": j.campaign_id, "workflow_id": j.workflow_id,
        "consistency_config_id": j.consistency_config_id, "batch_id": j.batch_id,
        "variation_index": j.variation_index, "name": j.name, "status": j.status,
        "comfy_prompt_id": j.comfy_prompt_id, "server_url": j.server_url,
        "parameter_values": j.parameter_values, "image_bindings": j.image_bindings,
        "progress": progress, "error": j.error, "execution_seconds": j.execution_seconds,
        "created_at": dt(j.created_at), "submitted_at": dt(j.submitted_at), "finished_at": dt(j.finished_at),
        "outputs": [output(o, with_meta=False) for o in j.outputs],
    }
    if include_prompt:
        d["submitted_prompt"] = j.submitted_prompt
        d["status_messages"] = j.status_messages
    return d


def activity(a: m.Activity) -> dict[str, Any]:
    return {"id": a.id, "project_id": a.project_id, "kind": a.kind, "message": a.message,
            "entity_type": a.entity_type, "entity_id": a.entity_id, "data": a.data,
            "created_at": dt(a.created_at)}
