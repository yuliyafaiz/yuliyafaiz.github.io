"""Pure-Python logic shared by the nodes (no torch / ComfyUI imports).

Keeping this separate makes the behaviour unit-testable without a ComfyUI
installation and keeps the node classes thin.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from typing import Any

SCHEMA = "creative-studio/node-metadata@1"


class NodeInputError(ValueError):
    """Raised for invalid node inputs; ComfyUI shows the message in the UI."""


# --- key/value parsing -------------------------------------------------------------


def parse_variables(text: str) -> dict[str, str]:
    """Parse ``key: value`` / ``key=value`` lines, or a JSON object.

    Blank lines and ``#`` comments are ignored. Keys may contain dots.
    """
    text = (text or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise NodeInputError(f"variables: invalid JSON ({exc.msg} at line {exc.lineno})") from exc
        if not isinstance(data, dict):
            raise NodeInputError("variables: JSON must be an object")
        return {str(k): v if isinstance(v, str) else json.dumps(v) for k, v in data.items()}
    out: dict[str, str] = {}
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w.\-]*)\s*[:=]\s*(.*)$", line)
        if not m:
            raise NodeInputError(f"variables line {n}: expected 'key: value', got {line!r}")
        out[m.group(1)] = m.group(2).strip()
    return out


# --- prompt templates -------------------------------------------------------------------

_VAR = re.compile(r"\{\s*([A-Za-z_][\w.\-]*)\s*(?:\|\s*([^{}]*?))?\s*\}")


def flatten(prefix: str, data: Any, out: dict[str, str]) -> None:
    if isinstance(data, dict):
        for k, v in data.items():
            flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(data, list):
        out[prefix] = ", ".join(str(x) for x in data if x not in (None, ""))
    elif data is not None:
        out[prefix] = str(data)


def render_template(template: str, variables: dict[str, str], strict: bool = True) -> tuple[str, dict[str, Any]]:
    """Render ``{name}`` / ``{name|default}`` placeholders.

    Literal braces are written as ``{{`` and ``}}``. In strict mode a missing
    variable without default raises; otherwise it renders as an empty string and
    is reported in the returned info.
    """
    used, missing = [], []
    sentinel_l, sentinel_r = "\x00L\x00", "\x00R\x00"
    t = (template or "").replace("{{", sentinel_l).replace("}}", sentinel_r)

    def sub(m: re.Match[str]) -> str:
        name, default = m.group(1), m.group(2)
        if name in variables and variables[name] != "":
            used.append(name)
            return variables[name]
        if default is not None:
            used.append(name)
            return default
        missing.append(name)
        return ""

    out = _VAR.sub(sub, t)
    if missing and strict:
        raise NodeInputError(f"template variables without value: {', '.join(sorted(set(missing)))}")
    out = re.sub(r"\s+,", ",", re.sub(r"(,\s*){2,}", ", ", out))  # tidy empty slots
    out = re.sub(r"[ \t]{2,}", " ", out).strip().strip(",").strip()
    out = out.replace(sentinel_l, "{").replace(sentinel_r, "}")
    return out, {"used": sorted(set(used)), "missing": sorted(set(missing))}


# --- profiles ---------------------------------------------------------------------------


def parse_profile(profile_json: str, expected_kind: str | None = None) -> dict[str, Any]:
    if not (profile_json or "").strip():
        raise NodeInputError("profile_json is empty — export a profile from Creative Studio or paste its JSON")
    try:
        p = json.loads(profile_json)
    except json.JSONDecodeError as exc:
        raise NodeInputError(f"profile_json: invalid JSON ({exc.msg})") from exc
    if not isinstance(p, dict) or "name" not in p:
        raise NodeInputError("profile_json must be an object with at least a 'name'")
    if expected_kind and p.get("kind") and p["kind"] != expected_kind:
        raise NodeInputError(f"expected a {expected_kind} profile, got {p['kind']!r}")
    p.setdefault("kind", expected_kind)
    p.setdefault("attributes", {})
    p.setdefault("preserve_details", [])
    p.setdefault("image_files", {})
    return p


def profile_fragment(p: dict[str, Any]) -> dict[str, str]:
    """Same algorithm as backend ``routers/profiles.prompt_fragment``."""
    parts: list[str] = []
    if p.get("description"):
        parts.append(p["description"].strip().rstrip("."))
    attrs = p.get("attributes") or {}
    for k in sorted(attrs):
        v = attrs[k]
        if v not in (None, "", []):
            v = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
            parts.append(f"{k.replace('_', ' ')}: {v}")
    preserve = [d.strip() for d in p.get("preserve_details") or [] if d.strip()]
    if preserve:
        parts.append("preserve exactly: " + "; ".join(preserve))
    negative = ""
    if p.get("kind") == "product":
        negative = "deformed product, altered design, extra stones, missing stones, warped metal, wrong proportions"
    elif p.get("kind") == "character":
        negative = "different person, inconsistent face, altered facial features"
    return {"positive": ", ".join(parts), "negative": negative}


def profile_variables(p: dict[str, Any], prefix: str = "profile") -> dict[str, str]:
    out: dict[str, str] = {}
    flatten(prefix, {k: v for k, v in p.items() if k not in ("image_files", "images")}, out)
    frag = profile_fragment(p)
    out[f"{prefix}.fragment"] = frag["positive"]
    out[f"{prefix}.negative"] = frag["negative"]
    return out


def profile_image_files(p: dict[str, Any], roles: list[str]) -> list[str]:
    files = p.get("image_files") or {}
    out: list[str] = []
    for r in roles:
        v = files.get(r) or []
        out.extend([v] if isinstance(v, str) else v)
    return out


def safe_input_path(input_dir: str, rel: str) -> str:
    """Resolve ``rel`` inside ComfyUI's input dir, refusing path traversal."""
    base = os.path.abspath(input_dir)
    path = os.path.abspath(os.path.join(base, rel))
    if os.path.commonpath([base, path]) != base:
        raise NodeInputError(f"image path escapes the input directory: {rel!r}")
    if not os.path.isfile(path):
        raise NodeInputError(f"profile image not found in ComfyUI input dir: {rel!r} "
                             "(Creative Studio uploads it on submission; when using the node manually, "
                             "put the file under ComfyUI/input)")
    return path


