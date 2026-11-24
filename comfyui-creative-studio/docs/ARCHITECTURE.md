# Architecture

A single local process (FastAPI) serves the API and the built React app, stores data in SQLite + the local filesystem, and talks to one ComfyUI server over HTTP and WebSocket. A separate node package runs *inside* ComfyUI. No cloud services, no microservices.

```
 Browser (React/Vite build)
        │  /api/*  (JSON, multipart)
        ▼
 FastAPI app  ──────────────────────────────┐
  routers/  projects · references · profiles │
            workflows · consistency · jobs   │
            comfy · custom_nodes · dashboard │
  services/ workflow.py   (format, deps, params, UI→API, metadata)
            comfy.py      (HTTP client, history interpretation)
            generation.py (submission, Tracker, WebSocket listener)
            images.py     (storage, thumbnails, dHash, palette, SSIM)
            demo.py       (jewelry demo seeder)
        │ SQLite: data/studio.sqlite3      Files: data/media/{references,outputs}
        ▼
 ComfyUI  (/prompt, /ws, /history, /queue, /view, /upload/image, /object_info, /system_stats)
   └─ custom_nodes/comfyui-creative-studio-nodes  (CS_* nodes)
```

## Key decisions

- **Stack as requested** (React+TS+Vite, FastAPI+Pydantic, SQLite, Pillow). SQLAlchemy 2 ORM instead of raw SQL; `create_all` instead of migrations for v0.1 (see roadmap).
- **No OpenCV.** Thumbnails, perceptual hash (dHash), palette and block SSIM are small NumPy/Pillow functions; OpenCV would add ~90 MB for no current need.
- **Polling + WebSocket.** The frontend polls the backend (1.5 s while jobs are active). The backend keeps one WebSocket to ComfyUI with a fixed `client_id` for live progress, and polls `/history` as the source of truth.
- **Classic node API** (`INPUT_TYPES`/`RETURN_TYPES`/`FUNCTION`), which every current ComfyUI loads, rather than the newer V3 schema API, for broad version compatibility.

## Truth model for job state

| State | Set when |
|---|---|
| `submitted` | `/prompt` accepted; prompt in the pending queue |
| `running` | prompt in `queue_running`, or a history entry without terminal status |
| `completed` | history `status_str == "success"` **and** `completed == true` **and** all output images downloaded |
| `failed` | `/prompt` rejected (validation errors stored as `node_errors`), history reports `execution_error`, or output retrieval failed |
| `interrupted` | history contains `execution_interrupted` |
| `cancelled` | removed from the pending queue by the user |
| `lost` | absent from queue *and* history for `CS_LOST_JOB_GRACE` seconds (e.g. ComfyUI restarted) |

If ComfyUI is unreachable, jobs keep their state and show `connection: unreachable`. Nothing is inferred from WebSocket events alone.

## Workflow formats

ComfyUI's **UI format** (`nodes`/`links`, widgets by position, Reroute/Primitive/Note nodes, mute/bypass, subgraphs) and **API format** (`{id: {class_type, inputs}}`) are not interchangeable. Creative Studio:

1. Preserves the imported JSON verbatim (`original_json`).
2. Executes only API format (`api_json`): either imported directly ("Export (API)" in ComfyUI — authoritative), or converted from UI format using the server's `/object_info` (input order, widget detection, `control_after_generate` skipping, Reroute/bypass pass-through, Primitive values). Subgraphs are refused with a message to use Export (API).
3. Validates before submission: missing node classes, missing models (combo values not in the server's list), unknown/missing inputs, dangling links, link type mismatches.

Parameters are keyed `"<node_id>.<input>"`. Discovery traces positive/negative prompts slot-aware from sampler inputs (through `InpaintModelConditioning`, `ControlNetApplyAdvanced`, …).

## Database schema

```
projects(id, name, description, client, status, template_key, meta JSON, cover_reference_id, created_at, updated_at)
campaigns(id, project_id→projects, name, description, status, created_at)
activity(id, project_id, kind, message, entity_type, entity_id, data JSON, created_at)
references(id, title, original_name, stored_name, mime, width, height, has_alpha, sha256, phash, palette JSON,
           category, tags JSON, description, favorite, created_at)
project_references(project_id, reference_id)            -- references are reusable across projects
collections(id, name, description, project_id, created_at)
collection_items(id, collection_id, reference_id, position)
profiles(id, kind[product|character], name, description, category, attributes JSON, preserve_details JSON,
         generation_settings JSON, notes, created_at, updated_at)
profile_images(id, profile_id, reference_id, role[primary|face|detail|angle|material|style|other], position)
project_profiles(project_id, profile_id) · profile_workflows(profile_id, workflow_id)
workflows(id, name, description, category, project_id, is_template, source_format[api|ui], original_json JSON,
          api_json JSON, api_source[imported|converted], conversion_warnings JSON, parameters JSON,
          node_types JSON, models JSON, created_at, updated_at)
consistency_configs(id, name, description, workflow_id, profile_id, project_id, methods JSON,
                    image_bindings JSON {param_key: reference_id}, values JSON {param_key: value},
                    use_profile_prompt, created_at, updated_at)
jobs(id, project_id, campaign_id, workflow_id, consistency_config_id, batch_id, variation_index, name, status,
     server_url, comfy_prompt_id, parameter_values JSON, image_bindings JSON, submitted_prompt JSON,
     progress JSON, error JSON, status_messages JSON, execution_seconds, created_at, submitted_at, finished_at)
outputs(id, job_id, project_id, stored_name, width, height, node_id, comfy_filename, comfy_subfolder, comfy_type,
        favorite, selected, rating, note, meta JSON, created_at)
app_settings(key, value JSON)
```

## Reproducibility record (`outputs.meta`)

`schema: creative-studio/generation@1` — job/batch/variation ids, workflow, extracted generation summary (prompt, negative, seed, sampler, scheduler, steps, CFG, denoise, dimensions, models with SHA-256 when known, methods), all parameter values, reference images with SHA-256, ComfyUI prompt id / server / execution time, the runtime record from `CS_GenerationMetadataSaver` (actual template-rendered prompt, variant, model hashes), timestamps, and the output file hash. The exact API prompt lives on the job and is included in exports.

Model hashes come from (1) `CS_GenerationMetadataSaver`, which hashes model files on the ComfyUI machine, or (2) `modelspec.hash_sha256` from `/view_metadata` if the safetensors header has it. Otherwise `sha256: null` — never guessed.

## Submission pipeline

1. Merge consistency-config values/bindings with request overrides; optionally append the profile prompt fragment to positive/negative prompts.
2. Check ComfyUI is reachable (503 otherwise; no job rows created).
3. Per variation: create the job row, upload bound references to `input/creative_studio/ref-<sha>.ext` (cached per batch, idempotent), inject profile JSON into `CS_*ProfileLoader` nodes and project/campaign/job ids into `CS_ProjectMetadata`, apply values, set seeds (`increment`/`random`/`fixed`) and `variant_index` on `CS_BatchVariantManager`, POST `/prompt` with `extra_data.creative_studio`.
