# User guide — luxury jewelry campaign walkthrough

This follows the demonstration scenario end to end. Screens referenced are in `docs/screenshots/`.

## 0. Start everything

1. Start ComfyUI (`python main.py` in your ComfyUI folder) with the node package installed (`./scripts/install_nodes.sh /path/to/ComfyUI`).
2. `./scripts/start.sh` and open <http://127.0.0.1:8420>. The sidebar footer shows the ComfyUI connection; **Settings** has the server URL and a diagnostics checklist.

Shortcut: **Dashboard → Create demo project** performs steps 1–6 with placeholder images.

## 1. Create the project
**Projects → New project**, name "Luxury Jewelry Campaign", template *Jewelry campaign*. The template creates campaigns (Packshots, Editorial, Close-up details) and collections. Add a campaign "Winter Collection 2026" on the Overview tab.

## 2. Upload the jewelry photo
Project → **References** tab, category *Jewelry*, drop the product image. For product-preserving workflows use a **PNG with transparent background** (cut out the product in any editor or a background-removal tool). The library records size, alpha, SHA-256, palette.

## 3. Create the Product Profile
**Reference Studio → Profiles → New product profile**. Fill visual description, material/finish/stones/setting/shape, and *Important details to preserve* (e.g. "six-prong setting", "single centre stone"). Add the cut-out as **Primary** image, macro shots as **Detail**. The right column shows the deterministic prompt fragment used by the app and the profile-loader node.

## 4–5. Style and lighting references
Upload mood images as *Style* and *Lighting*; group them into collections. Star favourites — they appear on the dashboard.

## 6. Select a workflow
**Workflows** lists imported workflows. Import your own via **Import workflow** (ComfyUI: *Workflow → Export (API)* is the most reliable; a normal saved workflow is converted using your server's node definitions). Open a workflow to see the **Dependency check** (missing nodes/models, graph errors) and the **Parameters** creators may change.

## 7. Configure generation parameters
**Consistency → New configuration**: choose workflow, Product Profile and project. *Apply profile images* binds profile images to the workflow's image inputs; bind style/lighting references to the remaining inputs; set conditioning strengths (IPAdapter weight, mask expand, denoise…). Save — this configuration is reusable in later projects.

## 8. Launch
Press **Generate N** on the configuration, or use **Production Board → New generation** (pick workflow or configuration, override prompt/steps/CFG/size, choose variations and seed mode: increment / random / fixed).

## 9. Track the job
The Jobs tab shows queue position, running node and sampler step from ComfyUI's WebSocket. A job only shows **Completed** after ComfyUI's history confirms success and the images are downloaded. Failures show ComfyUI's own messages (e.g. "ckpt_name … not in []" = model missing). **Interrupt/Cancel** is available while queued or running.

## 10–11. Review and compare
**Gallery** tab: click an image for full size and its metadata (seed, sampler, steps, CFG, models + hashes, variant, references). Tick 2–4 images → **Compare** for side-by-side view with differing settings highlighted. In the lightbox, **Compare with references…** computes structure/colour/hash similarity against chosen references (heuristics, not proof).

## 12. Select finals
Mark images **Final** (and favourite/rate). Project → Outputs → *Final selects* lists them.

## 13. Save with metadata
Gallery → tick images → **Export**: a ZIP with images, `*.metadata.json` (full reproducibility record), `*.workflow_api.json` (the exact prompt executed) and `manifest.json`. With `CS_GenerationMetadataSaver` in the workflow, ComfyUI also writes a sidecar JSON next to each PNG.

## 14. Reopen and reproduce
Reopen the project any time: jobs, outputs and settings are stored locally (`data/`). In an output's lightbox press **Reproduce** to resubmit the identical API prompt (same seed and inputs; reference images are re-uploaded if ComfyUI's input folder was cleaned). Bit-identical pixels additionally require the same model files, ComfyUI version and hardware backend — MPS/CPU/CUDA results can differ slightly.

## Tips
- Changing a numeric field and clearing it reverts to the workflow default.
- Archive projects instead of deleting; deletion is only allowed for archived projects and keeps references/profiles.
- Data lives in `CS_DATA_DIR` (default `./data`): back it up to keep your library.
