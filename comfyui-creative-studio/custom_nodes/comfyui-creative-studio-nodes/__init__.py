"""ComfyUI Creative Studio nodes.

Install by placing this directory in ``ComfyUI/custom_nodes/`` (or symlinking it)
and restarting ComfyUI. No extra dependencies beyond what ComfyUI already ships
(torch, numpy, Pillow).
"""
from .cs_nodes.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
