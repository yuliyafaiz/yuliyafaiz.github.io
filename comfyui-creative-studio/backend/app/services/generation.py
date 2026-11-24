"""Job submission and execution tracking.

Truth model
-----------
* ``/history/{prompt_id}`` is the source of truth for terminal states. A job is
  marked ``completed`` only when ComfyUI reports success *and* outputs were
  downloaded. WebSocket events are used only for live progress.
* If ComfyUI is unreachable the job keeps its last known state and is flagged
  ``connection: "unreachable"`` — it is never guessed as finished or failed.
* A prompt that is neither queued, running nor in history for
  ``lost_job_grace`` seconds (e.g. ComfyUI restarted) becomes ``lost``.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .. import models as m
from ..config import Settings
from . import workflow as wf
from .comfy import ComfyClient, ComfyError, ComfyUnavailable, interpret_history, output_images
from .images import ImageError, MediaStore

log = logging.getLogger("creative_studio.generation")

ACTIVE = ("submitted", "running")
TERMINAL = ("completed", "failed", "interrupted", "cancelled", "lost")


def now() -> datetime:
    return datetime.now(timezone.utc)


def activity(db: Session, kind: str, message: str, project_id: int | None = None,
             entity_type: str | None = None, entity_id: int | None = None, **data: Any) -> None:
    db.add(m.Activity(kind=kind, message=message, project_id=project_id,
                      entity_type=entity_type, entity_id=entity_id, data=data))


class ComfyManager:
    """Holds the ComfyUI client for the currently configured URL."""

    def __init__(self, url: str, transport: Any = None):
        self.transport = transport
        self.client = ComfyClient(url, transport=transport)
        self.client_id = f"creative-studio-{uuid.uuid4().hex[:12]}"
        # prompt_id -> {"value", "max", "node", "updated"} from WebSocket events
        self.live: dict[str, dict[str, Any]] = {}
        self.ws_connected = False
        self.last_error: str | None = None

    @property
    def url(self) -> str:
        return self.client.base_url

    async def set_url(self, url: str) -> None:
        old = self.client
        self.client = ComfyClient(url, transport=self.transport)
        await old.aclose()

    def handle_ws_message(self, msg: dict[str, Any]) -> None:
        t, d = msg.get("type"), msg.get("data") or {}
        pid = d.get("prompt_id")
        if not pid:
            return
        entry = self.live.setdefault(pid, {})
        entry["updated"] = time.time()
        if t == "progress":
            entry.update(value=d.get("value"), max=d.get("max"), node=d.get("node"))
        elif t == "executing":
            entry["node"] = d.get("node")
            entry["started"] = True
        elif t == "execution_start":
            entry["started"] = True
        elif t == "execution_cached":
            entry["cached_nodes"] = d.get("nodes", [])
        elif t in ("execution_success", "execution_error", "execution_interrupted"):
            entry["finished_event"] = t

    async def ws_loop(self, stop: asyncio.Event) -> None:
        """Maintain a WebSocket connection for live progress (best effort)."""
        import websockets

        while not stop.is_set():
            try:
                async with websockets.connect(f"{self.client.ws_url}?clientId={self.client_id}",
                                              max_size=None, open_timeout=5) as ws:
                    self.ws_connected = True
                    while not stop.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        if isinstance(raw, (bytes, bytearray)):
                            continue  # binary preview frames
                        with contextlib.suppress(ValueError):
                            self.handle_ws_message(json.loads(raw))
            except Exception as exc:  # noqa: BLE001 - reconnect on any failure
                self.last_error = f"websocket: {exc.__class__.__name__}"
            self.ws_connected = False
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=3.0)


# --- submission ----------------------------------------------------------------------


class SubmissionError(ValueError):
    pass


def _profile_payload(profile: m.Profile) -> dict[str, Any]:
    return {
        "id": profile.id, "kind": profile.kind, "name": profile.name, "description": profile.description,
        "category": profile.category, "attributes": profile.attributes,
        "preserve_details": profile.preserve_details, "notes": profile.notes,
        "images": [{"reference_id": pi.reference_id, "role": pi.role} for pi in profile.images],
    }


async def upload_reference(manager: ComfyManager, store: MediaStore, ref: m.Reference, subfolder: str) -> str:
    """Upload a reference into ComfyUI's input dir; return the value LoadImage expects."""
    data = store.path("references", ref.stored_name).read_bytes()
    name = f"ref-{ref.sha256[:16]}{Path(ref.stored_name).suffix}"
    resp = await manager.client.upload_image(data, name, subfolder, ref.mime)
    sub = resp.get("subfolder") or ""
    return f"{sub}/{resp['name']}" if sub else resp["name"]


