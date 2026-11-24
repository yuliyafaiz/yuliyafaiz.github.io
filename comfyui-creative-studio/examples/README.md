# Examples

## Workflows (API format)
| File | Needs | Purpose |
|---|---|---|
| `workflows/pipeline_check_reference_board_api.json` | Creative Studio nodes only | Verifies upload → execution → outputs → metadata without any model |
| `workflows/jewelry_product_preserve_sd15_api.json` | core nodes + SD1.5 inpainting checkpoint | Scene generated around a product cut-out; original product pixels composited back |
| `workflows/jewelry_editorial_ipadapter_sdxl_api.json` | SDXL, ComfyUI_IPAdapter_plus + models, Creative Studio nodes | Style transfer from a mood reference, lighting variants, product composite, full metadata |

All three were validated against a real ComfyUI 0.46.0 `/object_info`; only the pipeline check has been executed (no checkpoints were available). Import them in Creative Studio or post them to ComfyUI's `/prompt` endpoint.

## Demo project data
`POST /api/demo/jewelry` (Dashboard → *Create demo project*) creates the jewelry project, three synthetic placeholder references drawn with Pillow (`backend/app/services/demo.py`), the "Aurora Solitaire Ring" product profile, these workflows and three consistency configurations. Example configuration: `../.env.example`.
