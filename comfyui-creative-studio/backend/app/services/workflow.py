"""ComfyUI workflow analysis.

ComfyUI has two JSON formats that are NOT interchangeable:

* **UI / graph format** (what "Save" produces): ``{"nodes": [...], "links": [...], ...}``.
  Contains layout, widget values by position, virtual nodes (Reroute, Primitive,
  Note), muted/bypassed nodes and possibly subgraphs. ComfyUI's ``/prompt``
  endpoint cannot execute it.
* **API format** (what "Export (API)" produces): ``{"<node_id>": {"class_type": ...,
  "inputs": {...}}}``. This is what ``/prompt`` executes. Links are ``[node_id, slot]``.

This module detects the format, extracts dependencies, discovers editable
parameters, converts UI -> API on a best-effort basis (requires ``/object_info``),
builds executable prompts from parameter values, and extracts reproducibility
metadata from an executed prompt.
"""
from __future__ import annotations

import copy
import random
import re
from collections import deque
from typing import Any

MODEL_EXTENSIONS = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".sft", ".onnx")

# Inputs whose literal value names a model file, mapped to a model "kind".
MODEL_INPUTS: dict[str, str] = {
    "ckpt_name": "checkpoint",
    "unet_name": "diffusion_model",
    "vae_name": "vae",
    "lora_name": "lora",
    "control_net_name": "controlnet",
    "clip_name": "text_encoder",
    "clip_name1": "text_encoder",
    "clip_name2": "text_encoder",
    "clip_name3": "text_encoder",
    "ipadapter_file": "ipadapter",
    "clip_vision": "clip_vision",
    "model_name": "upscale_or_other",
    "style_model_name": "style_model",
}

SAMPLER_CLASSES = {"KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"}
SEED_INPUTS = {"seed", "noise_seed"}
VIRTUAL_UI_NODES = {"Note", "MarkdownNote", "Reroute", "PrimitiveNode"}
SEED_CONTROL_VALUES = {"fixed", "increment", "decrement", "randomize"}
TEXT_ENCODERS = {"CLIPTextEncode", "CLIPTextEncodeSDXL", "CLIPTextEncodeFlux"}
IMAGE_LOADERS = {"LoadImage", "LoadImageMask"}

# Consistency-method detection by node class name (prefix or exact).
METHOD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("faceid", re.compile(r"FaceID|InstantID|PuLID", re.I)),
    ("ipadapter", re.compile(r"^IPAdapter", re.I)),
    ("controlnet", re.compile(r"ControlNet", re.I)),
    ("openpose", re.compile(r"OpenPose|DWPose", re.I)),
    ("inpaint", re.compile(r"Inpaint|SetLatentNoiseMask|ImageCompositeMasked", re.I)),
    ("style_model", re.compile(r"StyleModel|Redux", re.I)),
    ("reference_profile", re.compile(r"^CS_(Product|Character)ProfileLoader$")),
]


class WorkflowFormatError(ValueError):
    pass


# --- format detection -------------------------------------------------------------


def unwrap(data: Any) -> Any:
    """Accept a ``{"prompt": {...}}`` wrapper (body of a /prompt request)."""
    if isinstance(data, dict) and "prompt" in data and isinstance(data["prompt"], dict):
        inner = data["prompt"]
        if inner and all(isinstance(v, dict) and "class_type" in v for v in inner.values()):
            return inner
    return data


def detect_format(data: Any) -> str:
    data = unwrap(data)
    if not isinstance(data, dict) or not data:
        raise WorkflowFormatError("workflow JSON must be a non-empty object")
    if isinstance(data.get("nodes"), list) and "links" in data:
        return "ui"
    if all(isinstance(v, dict) and "class_type" in v and "inputs" in v for v in data.values()):
        return "api"
    raise WorkflowFormatError(
        "unrecognised JSON: expected a ComfyUI UI workflow (nodes/links) "
        "or an API-format prompt ({node_id: {class_type, inputs}})"
    )


def is_link(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    )


# --- dependencies -----------------------------------------------------------------


def api_node_types(api: dict[str, Any]) -> list[str]:
    return sorted({n["class_type"] for n in api.values()})


