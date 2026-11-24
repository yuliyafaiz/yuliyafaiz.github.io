"""Test fixtures: isolated data dir + a scriptable fake ComfyUI (httpx MockTransport)."""
from __future__ import annotations

import io
import json
import re
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app

OBJECT_INFO: dict[str, Any] = {
    "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["model_a.safetensors"], {}]}},
                               "input_order": {"required": ["ckpt_name"]},
                               "output": ["MODEL", "CLIP", "VAE"], "output_node": False},
    "CLIPTextEncode": {"input": {"required": {"text": ["STRING", {"multiline": True}], "clip": ["CLIP", {}]}},
                       "input_order": {"required": ["text", "clip"]}, "output": ["CONDITIONING"]},
    "EmptyLatentImage": {"input": {"required": {"width": ["INT", {"default": 512, "min": 16, "max": 8192}],
                                                "height": ["INT", {"default": 512}], "batch_size": ["INT", {}]}},
                         "input_order": {"required": ["width", "height", "batch_size"]}, "output": ["LATENT"]},
    "KSampler": {"input": {"required": {
        "model": ["MODEL", {}], "seed": ["INT", {"control_after_generate": True, "min": 0}],
        "steps": ["INT", {"min": 1, "max": 10000}], "cfg": ["FLOAT", {"min": 0.0, "max": 100.0, "step": 0.1}],
        "sampler_name": [["euler", "dpmpp_2m"], {}], "scheduler": [["normal", "karras"], {}],
        "positive": ["CONDITIONING", {}], "negative": ["CONDITIONING", {}], "latent_image": ["LATENT", {}],
        "denoise": ["FLOAT", {"default": 1.0}]}},
        "input_order": {"required": ["model", "seed", "steps", "cfg", "sampler_name", "scheduler", "positive",
                                     "negative", "latent_image", "denoise"]},
        "output": ["LATENT"]},
    "VAEDecode": {"input": {"required": {"samples": ["LATENT", {}], "vae": ["VAE", {}]}}, "output": ["IMAGE"]},
    "SaveImage": {"input": {"required": {"images": ["IMAGE", {}], "filename_prefix": ["STRING", {}]}},
                  "output": [], "output_node": True},
    "LoadImage": {"input": {"required": {"image": [["example.png"], {"image_upload": True}]}},
                  "output": ["IMAGE", "MASK"]},
}

API_WORKFLOW: dict[str, Any] = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler",
                                               "scheduler": "normal", "denoise": 1.0, "model": ["4", 0],
                                               "positive": ["6", 0], "negative": ["7", 0],
                                               "latent_image": ["5", 0]}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model_a.safetensors"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a gold ring", "clip": ["4", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["4", 1]}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "test", "images": ["8", 0]}},
    "10": {"class_type": "LoadImage", "inputs": {"image": "example.png"}},
}


