"""ComfyUI node classes (classic ``INPUT_TYPES`` API, supported by all current ComfyUI versions).

Custom types passed between these nodes:
    CS_PROJECT    dict  project/campaign identifiers
    CS_PROFILE    dict  product or character profile
    CS_VARIANT    dict  selected batch variant (label, text, seed, index)
    CS_REFERENCES dict  manifest of collected reference images
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from . import core

CATEGORY = "Creative Studio"
MAX_REFS = 6


def _folder_paths():
    import folder_paths  # provided by ComfyUI at runtime

    return folder_paths


# --- 1. Reference Collector -----------------------------------------------------------------


class CS_ReferenceCollector:
    """Collect up to six reference images of *different* sizes into one batch + manifest.

    Core ``ImageBatch`` joins two images and rescales the second; this node accepts
    up to six (each may itself be a batch), keeps aspect ratio by padding or
    cropping, outputs a mask of padded areas and a labelled manifest that the
    metadata saver records with each output.
    """

    @classmethod
    def INPUT_TYPES(cls):
        optional = {f"image_{i}": ("IMAGE", {"tooltip": f"Reference image {i}"}) for i in range(1, MAX_REFS + 1)}
        return {
            "required": {
                "resize_mode": (["pad", "crop", "stretch"], {"default": "pad",
                                "tooltip": "How references of different sizes are brought to one size"}),
                "width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 8,
                                  "tooltip": "0 = width of the first image"}),
                "height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 8,
                                   "tooltip": "0 = height of the first image"}),
                "labels": ("STRING", {"default": "", "tooltip": "Comma-separated labels, one per connected input"}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE", "MASK", "CS_REFERENCES", "INT")
    RETURN_NAMES = ("images", "pad_mask", "references", "count")
    FUNCTION = "collect"
    CATEGORY = CATEGORY
    DESCRIPTION = "Batch differently sized reference images with labels and a manifest."

    def collect(self, resize_mode, width, height, labels="", **images):
        from . import imaging

        connected = [(k, images[k]) for k in sorted(images, key=lambda k: int(k.split("_")[1]))
                     if images.get(k) is not None]
        if not connected:
            raise core.NodeInputError("connect at least one image input")
        label_list = [l.strip() for l in labels.split(",")] if labels.strip() else []
        pil, manifest = [], []
        for n, (key, batch) in enumerate(connected):
            for b, im in enumerate(imaging.tensor_to_pil(batch)):
                manifest.append({"input": key, "batch_index": b, "label": label_list[n] if n < len(label_list) else key,
                                 "original_size": [im.width, im.height]})
                pil.append(im.convert("RGBA"))
        pil = imaging.common_batch(pil, resize_mode, width, height)
        image, mask = imaging.to_tensors(pil)
        refs = {"count": len(pil), "size": [pil[0].width, pil[0].height], "resize_mode": resize_mode,
                "items": manifest}
        return (image, mask, refs, len(pil))


# --- 2/3. Profile loaders ------------------------------------------------------------------------


class _ProfileLoaderBase:
    KIND = "product"
    ROLES_PRIMARY: list[str] = ["primary"]
    ROLES_SECONDARY: list[str] = ["detail"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "profile_json": ("STRING", {"multiline": True, "default": "",
                                            "tooltip": "Profile exported from Creative Studio (filled automatically "
                                                       "when the job is submitted from the app)"}),
                "max_side": ("INT", {"default": 1024, "min": 0, "max": 8192, "step": 8,
                                     "tooltip": "Downscale references so the longest side is at most this (0 = off)"}),
                "resize_mode": (["pad", "crop", "stretch"], {"default": "pad"}),
            }
        }

    CATEGORY = CATEGORY

    @classmethod
    def VALIDATE_INPUTS(cls, profile_json=None, **_):
        if profile_json is None:  # linked input: validated at execution time
            return True
        try:
            core.parse_profile(profile_json, cls.KIND)
        except core.NodeInputError as exc:
            return str(exc)
        return True

    @classmethod
    def IS_CHANGED(cls, profile_json, max_side, resize_mode):
        # Re-run when referenced files change on disk, not only when the JSON changes.
        h = hashlib.sha256(f"{profile_json}|{max_side}|{resize_mode}".encode())
        try:
            p = core.parse_profile(profile_json, cls.KIND)
            base = _folder_paths().get_input_directory()
            for rel in core.profile_image_files(p, cls.ROLES_PRIMARY + cls.ROLES_SECONDARY):
                path = os.path.join(base, rel)
                if os.path.isfile(path):
                    st = os.stat(path)
                    h.update(f"{rel}{st.st_size}{st.st_mtime}".encode())
        except core.NodeInputError:
            pass
        return h.hexdigest()

    def _load(self, p: dict[str, Any], roles: list[str], max_side: int, mode: str):
        from . import imaging

        base = _folder_paths().get_input_directory()
        files = core.profile_image_files(p, roles)
        ims = [imaging.limit_size(imaging.load_rgba(core.safe_input_path(base, f)), max_side) for f in files]
        if not ims:
            return None, None, files
        ims = imaging.common_batch(ims, mode, 0, 0)
        image, mask = imaging.to_tensors(ims)
        return image, mask, files

    def _primary_roles(self, p: dict[str, Any]) -> list[str]:
        return self.ROLES_PRIMARY

    def _run(self, profile_json, max_side, resize_mode):
        p = core.parse_profile(profile_json, self.KIND)
        primary = self._primary_roles(p)
        img1, mask1, files1 = self._load(p, primary, max_side, resize_mode)
        if img1 is None:
            raise core.NodeInputError(f"profile {p['name']!r} has no {'/'.join(primary)} images")
        img2, mask2, files2 = self._load(p, self.ROLES_SECONDARY, max_side, resize_mode)
        if img2 is None:  # fall back so downstream nodes always receive an image
            img2, mask2, files2 = img1, mask1, files1
        frag = core.profile_fragment(p)
        info = {k: p.get(k) for k in ("id", "kind", "name", "category", "description", "attributes",
                                      "preserve_details")}
        info["files"] = {"primary": files1, "secondary": files2}
        return p, img1, mask1, img2, frag, info


class CS_ProductProfileLoader(_ProfileLoaderBase):
    """Load a Product Profile: reference images, their alpha mask and prompt fragments.

    The mask follows ``LoadImage`` (1 = transparent), so for a product cut-out it
    marks the background to regenerate; invert it to protect the product.
    """

    KIND = "product"
    ROLES_PRIMARY = ["primary"]
    ROLES_SECONDARY = ["detail", "angle", "material"]
    RETURN_TYPES = ("IMAGE", "MASK", "IMAGE", "STRING", "STRING", "CS_PROFILE")
    RETURN_NAMES = ("product_images", "background_mask", "detail_images", "positive_fragment",
                    "negative_fragment", "profile")
    FUNCTION = "load"
    DESCRIPTION = "Product reference images + mask + deterministic prompt fragments from a Creative Studio profile."

    def load(self, profile_json, max_side, resize_mode):
        _p, img1, mask1, img2, frag, info = self._run(profile_json, max_side, resize_mode)
        return (img1, mask1, img2, frag["positive"], frag["negative"], info)


class CS_CharacterProfileLoader(_ProfileLoaderBase):
    """Load a Character Profile: face references, body/look references and prompt fragments."""

    KIND = "character"
    ROLES_PRIMARY = ["face"]
    ROLES_SECONDARY = ["primary", "angle", "detail", "other"]
    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING", "STRING", "CS_PROFILE")
    RETURN_NAMES = ("face_images", "reference_images", "positive_fragment", "negative_fragment", "profile")
    FUNCTION = "load"
    DESCRIPTION = "Character face/look references + prompt fragments from a Creative Studio profile."

    def _primary_roles(self, p: dict[str, Any]) -> list[str]:
        # A character profile without dedicated face images falls back to its primary images.
        return ["face"] if core.profile_image_files(p, ["face"]) else ["primary"]

    def load(self, profile_json, max_side, resize_mode):
        _p, img1, _m, img2, frag, info = self._run(profile_json, max_side, resize_mode)
        return (img1, img2, frag["positive"], frag["negative"], info)


# --- 4. Prompt Template Manager --------------------------------------------------------------------


class CS_PromptTemplate:
    """Render a reusable prompt template with ``{variables}`` and ``{var|default}``.

    Variables come from the text box and, optionally, from a profile
    (``{profile.name}``, ``{profile.attributes.material}``, ``{profile.fragment}``),
    a batch variant (``{variant.text}``, ``{variant.label}``) and a project
    (``{project.campaign}``). Strict mode fails fast on missing variables instead of
    silently sending an incomplete prompt.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "template": ("STRING", {"multiline": True,
                                        "default": "luxury product photograph of {profile.name}, {profile.fragment}, "
                                                   "{variant.text}, {lighting|soft studio light}"}),
                "variables": ("STRING", {"multiline": True, "default": "",
                                         "tooltip": "key: value per line, or a JSON object"}),
                "strict": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "profile": ("CS_PROFILE",),
                "variant": ("CS_VARIANT",),
                "project": ("CS_PROJECT",),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "resolution_json")
    FUNCTION = "render"
    CATEGORY = CATEGORY
    DESCRIPTION = "Reusable prompt templates with validated variables from profiles, variants and projects."

    def render(self, template, variables, strict, profile=None, variant=None, project=None):
        vars_: dict[str, str] = {}
        if profile:
            vars_.update(core.profile_variables(profile))
        if variant:
            core.flatten("variant", variant, vars_)
        if project:
            core.flatten("project", project, vars_)
        vars_.update(core.parse_variables(variables))
        text, info = core.render_template(template, vars_, strict=strict)
        return (text, json.dumps({"template": template, **info, "prompt": text}))


