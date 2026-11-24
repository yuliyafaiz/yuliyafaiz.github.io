"""Local image storage and lightweight image analysis (Pillow + NumPy).

OpenCV is intentionally not used: everything here (thumbnails, perceptual hash,
palette, SSIM on small grayscale images) is cheap to do with Pillow/NumPy and
avoids a ~90 MB dependency.
"""
from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
THUMB_SIZE = 512


class ImageError(ValueError):
    pass


@dataclass
class StoredImage:
    stored_name: str
    mime: str
    width: int
    height: int
    has_alpha: bool
    sha256: str
    phash: str
    palette: list[str]


def _open(data: bytes) -> Image.Image:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageError("file too large (max 50 MB)")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageError("not a readable image") from exc
    if img.format not in ALLOWED_FORMATS:
        raise ImageError(f"unsupported format {img.format}; use PNG, JPEG or WEBP")
    return img


def dhash(img: Image.Image, size: int = 8) -> str:
    """Difference hash (64 bit, hex). Robust to scaling and small edits."""
    g = img.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    a = np.asarray(g, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return f"{value:0{size * size // 4}x}"


def hamming(h1: str, h2: str) -> int:
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def palette(img: Image.Image, n: int = 5) -> list[str]:
    small = img.convert("RGB").resize((96, 96))
    q = small.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors() or [], reverse=True)
    out = []
    for _count, idx in counts[:n]:
        r, g, b = pal[idx * 3 : idx * 3 + 3]
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    return out


class MediaStore:
    """Stores originals and thumbnails under ``<data>/media/{kind}/``."""

    def __init__(self, root: Path):
        self.root = root

    def dir(self, kind: str) -> Path:
        d = self.root / kind
        d.mkdir(parents=True, exist_ok=True)
        (d / "thumbs").mkdir(exist_ok=True)
        return d

    def path(self, kind: str, stored_name: str) -> Path:
        return self.dir(kind) / stored_name

    def thumb_path(self, kind: str, stored_name: str) -> Path:
        return self.dir(kind) / "thumbs" / (Path(stored_name).stem + ".webp")

    def save(self, kind: str, data: bytes) -> StoredImage:
        img = _open(data)
        img = ImageOps.exif_transpose(img)
        fmt = img.format or "PNG"
        mime = ALLOWED_FORMATS.get(fmt, "image/png")
        ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[mime]
        sha = hashlib.sha256(data).hexdigest()
        stored_name = f"{sha[:16]}-{uuid.uuid4().hex[:8]}{ext}"
        self.path(kind, stored_name).write_bytes(data)
        self._thumb(img, self.thumb_path(kind, stored_name))
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        return StoredImage(
            stored_name=stored_name,
            mime=mime,
            width=img.width,
            height=img.height,
            has_alpha=bool(has_alpha),
            sha256=sha,
            phash=dhash(img),
            palette=palette(img),
        )

    @staticmethod
    def _thumb(img: Image.Image, dest: Path) -> None:
        t = img.copy()
        if t.mode not in ("RGB", "RGBA"):
            t = t.convert("RGBA")
        t.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
        t.save(dest, "WEBP", quality=85)

    def delete(self, kind: str, stored_name: str) -> None:
        for p in (self.path(kind, stored_name), self.thumb_path(kind, stored_name)):
            p.unlink(missing_ok=True)


# --- comparison ------------------------------------------------------------------


def _gray(path: Path, size: int = 256) -> np.ndarray:
    img = Image.open(path).convert("L")
    img = ImageOps.fit(img, (size, size), Image.Resampling.LANCZOS)
    return np.asarray(img, dtype=np.float64)


def ssim(a: np.ndarray, b: np.ndarray, win: int = 8) -> float:
    """Mean SSIM over non-overlapping windows (grayscale, 0..255)."""
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    h, w = a.shape
    h, w = h - h % win, w - w % win
    a = a[:h, :w].reshape(h // win, win, w // win, win).swapaxes(1, 2)
    b = b[:h, :w].reshape(h // win, win, w // win, win).swapaxes(1, 2)
    ma, mb = a.mean(axis=(2, 3)), b.mean(axis=(2, 3))
    va, vb = a.var(axis=(2, 3)), b.var(axis=(2, 3))
    cov = ((a - ma[..., None, None]) * (b - mb[..., None, None])).mean(axis=(2, 3))
    s = ((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma**2 + mb**2 + c1) * (va + vb + c2))
    return float(s.mean())


def histogram_correlation(p1: Path, p2: Path) -> float:
    def hist(p: Path) -> np.ndarray:
        img = Image.open(p).convert("RGB").resize((128, 128))
        h = np.concatenate([np.asarray(c.histogram(), dtype=np.float64) for c in img.split()])
        return h / h.sum()

    h1, h2 = hist(p1), hist(p2)
    return float(np.corrcoef(h1, h2)[0, 1])


def compare_images(p1: Path, p2: Path) -> dict[str, float]:
    """Heuristic similarity signals. These are NOT identity/product verification."""
    i1, i2 = Image.open(p1), Image.open(p2)
    phash_dist = hamming(dhash(i1), dhash(i2))
    return {
        "structural_similarity": round(ssim(_gray(p1), _gray(p2)), 4),
        "color_histogram_correlation": round(histogram_correlation(p1, p2), 4),
        "perceptual_hash_distance": phash_dist,
        "perceptual_hash_similarity": round(1 - phash_dist / 64, 4),
    }
