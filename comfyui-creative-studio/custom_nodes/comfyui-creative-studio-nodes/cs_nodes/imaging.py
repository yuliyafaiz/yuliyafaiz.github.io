"""Image <-> tensor helpers following ComfyUI conventions.

IMAGE: float32 tensor [B, H, W, C] in 0..1 (C=3).
MASK:  float32 tensor [B, H, W]; like core ``LoadImage``, mask = 1 - alpha
       (1 where the image is transparent).
"""
from __future__ import annotations

import numpy as np
import torch
from PIL import Image, ImageOps


def load_rgba(path: str) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGBA")


def fit(img: Image.Image, width: int, height: int, mode: str, pad_color=(0, 0, 0, 0)) -> Image.Image:
    """Resize to exactly ``width``x``height`` using pad | crop | stretch."""
    if mode == "stretch":
        return img.resize((width, height), Image.Resampling.LANCZOS)
    if mode == "crop":
        return ImageOps.fit(img, (width, height), Image.Resampling.LANCZOS)
    if mode == "pad":
        canvas = Image.new("RGBA", (width, height), pad_color)
        im = ImageOps.contain(img, (width, height), Image.Resampling.LANCZOS)
        canvas.paste(im, ((width - im.width) // 2, (height - im.height) // 2))
        return canvas
    raise ValueError(f"unknown resize mode {mode!r}")


def limit_size(img: Image.Image, max_side: int) -> Image.Image:
    if max_side and max(img.size) > max_side:
        img = ImageOps.contain(img, (max_side, max_side), Image.Resampling.LANCZOS)
    return img


def to_tensors(images: list[Image.Image]) -> tuple[torch.Tensor, torch.Tensor]:
    """Stack same-size RGBA PIL images into (IMAGE, MASK)."""
    rgb, masks = [], []
    for im in images:
        a = np.asarray(im.convert("RGBA"), dtype=np.float32) / 255.0
        rgb.append(torch.from_numpy(a[..., :3].copy()))
        masks.append(torch.from_numpy(1.0 - a[..., 3].copy()))
    return torch.stack(rgb), torch.stack(masks)


def tensor_to_pil(image: torch.Tensor) -> list[Image.Image]:
    """IMAGE [B,H,W,C] -> list of PIL RGB(A) images."""
    out = []
    for t in image:
        arr = np.clip(255.0 * t.detach().cpu().float().numpy(), 0, 255).astype(np.uint8)
        out.append(Image.fromarray(arr))
    return out


def common_batch(images: list[Image.Image], mode: str, width: int, height: int) -> list[Image.Image]:
    """Bring images of different sizes to one size (0 = use the first image's size)."""
    if not images:
        return []
    w = width or images[0].width
    h = height or images[0].height
    return [im if im.size == (w, h) else fit(im, w, h, mode) for im in images]
