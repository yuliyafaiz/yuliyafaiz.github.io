"""ComfyUI HTTP/WebSocket client.

Verified against ComfyUI 0.46.0 (server.py routes). Only long-standing routes
are used so older versions keep working: ``/system_stats``, ``/object_info``,
``/prompt``, ``/queue``, ``/history/{id}``, ``/interrupt``, ``/view``,
``/upload/image``, ``/view_metadata/{folder}`` and ``/ws?clientId=``.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


class ComfyError(RuntimeError):
    """Error talking to ComfyUI; ``payload`` holds ComfyUI's error JSON if any."""

    def __init__(self, message: str, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class ComfyUnavailable(ComfyError):
    pass


@dataclass
class HistoryResult:
    """Normalised view of a /history entry."""

    state: str  # running|completed|failed|interrupted
    outputs: dict[str, Any] = field(default_factory=dict)
    messages: list[Any] = field(default_factory=list)
    error: dict[str, Any] | None = None
    execution_seconds: float | None = None


def interpret_history(entry: dict[str, Any]) -> HistoryResult:
    """Decide a job's terminal state from a history entry.

    A job is only "completed" when ComfyUI reports ``status_str == "success"``
    and ``completed == True``. Interrupts are reported by ComfyUI as errors with
    an ``execution_interrupted`` message, which we surface distinctly.
    """
    status = entry.get("status") or {}
    msgs = status.get("messages") or []
    kinds = {m[0] for m in msgs if isinstance(m, list) and m}
    start = next((m[1].get("timestamp") for m in msgs if m and m[0] == "execution_start"), None)
    end = next((m[1].get("timestamp") for m in reversed(msgs)
                if m and m[0] in ("execution_success", "execution_error", "execution_interrupted")), None)
    secs = (end - start) / 1000 if start and end else None
    outputs = entry.get("outputs") or {}
    if status.get("status_str") == "success" and status.get("completed"):
        return HistoryResult("completed", outputs, msgs, None, secs)
    if "execution_interrupted" in kinds:
        return HistoryResult("interrupted", outputs, msgs, {"type": "interrupted",
                             "message": "Execution was interrupted"}, secs)
    if status.get("status_str") == "error" or "execution_error" in kinds:
        err = next((m[1] for m in msgs if m and m[0] == "execution_error"), {})
        return HistoryResult("failed", outputs, msgs, {
            "type": err.get("exception_type", "execution_error"),
            "message": err.get("exception_message", "ComfyUI reported an execution error"),
            "node_id": err.get("node_id"), "node_type": err.get("node_type"),
            "traceback": err.get("traceback"),
        }, secs)
    return HistoryResult("running", outputs, msgs)


def output_images(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten history outputs into image file descriptors (incl. node id)."""
    out = []
    for node_id, node_out in outputs.items():
        for img in node_out.get("images", []) or []:
            if isinstance(img, dict) and "filename" in img:
                out.append({"node_id": str(node_id), "filename": img["filename"],
                            "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")})
    return out


class ComfyClient:
    def __init__(self, base_url: str, timeout: float = 30.0, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout, transport=transport)
        self._object_info: tuple[float, dict[str, Any]] | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def ws_url(self) -> str:
        return ("wss://" if self.base_url.startswith("https") else "ws://") + self.base_url.split("://", 1)[1] + "/ws"

    async def _req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            r = await self._client.request(method, path, **kw)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            raise ComfyUnavailable(f"ComfyUI not reachable at {self.base_url}: {exc.__class__.__name__}") from exc
        if r.status_code >= 400:
            try:
                payload = r.json()
            except ValueError:
                payload = r.text[:2000]
            raise ComfyError(f"ComfyUI {method} {path} returned {r.status_code}", r.status_code, payload)
        return r

    async def system_stats(self) -> dict[str, Any]:
        return (await self._req("GET", "/system_stats")).json()

    async def object_info(self, refresh: bool = False, ttl: float = 60.0) -> dict[str, Any]:
        now = time.monotonic()
        if not refresh and self._object_info and now - self._object_info[0] < ttl:
            return self._object_info[1]
        data = (await self._req("GET", "/object_info")).json()
        self._object_info = (now, data)
        return data

    async def queue(self) -> dict[str, Any]:
        return (await self._req("GET", "/queue")).json()

    async def history(self, prompt_id: str) -> dict[str, Any] | None:
        data = (await self._req("GET", f"/history/{prompt_id}")).json()
        return data.get(prompt_id)

    async def submit(self, prompt: dict[str, Any], client_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        body = {"prompt": prompt, "client_id": client_id, "extra_data": {"creative_studio": extra or {}}}
        return (await self._req("POST", "/prompt", json=body)).json()

    async def interrupt(self, prompt_id: str | None = None) -> None:
        # Newer ComfyUI accepts {"prompt_id"} to only interrupt that prompt; older ignore the body.
        await self._req("POST", "/interrupt", json={"prompt_id": prompt_id} if prompt_id else {})

    async def delete_from_queue(self, prompt_id: str) -> None:
        await self._req("POST", "/queue", json={"delete": [prompt_id]})

    async def view(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        r = await self._req("GET", "/view", params={"filename": filename, "subfolder": subfolder, "type": type_})
        return r.content

    async def upload_image(self, data: bytes, filename: str, subfolder: str, mime: str = "image/png") -> dict[str, Any]:
        files = {"image": (filename, data, mime)}
        form = {"subfolder": subfolder, "type": "input", "overwrite": "true"}
        return (await self._req("POST", "/upload/image", files=files, data=form)).json()

    async def model_metadata(self, folder: str, filename: str) -> dict[str, Any] | None:
        """safetensors header metadata (may contain a ``modelspec.hash_sha256``)."""
        try:
            r = await self._req("GET", f"/view_metadata/{folder}", params={"filename": filename})
        except ComfyError:
            return None
        try:
            return r.json()
        except (ValueError, json.JSONDecodeError):
            return None

    async def queue_position(self, prompt_id: str) -> tuple[str, int | None]:
        """Return ("running"|"pending"|"absent", position)."""
        q = await self.queue()
        for item in q.get("queue_running", []):
            if len(item) > 1 and item[1] == prompt_id:
                return "running", 0
        pending = sorted(q.get("queue_pending", []), key=lambda i: i[0])
        for pos, item in enumerate(pending):
            if len(item) > 1 and item[1] == prompt_id:
                return "pending", pos + 1
        return "absent", None
