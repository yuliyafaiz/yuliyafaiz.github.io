# Roadmap

## Next (verification)
- Run the jewelry workflows on Apple Silicon (8/16 GB tiers), record timings and quality in MODEL_COMPATIBILITY.md, add real portfolio screenshots of generated outputs.
- Mask helper: optional background-removal step (e.g. a BiRefNet/RMBG node pack, checking licences) so users can start from a regular product photo instead of a cut-out.

## Product
- ControlNet (canny/depth) variant of the packshot workflow for angle-consistent re-renders.
- Batch "sweeps": vary any parameter across a batch from the UI (the API already supports `variant_values`).
- Side-by-side reference overlay (onion skin / difference view) in the comparison modal.
- Prompt template library managed in the app and synced to `CS_PromptTemplate`.
- Tags and notes on outputs; client review share-out (static HTML export).
- Image-to-video workflows (category exists; needs model guidance for Macs).

## Engineering
- Alembic migrations once the schema stabilises (v0.1 uses `create_all`).
- Server-sent events instead of polling for job updates.
- Multiple ComfyUI servers (per-job `server_url` is already stored).
- Optional support for ComfyUI's newer `/api/jobs` endpoints when available, keeping the classic routes as fallback.
- Publish the node package to the Comfy Registry.
