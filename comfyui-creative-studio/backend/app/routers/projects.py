"""Module 1 — Project Manager."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..deps import get_db, get_or_404
from ..services.generation import activity

router = APIRouter(tags=["projects"])

PROJECT_TEMPLATES: dict[str, dict[str, Any]] = {
    "jewelry_campaign": {
        "label": "Jewelry campaign",
        "description": "Product-faithful jewelry imagery: packshots, editorial and macro details.",
        "campaigns": ["Packshots", "Editorial", "Close-up details"],
        "collections": ["Product originals", "Style references", "Lighting references"],
        "meta": {"deliverables": ["1:1 packshot", "4:5 social", "16:9 banner"], "industry": "jewelry"},
    },
    "fashion_editorial": {
        "label": "Fashion editorial",
        "description": "Character-consistent fashion stories across looks and locations.",
        "campaigns": ["Lookbook", "Editorial story"],
        "collections": ["Model references", "Wardrobe", "Locations", "Poses"],
        "meta": {"industry": "fashion"},
    },
    "ecommerce_catalog": {
        "label": "E-commerce catalog",
        "description": "Consistent product imagery for marketplaces.",
        "campaigns": ["Main images", "Lifestyle"],
        "collections": ["Products", "Backgrounds"],
        "meta": {"industry": "ecommerce"},
    },
    "blank": {"label": "Blank project", "description": "", "campaigns": [], "collections": [], "meta": {}},
}


def _counts(db: Session, pid: int) -> dict[str, int]:
    p = db.get(m.Project, pid)
    return {
        "references": len(p.references) if p else 0,
        "profiles": len(p.profiles) if p else 0,
        "workflows": db.scalar(select(func.count()).select_from(m.Workflow).where(m.Workflow.project_id == pid)) or 0,
        "jobs": db.scalar(select(func.count()).select_from(m.Job).where(m.Job.project_id == pid)) or 0,
        "outputs": db.scalar(select(func.count()).select_from(m.Output).where(m.Output.project_id == pid)) or 0,
        "selected": db.scalar(select(func.count()).select_from(m.Output)
                              .where(m.Output.project_id == pid, m.Output.selected.is_(True))) or 0,
    }


@router.get("/project-templates")
def templates() -> list[dict[str, Any]]:
    return [{"key": k, **v} for k, v in PROJECT_TEMPLATES.items()]


@router.get("/projects")
def list_projects(status: str | None = "active", db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(m.Project).order_by(m.Project.updated_at.desc())
    if status and status != "all":
        q = q.where(m.Project.status == status)
    return [s.project(p, _counts(db, p.id)) for p in db.scalars(q).all()]


@router.post("/projects", status_code=201)
def create_project(body: s.ProjectIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    tpl = PROJECT_TEMPLATES.get(body.template_key or "blank")
    if tpl is None:
        raise HTTPException(422, f"unknown template {body.template_key}")
    p = m.Project(name=body.name, description=body.description or tpl["description"], client=body.client,
                  template_key=body.template_key, meta={**tpl["meta"], **body.meta})
    db.add(p)
    db.flush()
    for c in tpl["campaigns"]:
        db.add(m.Campaign(project_id=p.id, name=c))
    for c in tpl["collections"]:
        db.add(m.Collection(project_id=p.id, name=c))
    activity(db, "project_created", f"Project “{p.name}” created", p.id, "project", p.id,
             template=body.template_key)
    db.commit()
    db.refresh(p)
    return s.project(p, _counts(db, p.id))


@router.get("/projects/{pid}")
def get_project(pid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, m.Project, pid)
    d = s.project(p, _counts(db, pid))
    d["references"] = [s.reference(r) for r in p.references]
    d["profiles"] = [s.profile(pr) for pr in p.profiles]
    d["collections"] = [{"id": c.id, "name": c.name, "count": len(c.items)} for c in
                        db.scalars(select(m.Collection).where(m.Collection.project_id == pid)).all()]
    d["workflows"] = [s.workflow(w) for w in
                      db.scalars(select(m.Workflow).where(m.Workflow.project_id == pid)).all()]
    return d


@router.patch("/projects/{pid}")
def update_project(pid: int, body: s.ProjectPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, m.Project, pid)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p, k, v)
    activity(db, "project_updated", f"Project updated: {', '.join(changes) or 'no changes'}", pid, "project", pid)
    db.commit()
    return s.project(p, _counts(db, pid))


@router.post("/projects/{pid}/archive")
def archive(pid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, m.Project, pid)
    p.status = "archived"
    activity(db, "project_archived", "Project archived", pid, "project", pid)
    db.commit()
    return s.project(p, _counts(db, pid))


@router.post("/projects/{pid}/restore")
def restore(pid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, m.Project, pid)
    p.status = "active"
    activity(db, "project_restored", "Project restored", pid, "project", pid)
    db.commit()
    return s.project(p, _counts(db, pid))


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: int, db: Session = Depends(get_db)) -> None:
    p = get_or_404(db, m.Project, pid)
    if p.status != "archived":
        raise HTTPException(409, "archive the project before deleting it")
    db.delete(p)
    db.commit()


# campaigns


@router.post("/projects/{pid}/campaigns", status_code=201)
def add_campaign(pid: int, body: s.CampaignIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, m.Project, pid)
    c = m.Campaign(project_id=pid, name=body.name, description=body.description)
    db.add(c)
    db.flush()
    activity(db, "campaign_created", f"Campaign “{c.name}” created", pid, "campaign", c.id)
    db.commit()
    return s.campaign(c)


@router.patch("/campaigns/{cid}")
def update_campaign(cid: int, body: s.CampaignPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_or_404(db, m.Campaign, cid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    return s.campaign(c)


@router.delete("/campaigns/{cid}", status_code=204)
def delete_campaign(cid: int, db: Session = Depends(get_db)) -> None:
    c = get_or_404(db, m.Campaign, cid)
    db.delete(c)
    db.commit()


# associations


@router.post("/projects/{pid}/references")
def attach_references(pid: int, body: s.IdList, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, m.Project, pid)
    added = 0
    for rid in body.ids:
        r = get_or_404(db, m.Reference, rid)
        if r not in p.references:
            p.references.append(r)
            added += 1
    activity(db, "references_attached", f"{added} reference(s) added to project", pid)
    db.commit()
    return {"attached": added}


@router.delete("/projects/{pid}/references/{rid}", status_code=204)
def detach_reference(pid: int, rid: int, db: Session = Depends(get_db)) -> None:
    p = get_or_404(db, m.Project, pid)
    r = get_or_404(db, m.Reference, rid)
    if r in p.references:
        p.references.remove(r)
    db.commit()


@router.post("/projects/{pid}/profiles")
def attach_profiles(pid: int, body: s.IdList, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, m.Project, pid)
    for prid in body.ids:
        pr = get_or_404(db, m.Profile, prid)
        if pr not in p.profiles:
            p.profiles.append(pr)
    db.commit()
    return {"profile_ids": [x.id for x in p.profiles]}


@router.get("/projects/{pid}/activity")
def project_activity(pid: int, limit: int = 100, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(m.Activity).where(m.Activity.project_id == pid).order_by(m.Activity.id.desc()).limit(limit)
    return [s.activity(a) for a in db.scalars(q).all()]