def ui_node_types(ui: dict[str, Any]) -> list[str]:
    return sorted({n.get("type", "?") for n in ui.get("nodes", []) if n.get("type") not in VIRTUAL_UI_NODES})


def _looks_like_model(value: Any) -> bool:
    return isinstance(value, str) and value.lower().endswith(MODEL_EXTENSIONS)


def api_models(api: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for nid, node in api.items():
        for k, v in node.get("inputs", {}).items():
            if is_link(v):
                continue
            if k in MODEL_INPUTS and isinstance(v, str) or _looks_like_model(v):
                out.append(
                    {"node_id": str(nid), "class_type": node["class_type"], "input": k,
                     "name": v, "kind": MODEL_INPUTS.get(k, "model")}
                )
    return out


def ui_models(ui: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for n in ui.get("nodes", []):
        vals = n.get("widgets_values")
        vals = vals.values() if isinstance(vals, dict) else (vals or [])
        for v in vals:
            if _looks_like_model(v):
                out.append({"node_id": str(n.get("id")), "class_type": n.get("type"), "input": "",
                            "name": v, "kind": "model"})
    # Newer frontends also embed a "models" list with download URLs per node.
    return out


def detect_methods(node_types: list[str]) -> list[str]:
    found = []
    for method, pat in METHOD_PATTERNS:
        if any(pat.search(t) for t in node_types):
            found.append(method)
    if "VAEEncode" in node_types and "EmptyLatentImage" not in node_types and "inpaint" not in found:
        found.append("img2img")
    return found


def _combo_options(spec: Any) -> list[Any] | None:
    """Return combo choices for an /object_info input spec, if it is a combo."""
    if not isinstance(spec, list) or not spec:
        return None
    if isinstance(spec[0], list):
        return spec[0]
    if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
        return spec[1].get("options")
    return None


def _input_spec(info: dict[str, Any], name: str) -> Any:
    inp = info.get("input", {})
    return inp.get("required", {}).get(name) or inp.get("optional", {}).get(name)


def check_dependencies(api: dict[str, Any] | None, node_types: list[str],
                       object_info: dict[str, Any] | None) -> dict[str, Any]:
    """Compare a workflow with the connected ComfyUI's /object_info.

    Missing models are detected precisely: a loader input is a combo whose
    options are the files ComfyUI can see, so a value outside that list is
    missing on this server.
    """
    if object_info is None:
        return {"checked": False, "missing_nodes": [], "missing_models": [], "invalid_values": []}
    missing_nodes = sorted({t for t in node_types if t not in object_info})
    missing_models, invalid = [], []
    for nid, node in (api or {}).items():
        info = object_info.get(node["class_type"])
        if not info:
            continue
        for k, v in node.get("inputs", {}).items():
            if is_link(v):
                continue
            opts = _combo_options(_input_spec(info, k))
            if opts is None or v in opts:
                continue
            entry = {"node_id": str(nid), "class_type": node["class_type"], "input": k, "value": v}
            if k in MODEL_INPUTS or _looks_like_model(v):
                missing_models.append(entry)
            elif k not in ("image",):  # input images are uploaded at submission time
                invalid.append(entry)
    return {"checked": True, "missing_nodes": missing_nodes,
            "missing_models": missing_models, "invalid_values": invalid}


# --- graph helpers ----------------------------------------------------------------


def upstream(api: dict[str, Any], start: Any) -> set[str]:
    """All node ids reachable upstream from a link value ``[node_id, slot]``."""
    seen: set[str] = set()
    if not is_link(start):
        return seen
    q = deque([str(start[0])])
    while q:
        nid = q.popleft()
        if nid in seen or nid not in api:
            continue
        seen.add(nid)
        for v in api[nid].get("inputs", {}).values():
            if is_link(v):
                q.append(str(v[0]))
    return seen


def trace_conditioning(api: dict[str, Any], link: Any, depth: int = 0) -> list[str]:
    """Text-encoder node ids feeding a conditioning link, slot-aware.

    Nodes that carry both conditionings (InpaintModelConditioning,
    ControlNetApplyAdvanced, ...) output positive on slot 0 and negative on
    slot 1; only the matching branch is followed.
    """
    if not is_link(link) or depth > 64:
        return []
    nid, slot = str(link[0]), link[1]
    node = api.get(nid)
    if node is None:
        return []
    if node["class_type"] in TEXT_ENCODERS:
        return [nid]
    inputs = node.get("inputs", {})
    if "positive" in inputs and "negative" in inputs:
        return trace_conditioning(api, inputs["positive" if slot == 0 else "negative"], depth + 1)
    out: list[str] = []
    for k, v in inputs.items():
        if is_link(v) and ("conditioning" in k or k in ("positive", "negative", "cond")):
            out.extend(trace_conditioning(api, v, depth + 1))
    return out


def prompt_roles(api: dict[str, Any]) -> dict[str, str]:
    """Map text-encoder node id -> "positive" | "negative" by tracing sampler inputs."""
    roles: dict[str, str] = {}
    for node in api.values():
        if node["class_type"] not in SAMPLER_CLASSES and node["class_type"] != "CFGGuider":
            continue
        for role in ("positive", "negative"):
            for nid in trace_conditioning(api, node.get("inputs", {}).get(role)):
                roles.setdefault(nid, role)
    return roles


def _title(node: dict[str, Any], nid: str) -> str:
    return (node.get("_meta") or {}).get("title") or f"{node['class_type']} #{nid}"


# --- parameter discovery -----------------------------------------------------------

_PARAM_RULES: dict[str, list[tuple[str, str, str]]] = {
    # class_type: [(input, type, group)]
    "KSampler": [("seed", "seed", "sampling"), ("steps", "int", "sampling"), ("cfg", "float", "sampling"),
                 ("sampler_name", "choice", "sampling"), ("scheduler", "choice", "sampling"),
                 ("denoise", "float", "sampling")],
    "KSamplerAdvanced": [("noise_seed", "seed", "sampling"), ("steps", "int", "sampling"),
                         ("cfg", "float", "sampling"), ("sampler_name", "choice", "sampling"),
                         ("scheduler", "choice", "sampling")],
    "RandomNoise": [("noise_seed", "seed", "sampling")],
    "EmptyLatentImage": [("width", "int", "size"), ("height", "int", "size"), ("batch_size", "int", "size")],
    "EmptySD3LatentImage": [("width", "int", "size"), ("height", "int", "size"), ("batch_size", "int", "size")],
    "CheckpointLoaderSimple": [("ckpt_name", "choice", "models")],
    "LoraLoader": [("lora_name", "choice", "models"), ("strength_model", "float", "models"),
                   ("strength_clip", "float", "models")],
    "ControlNetApplyAdvanced": [("strength", "float", "conditioning"), ("start_percent", "float", "conditioning"),
                                ("end_percent", "float", "conditioning")],
    "ControlNetApply": [("strength", "float", "conditioning")],
    "IPAdapterAdvanced": [("weight", "float", "conditioning"), ("weight_type", "choice", "conditioning"),
                          ("start_at", "float", "conditioning"), ("end_at", "float", "conditioning")],
    "IPAdapter": [("weight", "float", "conditioning"), ("start_at", "float", "conditioning"),
                  ("end_at", "float", "conditioning")],
    "IPAdapterFaceID": [("weight", "float", "conditioning"), ("weight_faceidv2", "float", "conditioning")],
    "IPAdapterUnifiedLoader": [("preset", "choice", "models")],
    "ImageScaleToTotalPixels": [("megapixels", "float", "size")],
    "GrowMask": [("expand", "int", "conditioning")],
    "CS_PromptTemplate": [("template", "text", "prompt"), ("variables", "text", "prompt")],
    "CS_ProjectMetadata": [("project_id", "text", "metadata"), ("project_name", "text", "metadata"),
                           ("campaign", "text", "metadata"), ("job_id", "text", "metadata")],
    "CS_ProductProfileLoader": [("profile_json", "text", "profile")],
    "CS_CharacterProfileLoader": [("profile_json", "text", "profile")],
    "CS_BatchVariantManager": [("base_seed", "seed", "sampling"), ("variant_index", "int", "sampling"),
                               ("variants", "text", "prompt")],
}


def _enrich(param: dict[str, Any], object_info: dict[str, Any] | None, class_type: str) -> None:
    if not object_info or class_type not in object_info:
        return
    spec = _input_spec(object_info[class_type], param["input"])
    opts = _combo_options(spec)
    if opts is not None:
        param["choices"] = opts
        if param["type"] not in ("image",):
            param["type"] = "choice"
    elif isinstance(spec, list) and len(spec) > 1 and isinstance(spec[1], dict):
        for k in ("min", "max", "step"):
            if k in spec[1]:
                param[k] = spec[1][k]


def discover_parameters(api: dict[str, Any], object_info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    roles = prompt_roles(api)
    params: list[dict[str, Any]] = []

    def add(nid: str, node: dict[str, Any], inp: str, typ: str, group: str, label: str | None = None) -> None:
        v = node["inputs"].get(inp)
        if inp not in node["inputs"] or is_link(v):
            return
        p = {"key": f"{nid}.{inp}", "node_id": nid, "input": inp, "class_type": node["class_type"],
             "label": label or f"{_title(node, nid)} · {inp}", "type": typ, "group": group, "default": v}
        _enrich(p, object_info, node["class_type"])
        params.append(p)

    for nid, node in sorted(api.items(), key=lambda kv: _sort_key(kv[0])):
        ct = node["class_type"]
        if ct in TEXT_ENCODERS:
            role = roles.get(nid)
            label = {"positive": "Positive prompt", "negative": "Negative prompt"}.get(role or "", _title(node, nid))
            for inp in ("text", "text_g", "text_l", "clip_l", "t5xxl"):
                add(nid, node, inp, "text", "prompt", label if inp == "text" else f"{label} · {inp}")
            if params and params[-1]["node_id"] == nid:
                params[-1]["role"] = role
        elif ct in IMAGE_LOADERS:
            add(nid, node, "image", "image", "references", f"{_title(node, nid)}")
        elif ct in _PARAM_RULES:
            for inp, typ, group in _PARAM_RULES[ct]:
                add(nid, node, inp, typ, group)
    return params


def literal_inputs(api: dict[str, Any]) -> list[dict[str, Any]]:
    """All literal (non-link) inputs; candidates for manually exposed parameters."""
    out = []
    for nid, node in api.items():
        for k, v in node.get("inputs", {}).items():
            if not is_link(v):
                out.append({"key": f"{nid}.{k}", "node_id": str(nid), "input": k,
                            "class_type": node["class_type"], "value": v})
    return out


def _sort_key(nid: str) -> tuple[int, str]:
    return (int(nid), "") if str(nid).isdigit() else (10**9, str(nid))


# --- prompt building ------------------------------------------------------------------


class PromptBuildError(ValueError):
    pass


def _coerce(value: Any, typ: str) -> Any:
    try:
        if typ in ("int", "seed"):
            return int(value)
        if typ == "float":
            return float(value)
        if typ == "bool":
            return bool(value)
    except (TypeError, ValueError) as exc:
        raise PromptBuildError(f"cannot convert {value!r} to {typ}") from exc
    return value


def build_prompt(api: dict[str, Any], parameters: list[dict[str, Any]], values: dict[str, Any],
                 image_files: dict[str, str] | None = None, overrides: dict[str, Any] | None = None
                 ) -> dict[str, Any]:
    """Return a new API prompt with parameter values applied.

    ``values`` are keyed by parameter key (``"<node_id>.<input>"``). ``image_files``
    maps image-parameter keys to filenames already uploaded to ComfyUI's input dir.
    ``overrides`` may target any literal input by key (advanced use).
    """
    prompt = copy.deepcopy(api)
    types = {p["key"]: p.get("type", "text") for p in parameters}
    merged: dict[str, Any] = {}
    merged.update(overrides or {})
    merged.update({k: v for k, v in values.items() if v is not None and v != ""})
    merged.update(image_files or {})
    for key, value in merged.items():
        nid, _, inp = key.partition(".")
        if nid not in prompt or not inp:
            raise PromptBuildError(f"parameter {key!r} does not match a node in this workflow")
        if is_link(prompt[nid]["inputs"].get(inp)):
            raise PromptBuildError(f"input {key!r} is connected to another node and cannot be set")
        prompt[nid]["inputs"][inp] = _coerce(value, types.get(key, "text"))
    return prompt


def randomize_seeds(prompt: dict[str, Any], rng: random.Random | None = None) -> dict[str, int]:
    rng = rng or random.Random()
    out = {}
    for nid, node in prompt.items():
        for k in SEED_INPUTS:
            if k in node["inputs"] and not is_link(node["inputs"][k]):
                node["inputs"][k] = rng.randint(0, 2**48)
                out[f"{nid}.{k}"] = node["inputs"][k]
    return out


def seed_keys(prompt: dict[str, Any]) -> list[str]:
    return [f"{nid}.{k}" for nid, n in prompt.items() for k in SEED_INPUTS
            if k in n["inputs"] and not is_link(n["inputs"][k])]


# --- reproducibility metadata --------------------------------------------------------


def _texts(api: dict[str, Any], link: Any) -> list[dict[str, Any]]:
    out = []
    for nid in trace_conditioning(api, link):
        node = api[nid]
        if True:
            for k in ("text", "text_g", "text_l", "clip_l", "t5xxl"):
                v = node["inputs"].get(k)
                if v is None:
                    continue
                out.append({"node_id": nid, "input": k,
                            "text": v if not is_link(v) else None,
                            "dynamic_from": None if not is_link(v) else str(v[0])})
    return out


def extract_generation_metadata(api: dict[str, Any]) -> dict[str, Any]:
    """Extract human-readable reproducibility metadata from an API prompt.

    The full prompt is stored separately; this is a convenience summary.
    Dynamic values (e.g. a prompt produced by another node) are recorded as
    ``dynamic_from`` node ids rather than guessed.
    """
    samplers = []
    for nid, node in sorted(api.items(), key=lambda kv: _sort_key(kv[0])):
        ct, inp = node["class_type"], node["inputs"]
        if ct not in SAMPLER_CLASSES:
            continue
        lit = lambda k: None if is_link(inp.get(k)) else inp.get(k)  # noqa: E731
        s: dict[str, Any] = {
            "node_id": nid, "class_type": ct,
            "seed": lit("seed") if "seed" in inp else lit("noise_seed"),
            "steps": lit("steps"), "cfg": lit("cfg"), "sampler": lit("sampler_name"),
            "scheduler": lit("scheduler"), "denoise": lit("denoise"),
        }
        if "seed" in inp and is_link(inp["seed"]) or "noise_seed" in inp and is_link(inp.get("noise_seed")):
            s["seed_dynamic_from"] = str((inp.get("seed") or inp.get("noise_seed"))[0])
        s["positive"] = _texts(api, inp.get("positive"))
        s["negative"] = _texts(api, inp.get("negative"))
        samplers.append(s)

    dims = []
    for nid, node in api.items():
        i = node["inputs"]
        if "width" in i and "height" in i and not is_link(i["width"]) and not is_link(i["height"]):
            dims.append({"node_id": str(nid), "class_type": node["class_type"],
                         "width": i["width"], "height": i["height"], "batch_size": i.get("batch_size")})
    images = [{"node_id": str(nid), "image": n["inputs"].get("image")}
              for nid, n in api.items() if n["class_type"] in IMAGE_LOADERS]
    first = samplers[0] if samplers else {}
    pos = " ".join(t["text"] for t in first.get("positive", []) if t.get("text")) if first else ""
    neg = " ".join(t["text"] for t in first.get("negative", []) if t.get("text")) if first else ""
    return {
        "prompt": pos or None,
        "negative_prompt": neg or None,
        "seed": first.get("seed"),
        "sampler": first.get("sampler"),
        "scheduler": first.get("scheduler"),
        "steps": first.get("steps"),
        "cfg": first.get("cfg"),
        "denoise": first.get("denoise"),
        "dimensions": dims[0] if dims else None,
        "samplers": samplers,
        "models": api_models(api),
        "input_images": images,
        "node_types": api_node_types(api),
        "methods": detect_methods(api_node_types(api)),
    }


# --- UI -> API conversion -------------------------------------------------------------


def _ordered_inputs(info: dict[str, Any]) -> list[tuple[str, Any]]:
    inp = info.get("input", {})
    order = info.get("input_order")
    out = []
    for section in ("required", "optional"):
        specs = inp.get(section, {}) or {}
        names = (order or {}).get(section) or list(specs.keys())
        out.extend((n, specs[n]) for n in names if n in specs)
    return out


def _is_widget(spec: Any) -> bool:
    if not isinstance(spec, list) or not spec:
        return False
    opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if opts.get("forceInput") or opts.get("rawLink"):
        return False
    t = spec[0]
    return isinstance(t, list) or t in ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO")


def convert_ui_to_api(ui: dict[str, Any], object_info: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Best-effort UI -> API conversion. Returns (api_prompt, warnings).

    ComfyUI's own "Export (API)" is authoritative; this converter exists so that a
    saved workflow can still be used. Unsupported: subgraphs, nodes with dynamic
    widget layouts that differ from /object_info, frontend-only extensions
    (e.g. Set/Get nodes). ComfyUI validates the result again on submission.
    """
    warnings: list[str] = []
    if (ui.get("definitions") or {}).get("subgraphs"):
        raise WorkflowFormatError(
            "this workflow uses subgraphs; open it in ComfyUI and use Workflow → Export (API)")
    nodes = {n["id"]: n for n in ui.get("nodes", [])}
    links = {}
    for l in ui.get("links", []):
        if isinstance(l, list):
            links[l[0]] = {"origin": l[1], "slot": l[2], "target": l[3], "tslot": l[4], "type": l[5] if len(l) > 5 else "*"}
        elif isinstance(l, dict):
            links[l["id"]] = {"origin": l["origin_id"], "slot": l["origin_slot"], "target": l["target_id"],
                              "tslot": l["target_slot"], "type": l.get("type", "*")}

    # PrimitiveNode values pushed to their targets: (target_id, input_name) -> value
    primitive_values: dict[tuple[Any, str], Any] = {}
    for n in nodes.values():
        if n.get("type") == "PrimitiveNode" and n.get("widgets_values"):
            for lid in (n.get("outputs") or [{}])[0].get("links") or []:
                lk = links.get(lid)
                if lk:
                    tnode = nodes.get(lk["target"])
                    if tnode:
                        tin = (tnode.get("inputs") or [])[lk["tslot"]]
                        name = (tin.get("widget") or {}).get("name") or tin.get("name")
                        primitive_values[(lk["target"], name)] = n["widgets_values"][0]

    def resolve(link_id: Any, depth: int = 0) -> list[Any] | None:
        """Resolve a link to [origin_id, slot], walking through Reroute/bypassed nodes."""
        if depth > 64 or link_id is None or link_id not in links:
            return None
        lk = links[link_id]
        origin = nodes.get(lk["origin"])
        if origin is None:
            return None
        t, mode = origin.get("type"), origin.get("mode", 0)
        if t == "Reroute":
            ins = origin.get("inputs") or []
            return resolve(ins[0].get("link") if ins else None, depth + 1)
        if t == "PrimitiveNode":
            return None
        if mode == 4:  # bypassed: pass through first input of matching type
            out_type = (origin.get("outputs") or [])[lk["slot"]].get("type") if origin.get("outputs") else None
            for i in origin.get("inputs") or []:
                if i.get("link") is not None and (i.get("type") == out_type or out_type in (None, "*")):
                    return resolve(i["link"], depth + 1)
            return None
        if mode == 2:  # muted
            return None
        return [str(lk["origin"]), lk["slot"]]

    api: dict[str, Any] = {}
    for nid, n in nodes.items():
        t = n.get("type")
        if t in VIRTUAL_UI_NODES or n.get("mode", 0) in (2, 4):
            continue
        info = object_info.get(t)
        if info is None:
            warnings.append(f"node {nid} ({t}) is not installed on the connected ComfyUI; skipped")
            continue
        inputs: dict[str, Any] = {}
        ui_inputs = {i.get("name"): i for i in n.get("inputs") or []}
        wv = n.get("widgets_values")
        if isinstance(wv, dict):
            values_by_name, values = wv, []
        else:
            values_by_name, values = {}, list(wv or [])
        idx = 0
        for name, spec in _ordered_inputs(info):
            ui_in = ui_inputs.get(name)
            if _is_widget(spec):
                if values_by_name:
                    wval = values_by_name.get(name)
                elif idx < len(values):
                    wval = values[idx]
                    idx += 1
                    opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
                    if (opts.get("control_after_generate") or name in SEED_INPUTS) and idx < len(values) \
                            and values[idx] in SEED_CONTROL_VALUES:
                        idx += 1
                else:
                    wval = None
                if ui_in and ui_in.get("link") is not None:
                    r = resolve(ui_in["link"])
                    if r is not None:
                        inputs[name] = r
                        continue
                if (nid, name) in primitive_values:
                    inputs[name] = primitive_values[(nid, name)]
                elif wval is not None:
                    inputs[name] = wval
            elif ui_in and ui_in.get("link") is not None:
                r = resolve(ui_in["link"])
                if r is not None:
                    inputs[name] = r
                else:
                    warnings.append(f"node {nid} ({t}): input '{name}' comes from a muted/unsupported node")
        node_out: dict[str, Any] = {"class_type": t, "inputs": inputs}
        if n.get("title"):
            node_out["_meta"] = {"title": n["title"]}
        api[str(nid)] = node_out

    return api, warnings


# --- structural validation against /object_info -------------------------------------------


def _spec_type(spec: Any) -> str | None:
    if not isinstance(spec, list) or not spec:
        return None
    return "COMBO" if isinstance(spec[0], list) else str(spec[0])


def validate_structure(api: dict[str, Any], object_info: dict[str, Any]) -> list[dict[str, Any]]:
    """Find problems ComfyUI would reject, before submitting.

    Checks: unknown node classes, unknown input names, missing required inputs,
    links to missing nodes / out-of-range output slots, and link type mismatches.
    Values that depend on files (models, input images) are covered by
    :func:`check_dependencies`.
    """
    issues: list[dict[str, Any]] = []

    def add(nid: str, kind: str, msg: str) -> None:
        # Unknown inputs are ignored by ComfyUI (e.g. a newer workflow on an older server): warn only.
        severity = "warning" if kind == "unknown_input" else "error"
        issues.append({"node_id": nid, "class_type": api[nid]["class_type"], "kind": kind, "message": msg,
                       "severity": severity})

    for nid, node in api.items():
        info = object_info.get(node["class_type"])
        if info is None:
            add(nid, "unknown_node", f"node class {node['class_type']} is not installed")
            continue
        req = info.get("input", {}).get("required", {}) or {}
        opt = info.get("input", {}).get("optional", {}) or {}
        for name in req:
            if name not in node["inputs"]:
                add(nid, "missing_input", f"required input '{name}' is missing")
        for name, value in node["inputs"].items():
            spec = req.get(name) or opt.get(name)
            if spec is None:
                add(nid, "unknown_input", f"input '{name}' does not exist on {node['class_type']}")
                continue
            if not is_link(value):
                continue
            src_id, slot = str(value[0]), value[1]
            if src_id not in api:
                add(nid, "dangling_link", f"input '{name}' links to missing node {src_id}")
                continue
            src_info = object_info.get(api[src_id]["class_type"])
            if src_info is None:
                continue
            outs = src_info.get("output", [])
            if slot >= len(outs):
                add(nid, "bad_slot", f"input '{name}' uses output {slot} of node {src_id}, which has {len(outs)}")
                continue
            want, have = _spec_type(spec), outs[slot]
            have = "COMBO" if isinstance(have, list) else str(have)
            if want and have and want != "*" and have != "*" and want != have and \
                    not (want == "COMBO" and have in ("COMBO", "STRING")):
                wants = set(want.split(","))
                if have not in wants:
                    add(nid, "type_mismatch", f"input '{name}' expects {want} but node {src_id} outputs {have}")
    return issues
