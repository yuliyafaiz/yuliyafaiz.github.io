"""Module 2 — Reference Studio: references and collections."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..deps import get_db, get_or_404, get_store
from ..services.generation import activity
from ..services.images import ImageError, MediaStore

router = APIRouter(tags=["references"])


def _norm_tags(tags: list[str]) -> list[str]:
    seen, out = set(), []
    for t in tags:
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _check_category(cat: str) -> str:
    if cat not in s.REFERENCE_CATEGORIES:
        raise HTTPException(422, f"category must be one of {s.REFERENCE_CATEGORIES}")
    return cat


@router.get("/reference-categories")
def categories() -> list[str]:
    return s.REFERENCE_CATEGORIES


@router.get("/references")
def list_references(q: str = "", category: str = "", tag: str = "", project_id: int | None = None,
                    collection_id: int | None = None, favorite: bool | None = None,
                    db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    query = select(m.Reference).order_by(m.Reference.id.desc())
    if category:
        query = query.where(m.Reference.category == category)
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(m.Reference.title.ilike(like), m.Reference.original_name.ilike(like),
                                m.Reference.description.ilike(like)))
    if favorite is not None:
        query = query.where(m.Reference.favorite.is_(favorite))
    if project_id is not None:
        query = query.where(m.Reference.projects.any(m.Project.id == project_id))
    if collection_id is not None:
        query = query.join(m.CollectionItem, m.CollectionItem.reference_id == m.Reference.id) \
            .where(m.CollectionItem.collection_id == collection_id) \
            .order_by(None).order_by(m.CollectionItem.position)
    refs = db.scalars(query).all()
    if tag:
        t = tag.lower()
        refs = [r for r in refs if t in r.tags]
    return [s.reference(r) for r in refs]


@router.get("/references/tags")
def list_tags(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for tags in db.scalars(select(m.Reference.tags)).all():
        for t in tags or []:
            counts[t] = counts.get(t, 0) + 1
    return [{"tag": t, "count": c} for t, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


@router.post("/references", status_code=201)
async def upload_references(
    files: list[UploadFile] = File(...),
    category: str = Form("style"),
    tags: str = Form(""),
    description: str = Form(""),
    project_id: int | None = Form(None),
    collection_id: int | None = Form(None),
    db: Session = Depends(get_db),
    store: MediaStore = Depends(get_store),
) -> list[dict[str, Any]]:
    _check_category(category)
    project = get_or_404(db, m.Project, project_id) if project_id else None
    coll = get_or_404(db, m.Collection, collection_id) if collection_id else None
    tag_list = _norm_tags(tags.split(","))
    created = []
    for f in files:
        data = await f.read()
        try:
            st = store.save("references", data)
        except ImageError as exc:
            raise HTTPException(422, f"{f.filename}: {exc}") from exc
        title = (f.filename or "reference").rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
        r = m.Reference(title=title[:200], original_name=f.filename or "upload", stored_name=st.stored_name,
                        mime=st.mime, width=st.width, height=st.height, has_alpha=st.has_alpha,
                        sha256=st.sha256, phash=st.phash, palette=st.palette, category=category,
                        tags=tag_list, description=description)
        db.add(r)
        db.flush()
        if project:
            project.references.append(r)
        if coll:
            db.add(m.CollectionItem(collection_id=coll.id, reference_id=r.id, position=len(coll.items)))
        created.append(r)
    activity(db, "references_uploaded", f"{len(created)} reference(s) uploaded ({category})",
             project.id if project else None, ids=[r.id for r in created])
    db.commit()
    return [s.reference(r) for r in created]


@router.get("/references/{rid}")
def get_reference(rid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = get_or_404(db, m.Reference, rid)
    d = s.reference(r)
    d["profiles"] = [{"id": pi.profile_id, "role": pi.role} for pi in
                     db.scalars(select(m.ProfileImage).where(m.ProfileImage.reference_id == rid)).all()]
    d["collections"] = [ci.collection_id for ci in
                        db.scalars(select(m.CollectionItem).where(m.CollectionItem.reference_id == rid)).all()]
    return d


@router.patch("/references/{rid}")
def update_reference(rid: int, body: s.ReferencePatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = get_or_404(db, m.Reference, rid)
    data = body.model_dump(exclude_unset=True)
    if "category" in data:
        _check_category(data["category"])
    if "tags" in data:
        data["tags"] = _norm_tags(data["tags"])
    for k, v in data.items():
        setattr(r, k, v)
    db.commit()
    return s.reference(r)


@router.delete("/references/{rid}", status_code=204)
def delete_reference(rid: int, db: Session = Depends(get_db), store: MediaStore = Depends(get_store)) -> None:
    r = get_or_404(db, m.Reference, rid)
    in_use = db.scalars(select(m.Job).where(m.Job.status.in_(("submitted", "running")))).all()
    if any(rid in (j.image_bindings or {}).values() for j in in_use):
        raise HTTPException(409, "reference is used by an active job")
    store.delete("references", r.stored_name)
    db.delete(r)
    db.commit()


@router.get("/references/{rid}/file")
def reference_file(rid: int, db: Session = Depends(get_db), store: MediaStore = Depends(get_store)) -> FileResponse:
    r = get_or_404(db, m.Reference, rid)
    return FileResponse(store.path("references", r.stored_name), media_type=r.mime,
                        filename=r.original_name)


@router.get("/references/{rid}/thumb")
def reference_thumb(rid: int, db: Session = Depends(get_db), store: MediaStore = Depends(get_store)) -> FileResponse:
    r = get_or_404(db, m.Reference, rid)
    return FileResponse(store.thumb_path("references", r.stored_name), media_type="image/webp",
                        headers={"Cache-Control": "max-age=86400"})


# --- collections ----------------------------------------------------------------------


def _collection(c: m.Collection) -> dict[str, Any]:
    return {"id": c.id, "name": c.name, "description": c.description, "project_id": c.project_id,
            "reference_ids": [i.reference_id for i in c.items], "count": len(c.items),
            "cover_urls": [f"/api/references/{i.reference_id}/thumb" for i in c.items[:4]],
            "created_at": s.dt(c.created_at)}


@router.get("/collections")
def list_collections(project_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(m.Collection).order_by(m.Collection.id)
    if project_id is not None:
        q = q.where(m.Collection.project_id == project_id)
    return [_collection(c) for c in db.scalars(q).all()]


@router.post("/collections", status_code=201)
def create_collection(body: s.CollectionIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = m.Collection(name=body.name, description=body.description, project_id=body.project_id)
    db.add(c)
    db.flush()
    for i, rid in enumerate(body.reference_ids):
        get_or_404(db, m.Reference, rid)
        db.add(m.CollectionItem(collection_id=c.id, reference_id=rid, position=i))
    db.commit()
    db.refresh(c)
    return _collection(c)


@router.patch("/collections/{cid}")
def update_collection(cid: int, body: s.CollectionPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_or_404(db, m.Collection, cid)
    data = body.model_dump(exclude_unset=True)
    ids = data.pop("reference_ids", None)
    for k, v in data.items():
        setattr(c, k, v)
    if ids is not None:
        if len(set(ids)) != len(ids):
            raise HTTPException(422, "duplicate reference ids")
        c.items.clear()
        db.flush()
        for i, rid in enumerate(ids):
            get_or_404(db, m.Reference, rid)
            c.items.append(m.CollectionItem(reference_id=rid, position=i))
    db.commit()
    db.refresh(c)
    return _collection(c)


@router.post("/collections/{cid}/items")
def add_to_collection(cid: int, body: s.IdList, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_or_404(db, m.Collection, cid)
    existing = {i.reference_id for i in c.items}
    for rid in body.ids:
        get_or_404(db, m.Reference, rid)
        if rid not in existing:
            c.items.append(m.CollectionItem(reference_id=rid, position=len(c.items)))
            existing.add(rid)
    db.commit()
    db.refresh(c)
    return _collection(c)


@router.delete("/collections/{cid}/items/{rid}")
def remove_from_collection(cid: int, rid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = get_or_404(db, m.Collection, cid)
    c.items[:] = [i for i in c.items if i.reference_id != rid]
    for pos, i in enumerate(c.items):
        i.position = pos
    db.commit()
    return _collection(c)


@router.delete("/collections/{cid}", status_code=204)
def delete_collection(cid: int, db: Session = Depends(get_db)) -> None:
    db.delete(get_or_404(db, m.Collection, cid))
    db.commit()
