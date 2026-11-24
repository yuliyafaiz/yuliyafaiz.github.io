# Development

## Setup

```bash
./scripts/setup.sh     # .venv + backend deps, npm ci + build, .env from .env.example
./scripts/dev.sh       # backend --reload on :8420 + Vite on :5173 (proxies /api)
```

## Configuration (`.env`, prefix `CS_`)

| Variable | Default | Meaning |
|---|---|---|
| `CS_COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI server (a value saved in Settings overrides it) |
| `CS_DATA_DIR` | `./data` | SQLite DB + media; relative to the repo root |
| `CS_HOST` / `CS_PORT` | `127.0.0.1` / `8420` | bind address |
| `CS_CORS_ORIGINS` | Vite dev origins | |
| `CS_POLL_INTERVAL` | `1.5` | seconds between `/history` polls for active jobs |
| `CS_LOST_JOB_GRACE` | `20` | seconds before a vanished prompt is marked `lost` |

Variables already set in the shell take precedence over `.env`. No secrets are needed; `.env` and `data/` are git-ignored.

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

```bash
CS_TEST_COMFY_URL=http://127.0.0.1:8188 ../.venv/bin/python -m pytest -q   # + real ComfyUI test (needs the CS nodes installed)
```

```bash
cd frontend && npm test && npm run typecheck
```

```bash
cd custom_nodes/comfyui-creative-studio-nodes && python -m pytest tests   # run with ComfyUI's Python (torch) for node tests
```

- `backend/tests/conftest.py` contains `FakeComfy`, an httpx `MockTransport` ComfyUI double with scenarios (success, error, interrupt, pending, lost, offline, rejection). `client.poll()` runs one tracker iteration deterministically.
- `test_real_comfy.py` runs the real app, tracker and WebSocket against a live server using the model-free pipeline-check workflow.
- Frontend tests mock `fetch` (`src/test/mockApi.ts`).

Current counts: backend 26 (1 opt-in real-ComfyUI), custom nodes 16, frontend 10.

## Conventions
- Backend: routers are thin; logic lives in `services/`. Workflow analysis functions are pure and unit-tested. Parameter keys are `"<node_id>.<input>"`.
- Never mark a job completed without a successful `/history` entry; never guess metadata (unknown → `null` or `dynamic_from`).
- Frontend: typed client in `src/lib/api.ts` mirrors `backend/app/schemas.py`; design tokens in `src/styles.css`.
- After changing node interfaces run `tools/generate_manifest.py` (the app's Custom Nodes page reads `node_manifest.json`).

## Extracting into its own repository
This project currently lives in a subdirectory. To give it its own history:

```bash
git subtree split --prefix comfyui-creative-studio -b creative-studio
```

The included `.github/workflows/ci.yml` becomes active at the new repository root.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Sidebar says "ComfyUI offline" | Start ComfyUI; check the URL in Settings; `curl http://127.0.0.1:8188/system_stats` |
| Job failed with `value_not_in_list … ckpt_name` | Model not in `ComfyUI/models/checkpoints`; or pick the right file in the parameter dropdown |
| "Creative Studio nodes not installed" | `./scripts/install_nodes.sh /path/to/ComfyUI` then restart ComfyUI; check its console for import errors |
| UI workflow "not executable" | Connect ComfyUI and press *Convert*, or attach Workflow → Export (API) |
| Workflow uses subgraphs | Use Export (API) in ComfyUI — subgraphs are not converted |
| Job stuck "Queued" | Another prompt is running in ComfyUI (see queue in sidebar); generation on CPU is very slow |
| Job became "lost" | ComfyUI was restarted and forgot the prompt; resubmit with Reproduce |
| WebSocket not connected but jobs complete | Fine: completion comes from `/history`; only live step progress is missing |
| Port 8420 in use | `CS_PORT=8430 ./scripts/start.sh` |