def _default(vals: dict[str, Any], key: str, value: Any) -> None:
    """Set ``key`` unless the user supplied a non-empty value."""
    if vals.get(key) in (None, ""):
        vals[key] = value


async def _cached_upload(manager: ComfyManager, store: MediaStore, ref: m.Reference, settings: Settings,
                         cache: dict[int, str] | None) -> str:
    if cache is not None and ref.id in cache:
        return cache[ref.id]
    name = await upload_reference(manager, store, ref, settings.comfy_upload_subfolder)
    if cache is not None:
        cache[ref.id] = name
    return name


async def prepare_prompt(db: Session, manager: ComfyManager, store: MediaStore, settings: Settings,
                         workflow: m.Workflow, values: dict[str, Any], bindings: dict[str, int],
                         profile: m.Profile | None, project: m.Project | None, job_id: int | None = None,
                         campaign: str | None = None, upload_cache: dict[int, str] | None = None) -> dict[str, Any]:
    if workflow.api_json is None:
        raise SubmissionError("workflow has no executable API-format prompt; import an API export or convert it")
    image_files: dict[str, str] = {}
    params = {p["key"]: p for p in workflow.parameters}
    for key, ref_id in bindings.items():
        ref = db.get(m.Reference, ref_id)
        if ref is None:
            raise SubmissionError(f"reference {ref_id} bound to {key} does not exist")
        if key in params and params[key].get("type") != "image":
            raise SubmissionError(f"{key} is not an image input")
        image_files[key] = await _cached_upload(manager, store, ref, settings, upload_cache)
    vals = dict(values)
    # Profile → Creative Studio profile-loader nodes get the profile JSON automatically.
    if profile is not None:
        for nid, node in workflow.api_json.items():
            if node["class_type"] in ("CS_ProductProfileLoader", "CS_CharacterProfileLoader") \
                    and not wf.is_link(node["inputs"].get("profile_json")):
                payload = _profile_payload(profile)
                payload["image_files"] = {}
                for pi in profile.images:
                    payload["image_files"].setdefault(pi.role, []).append(
                        await _cached_upload(manager, store, pi.reference, settings, upload_cache))
                _default(vals, f"{nid}.profile_json", json.dumps(payload))
    if project is not None:
        for nid, node in workflow.api_json.items():
            if node["class_type"] == "CS_ProjectMetadata":
                _default(vals, f"{nid}.project_id", str(project.id))
                _default(vals, f"{nid}.project_name", project.name)
    for nid, node in workflow.api_json.items():
        if node["class_type"] == "CS_ProjectMetadata":
            if job_id is not None:
                _default(vals, f"{nid}.job_id", str(job_id))
            if campaign:
                _default(vals, f"{nid}.campaign", campaign)
    try:
        return wf.build_prompt(workflow.api_json, workflow.parameters, vals, image_files)
    except wf.PromptBuildError as exc:
        raise SubmissionError(str(exc)) from exc


def apply_variation(prompt: dict[str, Any], index: int, seed_mode: str, base_seed: int | None,
                    rng: random.Random) -> dict[str, int]:
    """Set seeds for variation ``index``. Returns the seeds applied."""
    keys = wf.seed_keys(prompt)
    applied: dict[str, int] = {}
    # Creative Studio variant nodes: variation i selects variant i (seed derives from it in-graph).
    for nid, node in prompt.items():
        if node["class_type"] == "CS_BatchVariantManager" and not wf.is_link(node["inputs"].get("variant_index")):
            node["inputs"]["variant_index"] = index
            applied[f"{nid}.variant_index"] = index
    for key in keys:
        nid, _, inp = key.partition(".")
        current = int(prompt[nid]["inputs"][inp])
        if seed_mode == "random":
            seed = rng.randint(0, 2**48)
        elif seed_mode == "increment":
            seed = (base_seed if base_seed is not None else current) + index
        else:  # fixed
            seed = base_seed if base_seed is not None else current
        prompt[nid]["inputs"][inp] = seed
        applied[key] = seed
    return applied


