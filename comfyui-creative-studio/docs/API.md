# REST API

Base URL `http://127.0.0.1:8420/api`. JSON unless noted. Interactive schema: `http://127.0.0.1:8420/docs` (FastAPI/OpenAPI). Errors return `{"detail": "..."}` with 404 (not found), 409 (state conflict), 422 (validation), 502/503 (ComfyUI error / unreachable).

## Projects
| Method | Path | Notes |
|---|---|---|
| GET | `/project-templates` | jewelry_campaign, fashion_editorial, ecommerce_catalog, blank |
| GET | `/projects?status=active\|archived\|all` | with counts |
| POST | `/projects` | `{name, description?, client?, template_key?, meta?}` — template creates campaigns + collections |
| GET | `/projects/{id}` | + references, profiles, collections, workflows |
| PATCH | `/projects/{id}` | name, description, client, meta, cover_reference_id |
| POST | `/projects/{id}/archive` · `/restore` | |
| DELETE | `/projects/{id}` | only when archived (409 otherwise) |
| POST | `/projects/{id}/campaigns` | `{name, description?}` |
| PATCH / DELETE | `/campaigns/{id}` | |
| POST | `/projects/{id}/references` | `{ids: [...]}` attach existing references |
| DELETE | `/projects/{id}/references/{rid}` | detach |
| POST | `/projects/{id}/profiles` | `{ids}` |
| GET | `/projects/{id}/activity` | history |

## References & collections
| Method | Path | Notes |
|---|---|---|
| GET | `/reference-categories` | 12 categories |
| GET | `/references?q=&category=&tag=&project_id=&collection_id=&favorite=` | |
| POST | `/references` | **multipart**: `files[]`, `category`, `tags` (comma), `description`, `project_id?`, `collection_id?`. PNG/JPEG/WEBP ≤ 50 MB |
| GET / PATCH / DELETE | `/references/{id}` | PATCH: title, category, tags, description, favorite. DELETE refused (409) while used by an active job |
| GET | `/references/{id}/file` · `/thumb` | original · 512 px WEBP |
| GET | `/references/tags` | tag counts |
| GET/POST | `/collections` | `{name, description?, project_id?, reference_ids?}` |
| PATCH | `/collections/{id}` | `reference_ids` = full ordered replacement |
| POST | `/collections/{id}/items` | `{ids}` append |
| DELETE | `/collections/{id}/items/{rid}` · `/collections/{id}` | |

## Profiles
| Method | Path | Notes |
|---|---|---|
| GET | `/profiles?kind=product\|character&project_id=` | |
| GET | `/profiles/attribute-fields` | suggested attribute keys + image roles |
| POST | `/profiles` | `{kind, name, description, category, attributes, preserve_details, generation_settings, notes, project_ids}` |
| GET | `/profiles/{id}` | includes `prompt_fragment {positive, negative}` |
| PATCH | `/profiles/{id}` | any field, plus `project_ids`, `workflow_ids` |
| POST | `/profiles/{id}/images` | `{reference_id, role}` |
| DELETE | `/profiles/{id}/images/{image_id}` · `/profiles/{id}` | |
| GET | `/profiles/{id}/export` | JSON for the `profile_json` input of the profile-loader nodes |

## Workflows
| Method | Path | Notes |
|---|---|---|
| GET | `/workflow-categories` | |
| GET | `/workflows?project_id=&category=&templates=` | |
| POST | `/workflows` | `{name, data, category, description?, project_id?, is_template?}`; `data` = UI or API JSON (or `{prompt: …}`) |
| POST | `/workflows/upload` | multipart `file` + same fields |
| GET / PATCH / DELETE | `/workflows/{id}` | PATCH `parameters` is validated: each must target a literal input |
| POST | `/workflows/{id}/convert` | UI→API with live `/object_info` (503 if ComfyUI offline) |
| POST | `/workflows/{id}/api-json` | `{data}` attach an Export (API) file |
| POST | `/workflows/{id}/rediscover` | re-run parameter discovery |
| GET | `/workflows/{id}/dependencies` | `{checked, missing_nodes, missing_models, invalid_values, structure_issues[{severity}], methods, ready}` |
| GET | `/workflows/{id}/inputs` | all literal inputs (to expose as parameters) |
| GET | `/workflows/{id}/download?which=api\|original` | |
| POST | `/workflows/{id}/duplicate?project_id=` | |

## Consistency
| Method | Path | Notes |
|---|---|---|
| GET | `/consistency/methods` | method descriptions |
| GET | `/consistency/plan/{workflow_id}?profile_id=` | image params, conditioning params, suggested bindings from profile images |
| GET/POST | `/consistency` | `{name, workflow_id, profile_id?, project_id?, image_bindings {key: reference_id}, values {key: value}, use_profile_prompt}` |
| GET / PATCH / DELETE | `/consistency/{id}` | |

## Production
| Method | Path | Notes |
|---|---|---|
| POST | `/generate` | `{workflow_id \| consistency_config_id, project_id?, campaign_id?, name?, values, image_bindings, variations 1–32, seed_mode increment\|random\|fixed, base_seed?, variant_values?[]}` → `{batch_id, jobs}`. 503 if ComfyUI unreachable; a ComfyUI validation rejection yields a `failed` job with `error.node_errors` |
| GET | `/jobs?project_id=&status=a,b&batch_id=&limit=` | includes live progress |
| GET | `/jobs/{id}` | + `submitted_prompt`, `status_messages` |
| POST | `/jobs/{id}/cancel` | pending → removed from queue (`cancelled`); running → `/interrupt` (becomes `interrupted` when history confirms) |
| POST | `/jobs/{id}/reproduce` | resubmits the identical API prompt |
| GET | `/outputs?project_id=&job_id=&batch_id=&favorite=&selected=` | |
| GET / PATCH | `/outputs/{id}` | favorite, selected, rating 0–5, note |
| GET | `/outputs/{id}/file` · `/thumb` · `/metadata` | metadata = reproducibility record + API prompt |
| POST | `/outputs/export` | `{output_ids}` → ZIP: images, `*.metadata.json`, `*.workflow_api.json`, `manifest.json` |
| POST | `/outputs/{id}/compare` | `{reference_ids?, output_ids?}` → SSIM, colour-histogram correlation, perceptual-hash distance (heuristics) |

## ComfyUI, settings, misc
| Method | Path | Notes |
|---|---|---|
| GET | `/comfy/status` | reachability, version, devices, RAM, queue, WebSocket |
| GET | `/comfy/diagnostics` | checklist (HTTP, object_info, CS nodes, IPAdapter, checkpoints, WebSocket, device) |
| GET | `/comfy/nodes?search=&category=` · `/comfy/nodes/{name}` | node catalogue from `/object_info` |
| GET / PUT | `/settings` | `{comfy_url}` (persisted, overrides `CS_COMFY_URL`) |
| POST | `/settings/test` | test a URL without saving |
| GET | `/custom-nodes` | node package manifest + installed status |
| GET | `/dashboard` | aggregates |
| POST | `/demo/jewelry` | idempotent demo seeding |
| GET | `/health` | |

## Example: run a batch with curl

```bash
curl -s -X POST localhost:8420/api/generate -H 'content-type: application/json' \
  -d '{"consistency_config_id": 1, "variations": 3, "seed_mode": "increment", "base_seed": 500}'
```
