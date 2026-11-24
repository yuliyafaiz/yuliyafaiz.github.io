# Custom nodes — `comfyui-creative-studio-nodes`

An independent ComfyUI package (`custom_nodes/comfyui-creative-studio-nodes/`). It works with or without the Creative Studio app. No dependencies beyond what ComfyUI ships (torch, NumPy, Pillow). Classic node API (`INPUT_TYPES`, `RETURN_TYPES`, `FUNCTION`, `CATEGORY`), category **Creative Studio**.

Verified: all 7 nodes load in ComfyUI 0.46.0 and the pipeline-check workflow executes end to end there.

## Install

```bash
./scripts/install_nodes.sh /path/to/ComfyUI          # symlink (development)
./scripts/install_nodes.sh /path/to/ComfyUI --copy   # copy
```

or copy the folder into `ComfyUI/custom_nodes/` manually, then restart ComfyUI. The package includes a `pyproject.toml` with `[tool.comfy]` metadata for the Comfy Registry (publisher id left empty).

## Custom types

| Type | Content |
|---|---|
| `CS_PROJECT` | `{project_id, project_name, campaign, job_id, tags}` |
| `CS_PROFILE` | profile summary (id, kind, name, category, description, attributes, preserve_details, files) |
| `CS_VARIANT` | `{label, text, index, count, wrapped, seed, strategy, …extra keys}` |
| `CS_REFERENCES` | `{count, size, resize_mode, items[{input, batch_index, label, original_size}]}` |

## Nodes

### Reference Collector — `CS_ReferenceCollector`
Batch up to six images of **different sizes** (each may be a batch) with `pad` / `crop` / `stretch` and target `width`/`height` (0 = first image). Outputs `images` (IMAGE), `pad_mask` (MASK, 1 = padding), `references` (CS_REFERENCES manifest with labels), `count`. Improvement over core `ImageBatch`: N inputs, aspect-preserving, labelled manifest recorded with outputs.

### Product Profile Loader — `CS_ProductProfileLoader`
Input `profile_json` (filled automatically by Creative Studio; or paste `GET /api/profiles/{id}/export` and put the files under `ComfyUI/input`), `max_side`, `resize_mode`. Outputs `product_images`, `background_mask` (LoadImage convention: 1 where transparent — so it marks the background of a cut-out; invert it to protect the product), `detail_images` (detail/angle/material roles; falls back to primary), `positive_fragment`, `negative_fragment`, `profile`. Paths are confined to the input directory; `VALIDATE_INPUTS` rejects malformed JSON before execution; `IS_CHANGED` re-runs when image files change.

### Character Profile Loader — `CS_CharacterProfileLoader`
Same contract for characters: `face_images` (role `face`, falling back to `primary`), `reference_images`, fragments, `profile`. Feed `face_images` to IPAdapter FaceID / InstantID / PuLID nodes if installed.

### Prompt Template — `CS_PromptTemplate`
`template` with `{var}` and `{var|default}` placeholders; `{{`/`}}` for literal braces. Variables from the text box (`key: value` lines or JSON) and optional `profile` (`{profile.name}`, `{profile.attributes.material}`, `{profile.fragment}`, `{profile.negative}`), `variant` (`{variant.text}`, `{variant.label}`), `project` (`{project.campaign}`). `strict` fails on missing variables instead of silently producing a broken prompt. Outputs `prompt`, `resolution_json` (used/missing variables).

### Generation Metadata Saver — `CS_GenerationMetadataSaver` (output node)
Saves PNGs like `SaveImage` (embedded `prompt`/`workflow`, respecting `--disable-metadata`) plus:
- a `creative_studio` PNG text chunk and a sidecar `<file>.png.json`;
- project, profile, variant, reference manifest, positive/negative prompt, seed, sampler summary, notes;
- **SHA-256 of every model file** referenced by the prompt (`ckpt_name`, `lora_name`, `vae_name`, `control_net_name`, `unet_name`, `clip_name*`, `ipadapter_file`, `clip_vision`, `style_model_name`), computed on the ComfyUI machine and cached by path+size+mtime in `user/creative_studio_hash_cache.json`. The first hash of a multi-GB checkpoint takes seconds to a minute.
The record is also returned as UI output `cs_metadata`, which Creative Studio stores with each output.

### Batch Variant Manager — `CS_BatchVariantManager`
`variants` (one per line `label | text`, or JSON list of strings/objects), `variant_index`, `base_seed`, `seed_strategy` (`increment` = base+index, `hash` = stable per label, `fixed`). Outputs `seed`, `variant_text`, `label`, `variant`. Creative Studio sets `variant_index` = variation number for each job in a batch.

### Project Metadata — `CS_ProjectMetadata`
`project_id`, `project_name`, `campaign`, `job_id`, `tags` → `project` and `filename_prefix` like `creative_studio/<project>/<campaign>/job42` (feed into the saver to organise output folders). Creative Studio fills ids automatically.

## Tests

```bash
cd custom_nodes/comfyui-creative-studio-nodes
python -m pytest tests            # pure-logic tests run anywhere; node tests need torch (skipped otherwise)
python tools/generate_manifest.py # regenerate node_manifest.json after changing node interfaces
```

`tests/conftest.py` provides a stub `folder_paths` module; inside ComfyUI the real one is used.