# --- batch variants ----------------------------------------------------------------------


def parse_variants(text: str) -> list[dict[str, str]]:
    """Variants as JSON list or one per line: ``label | text`` (label optional)."""
    text = (text or "").strip()
    if not text:
        return [{"label": "base", "text": ""}]
    if text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise NodeInputError(f"variants: invalid JSON ({exc.msg})") from exc
        out = []
        for i, v in enumerate(data):
            if isinstance(v, str):
                out.append({"label": f"v{i + 1}", "text": v})
            elif isinstance(v, dict):
                out.append({"label": str(v.get("label", f"v{i + 1}")), "text": str(v.get("text", "")),
                            **{k: str(x) for k, x in v.items() if k not in ("label", "text")}})
            else:
                raise NodeInputError("variants JSON entries must be strings or objects")
        return out or [{"label": "base", "text": ""}]
    out = []
    for i, line in enumerate(l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")):
        label, sep, body = line.partition("|")
        out.append({"label": label.strip(), "text": body.strip()} if sep else
                   {"label": f"v{i + 1}", "text": line.strip()})
    return out


def variant_seed(base_seed: int, index: int, label: str, strategy: str) -> int:
    if strategy == "increment":
        return (base_seed + index) % (2**64)
    if strategy == "fixed":
        return base_seed
    if strategy == "hash":
        h = hashlib.sha256(f"{base_seed}:{label}".encode()).digest()
        return int.from_bytes(h[:6], "big")
    raise NodeInputError(f"unknown seed strategy {strategy!r}")


def select_variant(variants: list[dict[str, str]], index: int, base_seed: int, strategy: str) -> dict[str, Any]:
    if index < 0:
        raise NodeInputError("variant_index must be >= 0")
    v = dict(variants[index % len(variants)])
    v["index"] = index
    v["count"] = len(variants)
    v["wrapped"] = index >= len(variants)
    v["seed"] = variant_seed(base_seed, index, v["label"], strategy)
    v["strategy"] = strategy
    return v


# --- project metadata ------------------------------------------------------------------------


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").lower()
    return s[:48] or "untitled"


def project_record(project_id: str, project_name: str, campaign: str, job_id: str, tags: str) -> dict[str, Any]:
    return {"project_id": project_id.strip(), "project_name": project_name.strip(),
            "campaign": campaign.strip(), "job_id": job_id.strip(),
            "tags": [t.strip() for t in (tags or "").split(",") if t.strip()]}


def filename_prefix(rec: dict[str, Any]) -> str:
    parts = ["creative_studio", slug(rec["project_name"] or rec["project_id"] or "project")]
    if rec.get("campaign"):
        parts.append(slug(rec["campaign"]))
    leaf = f"job{rec['job_id']}" if rec.get("job_id") else "img"
    return "/".join(parts) + "/" + leaf


# --- model hashing -------------------------------------------------------------------------------

MODEL_INPUT_FOLDERS = {
    "ckpt_name": "checkpoints", "lora_name": "loras", "vae_name": "vae",
    "control_net_name": "controlnet", "unet_name": "diffusion_models", "clip_name": "text_encoders",
    "clip_name1": "text_encoders", "clip_name2": "text_encoders", "ipadapter_file": "ipadapter",
    "clip_vision": "clip_vision", "style_model_name": "style_models",
}


class HashCache:
    """SHA-256 of model files, cached by (path, size, mtime) in a JSON file."""

    _lock = threading.Lock()

    def __init__(self, cache_file: str):
        self.cache_file = cache_file
        try:
            with open(cache_file) as f:
                self.data: dict[str, Any] = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def sha256(self, path: str) -> str:
        st = os.stat(path)
        key = f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}"
        with self._lock:
            if key in self.data:
                return self.data[key]
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                h.update(chunk)
        digest = h.hexdigest()
        with self._lock:
            self.data[key] = digest
            tmp = self.cache_file + ".tmp"
            try:
                os.makedirs(os.path.dirname(self.cache_file) or ".", exist_ok=True)
                with open(tmp, "w") as f:
                    json.dump(self.data, f)
                os.replace(tmp, self.cache_file)
            except OSError:
                pass
        return digest


