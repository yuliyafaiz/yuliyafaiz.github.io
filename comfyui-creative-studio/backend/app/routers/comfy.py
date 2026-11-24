"""Module 6 — ComfyUI integration: connection, diagnostics, node catalogue, settings."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..deps import get_db, get_manager, get_tracker
from ..services.comfy import ComfyClient, ComfyError, ComfyUnavailable
from ..services.generation import ComfyManager, Tracker

router = APIRouter(tags=["comfyui"])


async def comfy_status(manager: ComfyManager, tracker: Tracker | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"url": manager.url, "reachable": False, "websocket_connected": manager.ws_connected,
                           "client_id": manager.client_id}
    try:
        stats = await manager.client.system_stats()
        q = await manager.client.queue()
    except ComfyUnavailable as exc:
        out["error"] = str(exc)
        return out
    except ComfyError as exc:
        out["error"] = f"{exc} — is this URL a ComfyUI server?"
        return out
    sysinfo = stats.get("system", {})
    out.update(
        reachable=True,
        version=sysinfo.get("comfyui_version"),
        python=sysinfo.get("python_version", "").split(" ")[0],
        pytorch=sysinfo.get("pytorch_version"),
        os=sysinfo.get("os"),
        ram_total=sysinfo.get("ram_total"), ram_free=sysinfo.get("ram_free"),
        devices=[{k: d.get(k) for k in ("name", "type", "vram_total", "vram_free")} for d in stats.get("devices", [])],
        argv=sysinfo.get("argv"),
        queue_running=len(q.get("queue_running", [])), queue_pending=len(q.get("queue_pending", [])),
    )
    return out


@router.get("/comfy/status")
async def status(manager: ComfyManager = Depends(get_manager), tracker: Tracker = Depends(get_tracker)) -> dict[str, Any]:
    return await comfy_status(manager, tracker)


@router.get("/comfy/diagnostics")
async def diagnostics(manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    st = await comfy_status(manager)
    checks = [{"name": "HTTP reachable", "ok": st["reachable"], "detail": st.get("error") or st.get("version")}]
    if st["reachable"]:
        try:
            oi = await manager.client.object_info(refresh=True)
            checks.append({"name": "/object_info", "ok": True, "detail": f"{len(oi)} node classes"})
            cs = sorted(k for k in oi if k.startswith("CS_"))
            checks.append({"name": "Creative Studio nodes", "ok": bool(cs),
                           "detail": ", ".join(cs) or "not installed (see Custom Nodes page)"})
            ipa = "IPAdapterAdvanced" in oi
            checks.append({"name": "IPAdapter (ComfyUI_IPAdapter_plus)", "ok": ipa,
                           "detail": "installed" if ipa else "optional; needed for IPAdapter workflows"})
            ckpts = (oi.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {})
                     .get("ckpt_name", [[]])[0])
            checks.append({"name": "Checkpoints visible", "ok": bool(ckpts),
                           "detail": f"{len(ckpts)} found" + (f": {', '.join(ckpts[:5])}" if ckpts else
                                                               " — add a model to ComfyUI/models/checkpoints")})
        except ComfyError as exc:
            checks.append({"name": "/object_info", "ok": False, "detail": str(exc)})
        checks.append({"name": "WebSocket progress", "ok": manager.ws_connected,
                       "detail": "connected" if manager.ws_connected else (manager.last_error or "connecting…")})
        devs = st.get("devices") or []
        if devs:
            d = devs[0]
            checks.append({"name": "Compute device", "ok": d.get("type") != "cpu",
                           "detail": f"{d.get('name')} ({d.get('type')})" + (
                               " — CPU-only generation is very slow" if d.get("type") == "cpu" else "")})
    return {"status": st, "checks": checks}


@router.get("/comfy/nodes")
async def nodes(search: str = "", category: str = "", limit: int = 200,
                manager: ComfyManager = Depends(get_manager)) -> list[dict[str, Any]]:
    try:
        oi = await manager.client.object_info()
    except ComfyUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    q = search.lower()
    out = []
    for name, info in oi.items():
        if q and q not in name.lower() and q not in str(info.get("display_name", "")).lower():
            continue
        if category and not str(info.get("category", "")).startswith(category):
            continue
        out.append({"name": name, "display_name": info.get("display_name"), "category": info.get("category"),
                    "output_node": info.get("output_node", False), "outputs": info.get("output", []),
                    "inputs": list((info.get("input", {}).get("required") or {}).keys()) +
                    list((info.get("input", {}).get("optional") or {}).keys())})
        if len(out) >= limit:
            break
    return out


@router.get("/comfy/nodes/{name}")
async def node(name: str, manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    try:
        oi = await manager.client.object_info()
    except ComfyUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if name not in oi:
        raise HTTPException(404, f"node {name} not installed on the connected ComfyUI")
    return oi[name]


@router.get("/settings")
def get_settings(manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    return {"comfy_url": manager.url}


@router.put("/settings")
async def put_settings(body: s.ComfySettingsIn, db: Session = Depends(get_db),
                       manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    url = body.comfy_url.rstrip("/")
    row = db.get(m.AppSetting, "comfy_url")
    if row:
        row.value = url
    else:
        db.add(m.AppSetting(key="comfy_url", value=url))
    db.commit()
    await manager.set_url(url)
    return {"comfy_url": url, "status": await comfy_status(manager)}


@router.post("/settings/test")
async def test_url(body: s.ComfySettingsIn) -> dict[str, Any]:
    """Test a URL without saving it."""
    c = ComfyClient(body.comfy_url)
    try:
        st = await c.system_stats()
        return {"reachable": True, "version": st.get("system", {}).get("comfyui_version")}
    except ComfyError as exc:
        return {"reachable": False, "error": str(exc)}
    finally:
        await c.aclose()
