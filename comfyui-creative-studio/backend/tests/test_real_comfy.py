"""Integration test against a real ComfyUI with the Creative Studio nodes installed.

Skipped unless CS_TEST_COMFY_URL is set, e.g.:
    CS_TEST_COMFY_URL=http://127.0.0.1:8188 pytest -m comfy
Uses the model-free "pipeline check" workflow, so no checkpoints are needed.
"""
import os
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

URL = os.environ.get("CS_TEST_COMFY_URL")
pytestmark = [pytest.mark.comfy, pytest.mark.skipif(not URL, reason="CS_TEST_COMFY_URL not set")]


def test_pipeline_check_end_to_end(tmp_path):
    try:
        oi = httpx.get(f"{URL}/object_info/CS_ReferenceCollector", timeout=5).json()
    except httpx.HTTPError:
        pytest.skip("ComfyUI not reachable")
    if not oi:
        pytest.skip("Creative Studio nodes are not installed in this ComfyUI")
    settings = Settings(data_dir=tmp_path / "data", comfy_url=URL, poll_interval=0.3,
                        frontend_dist=tmp_path / "nodist")
    with TestClient(create_app(settings)) as c:  # real tracker + WebSocket running
        deadline = time.time() + 10
        while not c.get("/api/comfy/status").json()["websocket_connected"] and time.time() < deadline:
            time.sleep(0.2)
        assert c.get("/api/comfy/status").json()["websocket_connected"]
        project = c.post("/api/demo/jewelry").json()
        cfg = next(x for x in c.get(f"/api/consistency?project_id={project['id']}").json()
                   if x["name"] == "Aurora · pipeline check")
        dep = c.get(f"/api/workflows/{cfg['workflow_id']}/dependencies").json()
        assert dep["ready"], dep
        batch = c.post("/api/generate", json={"consistency_config_id": cfg["id"], "variations": 2,
                                              "campaign_id": project["campaigns"][0]["id"]}).json()
        ids = [j["id"] for j in batch["jobs"]]
        deadline = time.time() + 60
        while time.time() < deadline:
            jobs = [c.get(f"/api/jobs/{i}").json() for i in ids]
            if all(j["status"] in ("completed", "failed", "interrupted", "lost") for j in jobs):
                break
            time.sleep(0.3)
        assert [j["status"] for j in jobs] == ["completed", "completed"], [j["error"] for j in jobs]
        outs = c.get(f"/api/outputs?batch_id={batch['batch_id']}").json()
        assert len(outs) == 6  # 3 references on the board × 2 variations
        meta = outs[0]["meta"]
        runtime = next(iter(meta["node_metadata"].values()))[0]
        assert runtime["project"]["job_id"] in {str(i) for i in ids}
        assert runtime["profile"]["name"] == "Aurora Solitaire Ring"
        assert {o["meta"]["generation"]["variant"]["label"] for o in outs} == {"warm", "cool"}
        assert c.get(outs[0]["file_url"]).content[:4] == b"\x89PNG"