# --- 5. Generation Metadata Saver -------------------------------------------------------------------


class CS_GenerationMetadataSaver:
    """Save images as PNG with embedded workflow + a structured sidecar JSON.

    Beyond core ``SaveImage``: writes ``<file>.json`` with project/profile/variant/
    reference context, sampler settings, and SHA-256 hashes of every model file
    used (computed on the ComfyUI machine, cached by size+mtime). The record is also
    returned in the node's UI output (``cs_metadata``) so Creative Studio can store it.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "creative_studio/output"}),
                "hash_models": ("BOOLEAN", {"default": True,
                                            "tooltip": "SHA-256 model files (first run per model can take a while)"}),
                "notes": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {
                "project": ("CS_PROJECT",),
                "profile": ("CS_PROFILE",),
                "variant": ("CS_VARIANT",),
                "references": ("CS_REFERENCES",),
                "positive": ("STRING", {"forceInput": True}),
                "negative": ("STRING", {"forceInput": True}),
                "seed": ("INT", {"forceInput": True}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO", "unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ()
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY
    DESCRIPTION = "Save PNGs with embedded workflow plus a sidecar JSON of reproducibility metadata and model hashes."

    def _hashes(self, prompt) -> dict[str, str]:
        fp = _folder_paths()
        cache = core.HashCache(os.path.join(fp.get_user_directory() if hasattr(fp, "get_user_directory")
                                            else fp.get_output_directory(), "creative_studio_hash_cache.json"))
        out = {}
        for _inp, folder, name in core.model_refs(prompt):
            try:
                path = fp.get_full_path(folder, name)
            except Exception:  # noqa: BLE001 - unknown folder name on this ComfyUI version
                path = None
            if path and os.path.isfile(path):
                out[name] = cache.sha256(path)
        return out

    def save(self, images, filename_prefix, hash_models, notes, project=None, profile=None, variant=None,
             references=None, positive=None, negative=None, seed=None, prompt=None, extra_pnginfo=None,
             unique_id=None):
        from PIL.PngImagePlugin import PngInfo

        from . import imaging

        fp = _folder_paths()
        out_dir = fp.get_output_directory()
        full_folder, filename, counter, subfolder, _ = fp.get_save_image_path(
            filename_prefix, out_dir, images[0].shape[1], images[0].shape[0])
        hashes = self._hashes(prompt) if hash_models else {}
        try:
            from comfy.cli_args import args

            embed = not args.disable_metadata
        except Exception:  # noqa: BLE001
            embed = True
        results, files = [], []
        for b, pil in enumerate(imaging.tensor_to_pil(images)):
            name = f"{filename.replace('%batch_num%', str(b))}_{counter:05}_.png"
            files.append({"filename": name, "subfolder": subfolder, "type": "output", "batch_index": b})
            counter += 1
        record = core.metadata_record(prompt=prompt, project=project, profile=profile, variant=variant,
                                      references=references, positive=positive, negative=negative, seed=seed,
                                      notes=notes, model_hashes=hashes, images=files, node_id=unique_id)
        for f, pil in zip(files, imaging.tensor_to_pil(images)):
            info = None
            if embed:
                info = PngInfo()
                if prompt is not None:
                    info.add_text("prompt", json.dumps(prompt))
                for k, v in (extra_pnginfo or {}).items():
                    info.add_text(k, json.dumps(v))
                info.add_text("creative_studio", json.dumps(record))
            path = os.path.join(full_folder, f["filename"])
            pil.save(path, pnginfo=info, compress_level=4)
            with open(path + ".json", "w", encoding="utf-8") as fh:
                json.dump({**record, "file": f}, fh, indent=2)
            results.append({k: f[k] for k in ("filename", "subfolder", "type")})
        return {"ui": {"images": results, "cs_metadata": [record]}}


# --- 6. Batch Variant Manager -------------------------------------------------------------------------


class CS_BatchVariantManager:
    """Pick variant ``variant_index`` from a list and derive a deterministic seed.

    Lets one workflow produce a structured batch (e.g. "gold | warm candlelight",
    "silver | cold daylight") where every output records which variant and seed it
    came from. Creative Studio sets ``variant_index`` per job in a batch.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "variants": ("STRING", {"multiline": True,
                                        "default": "warm | warm golden-hour light, champagne tones\n"
                                                   "cool | cool north-window daylight, silver tones\n"
                                                   "noir | dramatic low-key light, black velvet"}),
                "variant_index": ("INT", {"default": 0, "min": 0, "max": 9999}),
                "base_seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "seed_strategy": (["increment", "hash", "fixed"], {"default": "increment"}),
            }
        }

    RETURN_TYPES = ("INT", "STRING", "STRING", "CS_VARIANT")
    RETURN_NAMES = ("seed", "variant_text", "label", "variant")
    FUNCTION = "select"
    CATEGORY = CATEGORY
    DESCRIPTION = "Structured, reproducible batch variations (text + seed) with metadata."

    @classmethod
    def VALIDATE_INPUTS(cls, variants=None, **_):
        if variants is None:
            return True
        try:
            core.parse_variants(variants)
        except core.NodeInputError as exc:
            return str(exc)
        return True

    def select(self, variants, variant_index, base_seed, seed_strategy):
        v = core.select_variant(core.parse_variants(variants), variant_index, base_seed, seed_strategy)
        return (v["seed"], v["text"], v["label"], v)