def model_refs(prompt: dict[str, Any] | None) -> list[tuple[str, str, str]]:
    """(input_name, folder, filename) for literal model inputs in an API prompt."""
    out = []
    for node in (prompt or {}).values():
        for k, v in (node.get("inputs") or {}).items():
            if k in MODEL_INPUT_FOLDERS and isinstance(v, str):
                out.append((k, MODEL_INPUT_FOLDERS[k], v))
    return out


def sampler_summary(prompt: dict[str, Any] | None) -> list[dict[str, Any]]:
    out = []
    for nid, node in (prompt or {}).items():
        if node.get("class_type") in ("KSampler", "KSamplerAdvanced", "SamplerCustom"):
            i = node.get("inputs", {})
            lit = lambda k: None if isinstance(i.get(k), list) else i.get(k)  # noqa: E731
            out.append({"node_id": nid, "class_type": node["class_type"],
                        "seed": lit("seed") if "seed" in i else lit("noise_seed"), "steps": lit("steps"),
                        "cfg": lit("cfg"), "sampler": lit("sampler_name"), "scheduler": lit("scheduler"),
                        "denoise": lit("denoise")})
    return out


def metadata_record(*, prompt: dict[str, Any] | None, project: dict[str, Any] | None,
                    profile: dict[str, Any] | None, variant: dict[str, Any] | None,
                    references: dict[str, Any] | None, positive: str | None, negative: str | None,
                    seed: int | None, notes: str, model_hashes: dict[str, str], images: list[dict[str, Any]],
                    node_id: str | None) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "node_id": node_id,
        "project": project,
        "profile": {k: profile.get(k) for k in ("id", "kind", "name", "category")} if profile else None,
        "variant": variant,
        "references": references,
        "prompt": positive,
        "negative_prompt": negative,
        "seed": seed,
        "samplers": sampler_summary(prompt),
        "model_hashes": model_hashes,
        "notes": notes or None,
        "images": images,
    }