async def submit_job(db: Session, manager: ComfyManager, job: m.Job, prompt: dict[str, Any]) -> m.Job:
    job.submitted_prompt = prompt
    job.server_url = manager.url
    try:
        resp = await manager.client.submit(prompt, manager.client_id,
                                           {"job_id": job.id, "project_id": job.project_id, "batch_id": job.batch_id})
    except ComfyUnavailable as exc:
        job.status, job.error = "failed", {"type": "comfy_unavailable", "message": str(exc)}
        job.finished_at = now()
    except ComfyError as exc:
        payload = exc.payload if isinstance(exc.payload, dict) else {"raw": exc.payload}
        err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        job.status = "failed"
        job.error = {"type": err.get("type", "rejected"), "message": err.get("message", str(exc)),
                     "node_errors": payload.get("node_errors", {})}
        job.finished_at = now()
    else:
        job.comfy_prompt_id = resp["prompt_id"]
        job.status = "submitted"
        job.submitted_at = now()
        if resp.get("node_errors"):
            job.progress = {**job.progress, "node_warnings": resp["node_errors"]}
    db.commit()
    return job


# --- tracking -------------------------------------------------------------------------


class Tracker:
    def __init__(self, sf: sessionmaker[Session], manager: ComfyManager, store: MediaStore, settings: Settings):
        self.sf, self.manager, self.store, self.settings = sf, manager, store, settings
        self._absent_since: dict[int, float] = {}
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []
        self.comfy_reachable: bool | None = None

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._loop()), asyncio.create_task(self.manager.ws_loop(self._stop))]

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.poll_once()
            except Exception:  # noqa: BLE001
                log.exception("tracker poll failed")
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.poll_interval)

    async def poll_once(self) -> None:
        with self.sf() as db:
            jobs = db.scalars(select(m.Job).where(m.Job.status.in_(ACTIVE))).all()
            for job in jobs:
                await self._poll_job(db, job)
            db.commit()

    async def _poll_job(self, db: Session, job: m.Job) -> None:
        pid = job.comfy_prompt_id
        if not pid:
            return
        client = self.manager.client
        try:
            entry = await client.history(pid)
            if entry is None:
                where, pos = await client.queue_position(pid)
        except ComfyUnavailable:
            self.comfy_reachable = False
            job.progress = {**job.progress, "connection": "unreachable"}
            return
        except ComfyError as exc:
            job.progress = {**job.progress, "connection": f"error {exc.status}"}
            return
        self.comfy_reachable = True
        live = self.manager.live.get(pid, {})
        if entry is None:
            if where == "absent":
                first = self._absent_since.setdefault(job.id, time.monotonic())
                if time.monotonic() - first > self.settings.lost_job_grace:
                    job.status = "lost"
                    job.error = {"type": "lost", "message": "Prompt is no longer queued, running or in "
                                 "ComfyUI history (was ComfyUI restarted?). No outputs were recorded."}
                    job.finished_at = now()
                    activity(db, "job_lost", f"Job #{job.id} lost", job.project_id, "job", job.id)
                return
            self._absent_since.pop(job.id, None)
            job.status = "running" if where == "running" else "submitted"
            job.progress = {"connection": "ok", "queue": where, "queue_position": pos,
                            "value": live.get("value"), "max": live.get("max"), "node": live.get("node")}
            return
        self._absent_since.pop(job.id, None)
        result = interpret_history(entry)
        job.status_messages = result.messages
        job.execution_seconds = result.execution_seconds
        if result.state == "running":
            job.status = "running"
            return
        if result.state == "completed":
            try:
                await self._collect_outputs(db, job, result.outputs)
            except (ComfyError, ImageError, OSError) as exc:
                job.status = "failed"
                job.error = {"type": "output_retrieval_failed", "message": str(exc)}
                job.finished_at = now()
                return
            job.status = "completed"
            job.progress = {"connection": "ok", "value": 1, "max": 1}
            activity(db, "job_completed", f"Job #{job.id} completed with {len(job.outputs)} output(s)",
                     job.project_id, "job", job.id)
        else:
            job.status = result.state
            job.error = result.error
            activity(db, f"job_{result.state}", f"Job #{job.id} {result.state}: "
                     f"{(result.error or {}).get('message', '')}"[:300], job.project_id, "job", job.id)
        job.finished_at = now()
        self.manager.live.pop(pid, None)

    async def _collect_outputs(self, db: Session, job: m.Job, outputs: dict[str, Any]) -> None:
        files = [f for f in output_images(outputs) if f["type"] == "output"]
        node_meta = {str(nid): o.get("cs_metadata") for nid, o in outputs.items() if o.get("cs_metadata")}
        base_meta = await self.reproducibility_record(db, job, node_meta)
        for f in files:
            data = await self.manager.client.view(f["filename"], f["subfolder"], f["type"])
            stored = self.store.save("outputs", data)
            db.add(m.Output(
                job_id=job.id, project_id=job.project_id, stored_name=stored.stored_name,
                width=stored.width, height=stored.height, node_id=f["node_id"],
                comfy_filename=f["filename"], comfy_subfolder=f["subfolder"], comfy_type=f["type"],
                meta={**base_meta, "output": {**f, "sha256": stored.sha256, "width": stored.width,
                                              "height": stored.height}},
            ))
        db.flush()
        db.refresh(job)

    async def reproducibility_record(self, db: Session, job: m.Job, node_meta: dict[str, Any]) -> dict[str, Any]:
        prompt = job.submitted_prompt or {}
        gen = wf.extract_generation_metadata(prompt)
        workflow = db.get(m.Workflow, job.workflow_id) if job.workflow_id else None
        refs = []
        for key, rid in (job.image_bindings or {}).items():
            r = db.get(m.Reference, rid)
            if r:
                refs.append({"parameter": key, "reference_id": r.id, "title": r.title or r.original_name,
                             "sha256": r.sha256, "category": r.category})
        hashes: dict[str, Any] = {}
        for meta in node_meta.values():
            for item in meta if isinstance(meta, list) else [meta]:
                hashes.update((item or {}).get("model_hashes", {}))
        for mdl in gen["models"]:
            if mdl["name"] in hashes:
                mdl["sha256"] = hashes[mdl["name"]]
            elif mdl["kind"] == "checkpoint":
                md = await self._safe_model_meta("checkpoints", mdl["name"])
                if md and md.get("modelspec.hash_sha256"):
                    mdl["sha256"] = md["modelspec.hash_sha256"]
            mdl.setdefault("sha256", None)
        # Values computed inside the graph (template prompts, variant seeds) are taken from the
        # CS_GenerationMetadataSaver record, which saw the actual runtime values.
        runtime = next((item for meta in node_meta.values() for item in (meta if isinstance(meta, list) else [meta])
                        if item), None)
        if runtime:
            for key, rkey in (("prompt", "prompt"), ("negative_prompt", "negative_prompt"), ("seed", "seed")):
                if gen.get(key) is None and runtime.get(rkey) is not None:
                    gen[key] = runtime[rkey]
                    gen.setdefault("runtime_values_from", runtime.get("node_id"))
            if runtime.get("variant"):
                gen["variant"] = {k: runtime["variant"].get(k) for k in ("label", "text", "index", "seed")}
        return {
            "schema": "creative-studio/generation@1",
            "job": {"id": job.id, "batch_id": job.batch_id, "variation_index": job.variation_index,
                    "project_id": job.project_id, "campaign_id": job.campaign_id,
                    "consistency_config_id": job.consistency_config_id},
            "workflow": {"id": workflow.id, "name": workflow.name, "category": workflow.category} if workflow else None,
            "generation": gen,
            "parameter_values": job.parameter_values,
            "reference_images": refs,
            "comfy": {"prompt_id": job.comfy_prompt_id, "server_url": job.server_url,
                      "execution_seconds": job.execution_seconds},
            "node_metadata": node_meta or None,
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "completed_at": now().isoformat(),
        }

    async def _safe_model_meta(self, folder: str, name: str) -> dict[str, Any] | None:
        try:
            return await self.manager.client.model_metadata(folder, name)
        except ComfyError:
            return None