# --- 7. Project Metadata ------------------------------------------------------------------------------


class CS_ProjectMetadata:
    """Attach project/campaign/job identifiers and produce an organised filename prefix."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project_id": ("STRING", {"default": ""}),
                "project_name": ("STRING", {"default": "Untitled project"}),
                "campaign": ("STRING", {"default": ""}),
                "job_id": ("STRING", {"default": ""}),
                "tags": ("STRING", {"default": "", "tooltip": "comma separated"}),
            }
        }

    RETURN_TYPES = ("CS_PROJECT", "STRING")
    RETURN_NAMES = ("project", "filename_prefix")
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "Project/campaign identifiers for metadata and output folder organisation."

    def build(self, project_id, project_name, campaign, job_id, tags):
        rec = core.project_record(project_id, project_name, campaign, job_id, tags)
        return (rec, core.filename_prefix(rec))


NODE_CLASS_MAPPINGS = {
    "CS_ReferenceCollector": CS_ReferenceCollector,
    "CS_ProductProfileLoader": CS_ProductProfileLoader,
    "CS_CharacterProfileLoader": CS_CharacterProfileLoader,
    "CS_PromptTemplate": CS_PromptTemplate,
    "CS_GenerationMetadataSaver": CS_GenerationMetadataSaver,
    "CS_BatchVariantManager": CS_BatchVariantManager,
    "CS_ProjectMetadata": CS_ProjectMetadata,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CS_ReferenceCollector": "Reference Collector (Creative Studio)",
    "CS_ProductProfileLoader": "Product Profile Loader (Creative Studio)",
    "CS_CharacterProfileLoader": "Character Profile Loader (Creative Studio)",
    "CS_PromptTemplate": "Prompt Template (Creative Studio)",
    "CS_GenerationMetadataSaver": "Generation Metadata Saver (Creative Studio)",
    "CS_BatchVariantManager": "Batch Variant Manager (Creative Studio)",
    "CS_ProjectMetadata": "Project Metadata (Creative Studio)",
}
