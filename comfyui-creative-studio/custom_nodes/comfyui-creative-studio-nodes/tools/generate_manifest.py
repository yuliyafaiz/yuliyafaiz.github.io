"""Write node_manifest.json from NODE_CLASS_MAPPINGS (consumed by the Creative Studio app).

Usage: python tools/generate_manifest.py   (no torch required)
"""
import importlib.util
import json
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cs_manifest_pkg", PKG / "__init__.py",
                                              submodule_search_locations=[str(PKG)])
mod = importlib.util.module_from_spec(spec)
sys.modules["cs_manifest_pkg"] = mod
spec.loader.exec_module(mod)


def describe(name, cls):
    spec = cls.INPUT_TYPES()
    def fmt(section):
        out = []
        for k, v in (spec.get(section) or {}).items():
            t = v[0] if isinstance(v, tuple) else v
            out.append({"name": k, "type": "COMBO" if isinstance(t, list) else t,
                        **({"options": t} if isinstance(t, list) else {}),
                        "tooltip": (v[1].get("tooltip") if isinstance(v, tuple) and len(v) > 1 else None)})
        return out
    return {"name": name, "display_name": mod.NODE_DISPLAY_NAME_MAPPINGS[name], "category": cls.CATEGORY,
            "description": getattr(cls, "DESCRIPTION", ""), "inputs": fmt("required"), "optional_inputs": fmt("optional"),
            "outputs": [{"name": n, "type": t} for n, t in zip(getattr(cls, "RETURN_NAMES", cls.RETURN_TYPES),
                                                               cls.RETURN_TYPES)],
            "output_node": getattr(cls, "OUTPUT_NODE", False)}


manifest = {"package": "comfyui-creative-studio-nodes", "version": "0.1.0",
            "nodes": [describe(n, c) for n, c in mod.NODE_CLASS_MAPPINGS.items()]}
(PKG / "node_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(f"wrote {len(manifest['nodes'])} nodes")
