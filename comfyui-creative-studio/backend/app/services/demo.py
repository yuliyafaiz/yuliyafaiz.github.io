"""Jewelry campaign demonstration data.

Reference images are *synthetic placeholders drawn with Pillow* (clearly labelled)
so the repository ships no third-party imagery. Replace the product cut-out with a
real product photo (PNG with transparent background) for real results.
"""
from __future__ import annotations

import io
import json
import math
from typing import Any

from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import REPO_ROOT
from . import workflow as wf
from .generation import activity
from .images import MediaStore

DEMO_NAME = "Luxury Jewelry Campaign (demo)"
PLACEHOLDER_NOTE = ("Synthetic placeholder drawn by the demo seeder (not a photograph). "
                    "Replace with your real product photo.")


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def product_cutout(size: int = 768) -> bytes:
    """A stylised solitaire ring on a transparent background."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = s // 2, int(s * 0.58)
    for i in range(28):  # band with simple gold shading
        t = i / 27
        col = (int(170 + 70 * math.sin(t * math.pi)), int(125 + 60 * math.sin(t * math.pi)), int(40 + 30 * t), 255)
        d.ellipse([cx - s * 0.30 + i, cy - s * 0.22 + i * 0.6, cx + s * 0.30 - i, cy + s * 0.22 - i * 0.6],
                  outline=col, width=2)
    d.ellipse([cx - s * 0.245, cy - s * 0.165, cx + s * 0.245, cy + s * 0.165], fill=(0, 0, 0, 0))
    top = cy - int(s * 0.22)
    for dx in (-1, 1):  # prongs
        d.polygon([(cx + dx * 30, top + 10), (cx + dx * 48, top - 70), (cx + dx * 38, top - 72),
                   (cx + dx * 22, top + 10)], fill=(214, 176, 92, 255))
    gem = [(cx, top - 150), (cx + 78, top - 92), (cx + 52, top - 20), (cx, top + 8), (cx - 52, top - 20),
           (cx - 78, top - 92)]
    d.polygon(gem, fill=(205, 225, 240, 255), outline=(150, 175, 195, 255))
    for x, y in gem:  # facets
        d.line([(cx, top - 70), (x, y)], fill=(235, 245, 252, 255), width=2)
    d.polygon([(cx - 20, top - 120), (cx + 8, top - 132), (cx - 6, top - 96)], fill=(255, 255, 255, 255))
    return _png(img)


def style_reference(size: int = 768) -> bytes:
    img = Image.new("RGB", (size, size), (16, 15, 18))
    d = ImageDraw.Draw(img)
    for i in range(0, size, 3):  # marble-like veins
        y = int(size * 0.5 + math.sin(i / 37.0) * 120 + math.sin(i / 11.0) * 18)
        d.point((i, y), fill=(120, 116, 112))
        d.line([(i, y), (i + 2, y + 1)], fill=(70, 68, 66))
    for k in range(6):
        y0 = int(size * (0.12 + 0.15 * k))
        d.line([(0, y0), (size, y0 + int(math.sin(k) * 140))], fill=(48, 46, 50), width=2)
    img = img.filter(ImageFilter.GaussianBlur(1.6))
    d = ImageDraw.Draw(img)
    d.ellipse([size * 0.25, size * 0.68, size * 0.75, size * 0.82], fill=(30, 28, 30))
    return _png(img.filter(ImageFilter.GaussianBlur(2)))


def lighting_reference(size: int = 768) -> bytes:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            dd = math.hypot(x - size * 0.68, y - size * 0.3) / size
            v = max(0.0, 1.0 - dd * 1.7)
            px[x, y] = (int(25 + 230 * v ** 1.6), int(20 + 190 * v ** 1.8), int(18 + 120 * v ** 2.4))
    return _png(img)


def _add_ref(db: Session, store: MediaStore, data: bytes, name: str, title: str, category: str,
             tags: list[str], project: m.Project, favorite: bool = False) -> m.Reference:
    st = store.save("references", data)
    r = m.Reference(title=title, original_name=name, stored_name=st.stored_name, mime=st.mime, width=st.width,
                    height=st.height, has_alpha=st.has_alpha, sha256=st.sha256, phash=st.phash, palette=st.palette,
                    category=category, tags=tags, description=PLACEHOLDER_NOTE, favorite=favorite)
    db.add(r)
    db.flush()
    project.references.append(r)
    return r


def _workflow(db: Session, name: str, file: str, category: str, description: str, project: m.Project,
              object_info: dict[str, Any] | None) -> m.Workflow:
    api = json.loads((REPO_ROOT / "examples" / "workflows" / file).read_text())
    w = m.Workflow(name=name, description=description, category=category, project_id=project.id,
                   is_template=True, source_format="api", original_json=api, api_json=api, api_source="imported",
                   node_types=wf.api_node_types(api), models=wf.api_models(api),
                   parameters=wf.discover_parameters(api, object_info))
    db.add(w)
    db.flush()
    return w


def seed_jewelry_demo(db: Session, store: MediaStore, object_info: dict[str, Any] | None = None) -> m.Project:
    existing = db.scalar(select(m.Project).where(m.Project.name == DEMO_NAME))
    if existing:
        return existing
    p = m.Project(name=DEMO_NAME, client="Demo brand", template_key="jewelry_campaign",
                  description="Winter Collection 2026 — product-faithful packshots and editorial imagery for a "
                              "solitaire ring. Demonstrates profiles, consistency configs, batches and metadata.",
                  meta={"industry": "jewelry", "deliverables": ["1:1 packshot", "4:5 social", "16:9 banner"]})
    db.add(p)
    db.flush()
    for c in ("Winter Collection 2026", "Packshots", "Editorial", "Close-up details"):
        db.add(m.Campaign(project_id=p.id, name=c))
    product = _add_ref(db, store, product_cutout(), "aurora_ring_cutout.png", "Aurora ring — cut-out (placeholder)",
                       "jewelry", ["ring", "gold", "solitaire", "cutout"], p, favorite=True)
    style = _add_ref(db, store, style_reference(), "black_marble_style.png", "Black marble mood (placeholder)",
                     "style", ["marble", "dark", "luxury"], p, favorite=True)
    light = _add_ref(db, store, lighting_reference(), "warm_key_light.png", "Warm key light (placeholder)",
                     "lighting", ["warm", "key light", "soft"], p)
    p.cover_reference_id = product.id
    for name, refs in (("Product originals", [product]), ("Style references", [style]),
                       ("Lighting references", [light])):
        c = m.Collection(name=name, project_id=p.id)
        db.add(c)
        db.flush()
        for i, r in enumerate(refs):
            db.add(m.CollectionItem(collection_id=c.id, reference_id=r.id, position=i))

    prof = m.Profile(kind="product", name="Aurora Solitaire Ring", category="ring",
                     description="Solitaire engagement ring with a single round brilliant stone",
                     attributes={"material": "18k yellow gold", "finish": "high polish",
                                 "stones": "one round brilliant, colourless", "stone_setting": "six-prong",
                                 "shape": "thin round band, 2 mm"},
                     preserve_details=["single centre stone", "six-prong setting", "thin 2 mm band",
                                       "yellow gold colour"],
                     generation_settings={"recommended_denoise": 1.0, "mask_expand": 6, "working_size": 768},
                     notes="Product pixels are composited back after generation (see workflow). "
                           "Replace the placeholder cut-out with a real photo with transparent background.")
    prof.images.append(m.ProfileImage(reference_id=product.id, role="primary", position=0))
    prof.projects.append(p)
    db.add(prof)
    db.flush()

    check = _workflow(db, "Pipeline check — reference board (no model)", "pipeline_check_reference_board_api.json",
                      "utility", "Runs on any ComfyUI with the Creative Studio nodes installed; needs no diffusion "
                      "model. Verifies upload → execution → outputs → metadata end-to-end.", p, object_info)
    packshot = _workflow(db, "Jewelry packshot — product-preserving (SD1.5 inpainting)",
                         "jewelry_product_preserve_sd15_api.json", "jewelry_campaign",
                         "Generates a scene around a product cut-out and pastes the original product pixels back. "
                         "Core nodes only. Needs an SD1.5 inpainting checkpoint.", p, object_info)
    editorial = _workflow(db, "Jewelry editorial — SDXL + IPAdapter style + product composite",
                          "jewelry_editorial_ipadapter_sdxl_api.json", "jewelry_campaign",
                          "Style transfer from a mood reference (IPAdapter) with lighting variants; product "
                          "composited back. Needs SDXL, ComfyUI_IPAdapter_plus and its models.", p, object_info)
    prof.workflows.extend([check, packshot, editorial])
    configs = [
        m.ConsistencyConfig(name="Aurora · pipeline check", workflow_id=check.id, profile_id=prof.id, project_id=p.id,
                            methods=wf.detect_methods(check.node_types),
                            image_bindings={"2.image": style.id, "3.image": light.id}, values={},
                            use_profile_prompt=False,
                            description="Product profile + style + lighting references on a reference board."),
        m.ConsistencyConfig(name="Aurora · packshot on black marble", workflow_id=packshot.id, profile_id=prof.id,
                            project_id=p.id, methods=wf.detect_methods(packshot.node_types),
                            image_bindings={"2.image": product.id}, values={"12.steps": 28, "12.cfg": 6.5},
                            use_profile_prompt=True,
                            description="Product cut-out bound to the inpainting input; profile text appended."),
        m.ConsistencyConfig(name="Aurora · editorial lighting variants", workflow_id=editorial.id, profile_id=prof.id,
                            project_id=p.id, methods=wf.detect_methods(editorial.node_types),
                            image_bindings={"3.image": style.id}, values={"5.weight": 0.6},
                            use_profile_prompt=False,
                            description="Profile loaded in-graph by CS_ProductProfileLoader; IPAdapter weight 0.6."),
    ]
    db.add_all(configs)
    activity(db, "demo_seeded", "Jewelry demo project created", p.id, "project", p.id)
    db.commit()
    return p
