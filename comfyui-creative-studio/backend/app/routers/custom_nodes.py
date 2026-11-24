"""Custom node package information and installation status on the connected ComfyUI."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends

from ..config import REPO_ROOT
from ..deps import get_manager
from ..services.comfy import ComfyError
from ..services.generation import ComfyManager

router = APIRouter(tags=["custom-nodes"])

PACKAGE_DIR = REPO_ROOT / "custom_nodes" / "comfyui-creative-studio-nodes"


@router.get("/custom-nodes")
async def custom_nodes(manager: ComfyManager = Depends(get_manager)) -> dict[str, Any]:
    manifest_path = PACKAGE_DIR / "node_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"nodes": []}
    installed: dict[str, Any] | None
    try:
        oi = await manager.client.object_info()
        installed = {n["name"]: n["name"] in oi for n in manifest["nodes"]}
        live = {n["name"]: oi[n["name"]] for n in manifest["nodes"] if n["name"] in oi}
    except ComfyError:
        installed, live = None, {}
    return {"package": manifest.get("package"), "version": manifest.get("version"),
            "package_path": "custom_nodes/comfyui-creative-studio-nodes",
            "nodes": [{**n, "installed": None if installed is None else installed.get(n["name"], False),
                       "live_definition": live.get(n["name"])} for n in manifest["nodes"]],
            "comfy_reachable": installed is not None}