def png_bytes(color=(200, 150, 50), size=(64, 48), mode="RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, color if mode == "RGB" else (*color, 128)).save(buf, "PNG")
    return buf.getvalue()


class FakeComfy:
    """Minimal ComfyUI double. ``scenario`` controls what each new prompt does."""

    def __init__(self) -> None:
        self.up = True
        self.scenario = "success"  # success|error|interrupt|lost|pending
        self.prompts: dict[str, dict[str, Any]] = {}
        self.uploads: list[dict[str, Any]] = []
        self.interrupted: list[str] = []
        self.deleted: list[str] = []
        self.reject_next: dict[str, Any] | None = None

    # test helpers ------------------------------------------------------------
    def finish(self, pid: str) -> None:
        p = self.prompts[pid]
        p["state"] = {"success": "done", "error": "error", "interrupt": "interrupted"}.get(p["scenario"], p["state"])

    def finish_all(self) -> None:
        for pid in list(self.prompts):
            self.finish(pid)

    def history_entry(self, pid: str) -> dict[str, Any] | None:
        p = self.prompts[pid]
        ts = [["execution_start", {"prompt_id": pid, "timestamp": 1000}]]
        if p["state"] == "done":
            return {"prompt": [0, pid, p["prompt"], {}, []],
                    "outputs": {"9": {"images": [{"filename": f"{pid[:8]}_00001_.png", "subfolder": "", "type": "output"},
                                                 {"filename": "preview.png", "subfolder": "", "type": "temp"}]}},
                    "status": {"status_str": "success", "completed": True,
                               "messages": ts + [["execution_success", {"prompt_id": pid, "timestamp": 3500}]]}}
        if p["state"] == "error":
            return {"prompt": [0, pid, p["prompt"], {}, []], "outputs": {},
                    "status": {"status_str": "error", "completed": False, "messages": ts + [[
                        "execution_error", {"prompt_id": pid, "node_id": "3", "node_type": "KSampler",
                                            "exception_type": "RuntimeError", "exception_message": "out of memory",
                                            "traceback": ["..."], "timestamp": 2000}]]}}
        if p["state"] == "interrupted":
            return {"prompt": [0, pid, p["prompt"], {}, []], "outputs": {},
                    "status": {"status_str": "error", "completed": False, "messages": ts + [[
                        "execution_interrupted", {"prompt_id": pid, "node_id": "3", "timestamp": 1500}]]}}
        return None

    # transport ----------------------------------------------------------------
    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("connection refused", request=request)
        path, method = request.url.path, request.method
        if path == "/system_stats":
            return httpx.Response(200, json={"system": {"comfyui_version": "0.46.0", "os": "test",
                                                        "python_version": "3.13.0 (main)"},
                                             "devices": [{"name": "fake", "type": "mps"}]})
        if path == "/object_info":
            return httpx.Response(200, json=OBJECT_INFO)
        if path == "/upload/image":
            body = request.content.decode("latin-1")
            name = re.search(r'filename="([^"]+)"', body).group(1)
            sub = re.search(r'name="subfolder"\r\n\r\n([^\r]*)', body).group(1)
            self.uploads.append({"name": name, "subfolder": sub})
            return httpx.Response(200, json={"name": name, "subfolder": sub, "type": "input"})
        if path == "/prompt" and method == "POST":
            data = json.loads(request.content)
            if self.reject_next:
                err, self.reject_next = self.reject_next, None
                return httpx.Response(400, json=err)
            pid = str(uuid.uuid4())
            state = "lost" if self.scenario == "lost" else ("pending" if self.scenario == "pending" else "running")
            self.prompts[pid] = {"prompt": data["prompt"], "extra": data.get("extra_data"), "state": state,
                                 "scenario": self.scenario}
            return httpx.Response(200, json={"prompt_id": pid, "number": len(self.prompts), "node_errors": {}})
        if path == "/queue" and method == "GET":
            running = [[0, pid, {}, {}, []] for pid, p in self.prompts.items() if p["state"] == "running"]
            pending = [[1, pid, {}, {}, []] for pid, p in self.prompts.items() if p["state"] == "pending"]
            return httpx.Response(200, json={"queue_running": running, "queue_pending": pending})
        if path == "/queue" and method == "POST":
            for pid in json.loads(request.content).get("delete", []):
                self.deleted.append(pid)
                self.prompts[pid]["state"] = "deleted"
            return httpx.Response(200)
        if path.startswith("/history/"):
            pid = path.rsplit("/", 1)[1]
            entry = self.history_entry(pid) if pid in self.prompts else None
            return httpx.Response(200, json={pid: entry} if entry else {})
        if path == "/interrupt":
            pid = json.loads(request.content or b"{}").get("prompt_id")
            self.interrupted.append(pid)
            if pid in self.prompts:
                self.prompts[pid]["state"] = "interrupted"
            return httpx.Response(200)
        if path == "/view":
            return httpx.Response(200, content=png_bytes((30, 60, 90), (64, 64)), headers={"content-type": "image/png"})
        if path.startswith("/view_metadata/"):
            return httpx.Response(200, json={"modelspec.hash_sha256": "0xabc"})
        return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def fake() -> FakeComfy:
    return FakeComfy()


@pytest.fixture
def client(tmp_path, fake):
    settings = Settings(data_dir=tmp_path / "data", enable_tracker=False, lost_job_grace=0.0,
                        comfy_url="http://comfy.test", frontend_dist=tmp_path / "nodist")
    app = create_app(settings, comfy_transport=httpx.MockTransport(fake.handler))
    with TestClient(app) as c:
        c.fake = fake
        c.tracker = app.state.tracker
        c.poll = lambda: c.portal.call(app.state.tracker.poll_once)
        yield c


@pytest.fixture
def project(client):
    return client.post("/api/projects", json={"name": "Jewelry", "template_key": "jewelry_campaign"}).json()


@pytest.fixture
def ref(client, project):
    files = [("files", ("ring.png", png_bytes(), "image/png"))]
    r = client.post("/api/references", files=files, data={"category": "jewelry", "tags": "Gold, ring",
                                                          "project_id": str(project["id"])})
    assert r.status_code == 201, r.text
    return r.json()[0]


@pytest.fixture
def workflow(client, project):
    r = client.post("/api/workflows", json={"name": "T2I", "data": API_WORKFLOW, "category": "jewelry_campaign",
                                            "project_id": project["id"]})
    assert r.status_code == 201, r.text
    return r.json()
