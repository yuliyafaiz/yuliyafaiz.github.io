# Model compatibility, hardware and licensing

**Status:** nothing in this document has been benchmarked on a Mac yet. The development environment had no access to the user's Mac or to Hugging Face, so no model was downloaded or run. Recommendations below are based on known model sizes and ComfyUI's MPS support; verify on your machine (steps at the end). Creative Studio never downloads models automatically.

## Check your Mac first

```bash
sysctl -n machdep.cpu.brand_string; sysctl -n hw.memsize | awk '{print $1/1024/1024/1024 " GB"}'
```

```bash
df -h ~
```

In Creative Studio → **Settings → Diagnostics** shows the device ComfyUI uses (`mps` on Apple Silicon, `cpu` otherwise) and free memory. Intel Macs without Metal-capable PyTorch run on CPU only — practical only for the model-free pipeline check.

## Recommended tiers (Apple Silicon, unified memory)

| Memory | Recommended base | Workflow | Expectation |
|---|---|---|---|
| 8 GB | SD 1.5 inpainting (~2 GB fp16) | `jewelry_product_preserve_sd15_api.json` at 512–768 px | Feasible; close other apps |
| 16 GB | SD 1.5, or SDXL base / an SDXL fine-tune (~6.5 GB) | both demo workflows; SDXL at 1024 px | SDXL is slow but usable |
| 24 GB+ | SDXL + IPAdapter Plus + ControlNet | `jewelry_editorial_ipadapter_sdxl_api.json` | Comfortable |

Not recommended for this project on most Macs: FLUX.1 (12B parameters; fp8/GGUF variants exist but are slow on MPS, and FLUX.1-dev is non-commercial), SD 3.5 Large, video models.

## Files for the demo workflows

| Workflow | Model file (ComfyUI folder) | Notes |
|---|---|---|
| Packshot (SD1.5 inpainting) | an SD 1.5 **inpainting** checkpoint → `models/checkpoints/` | The workflow default name is `sd-v1-5-inpainting.ckpt`; choose your actual file in the Sampler/Models parameter dropdown. A regular SD 1.5 checkpoint also works with `InpaintModelConditioning` (noise mask), with weaker edge blending. |
| Editorial (SDXL + IPAdapter) | SDXL checkpoint → `models/checkpoints/`; IPAdapter Plus SDXL model → `models/ipadapter/`; CLIP Vision ViT-H → `models/clip_vision/` | Requires the **ComfyUI_IPAdapter_plus** node pack. Its `IPAdapterUnifiedLoader` expects specific filenames per preset — follow that project's README. |
| Pipeline check | none | Verifies the integration only. |

ComfyUI_IPAdapter_plus has been in **maintenance-only mode since April 2025** (author notice in the repository). Its node signatures used here were verified against commit `a0f451a` (14 Apr 2025) on ComfyUI 0.46.0. If it breaks on a future ComfyUI, the packshot workflow (core nodes only) is unaffected.

## Licensing (verify before commercial use)

Summaries, not legal advice. Always read the license on the model card of the exact file you download.

| Model family | License | Commercial use of outputs |
|---|---|---|
| Stable Diffusion 1.5 / 1.5 inpainting | CreativeML OpenRAIL-M | Allowed, subject to the use-based restrictions |
| SDXL 1.0 base/refiner | CreativeML Open RAIL++-M | Allowed, subject to the use-based restrictions |
| Community SDXL / SD1.5 fine-tunes | varies (often OpenRAIL; some add restrictions) | Check each model card |
| IP-Adapter (h94) weights | Apache-2.0 per the model card (verify) | Allowed |
| ComfyUI_IPAdapter_plus code | GPL-3.0 | Code license; affects redistribution of the node pack, not your images |
| **InsightFace** model packs (`buffalo_l`, `antelopev2`) used by IPAdapter FaceID / InstantID | **Non-commercial research only**; commercial licence from InsightFace | Treat FaceID/InstantID pipelines as non-commercial unless licensed |
| FLUX.1 [schnell] | Apache-2.0 | Allowed |
| FLUX.1 [dev] | FLUX [dev] Non-Commercial License | Model use is non-commercial; terms for outputs have changed between versions — check bfl.ai |

## Limits of reference preservation — read before promising clients anything

- **Exact product pixels**: the demo workflows composite the original cut-out back onto the generated scene (`ImageCompositeMasked`). Shape, stone placement and metal colour of the product are therefore unchanged *by construction* — but only where the mask covers the product. Mask quality is everything: use a clean PNG cut-out.
- **What compositing cannot do**: physically consistent reflections, contact shadows, light colour on the metal, or the product rendered from a new angle or worn on a hand. Those require regenerating product pixels, and then diffusion models routinely alter prongs, stone counts and engravings.
- **IPAdapter / style references** transfer mood, palette and texture; they do not preserve geometry.
- **ControlNet (canny/depth)** preserves outlines approximately; fine details (prong count, micro-pavé) are not reliable.
- **Character identity** (FaceID/InstantID/PuLID) improves likeness but is not guaranteed, and the face-embedding models carry the licence restriction above.
- The comparison metrics in the app (SSIM, histogram correlation, perceptual hash) are drift indicators, not proof of preservation. Final review is human.

## Verifying on your Mac

1. Install ComfyUI and the node package; start ComfyUI and Creative Studio.
2. Run **Aurora · pipeline check** — confirms the integration (seconds).
3. Put one SD 1.5 inpainting checkpoint into `ComfyUI/models/checkpoints/`, open **Workflows → Jewelry packshot** → *Dependency check* should turn green.
4. Replace the placeholder cut-out with a real product PNG (Reference Studio → upload as *Jewelry* → Profile → primary image; update the binding in the consistency config).
5. Generate 2 variations at 768 px, note the execution time shown on each job, and inspect product edges at 100 %.
