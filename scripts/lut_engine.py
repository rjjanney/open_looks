"""Parse and apply 3D .cube LUTs -- the de facto standard format for
color-grading/film-emulation "looks", supported by DaVinci Resolve, Premiere,
Lightroom/ACR, Photoshop, and basically everything else. Trilinear
interpolation, vectorized in numpy so it's fast enough for full-res photos.

Only 3D LUTs are supported (LUT_3D_SIZE) -- 1D LUTs are a different, much
simpler mechanism (per-channel curve, no cross-channel color shift) and
aren't what people mean by a "film look" LUT.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


class Lut3D:
    def __init__(
        self,
        table: np.ndarray,
        domain_min: tuple[float, float, float] = (0.0, 0.0, 0.0),
        domain_max: tuple[float, float, float] = (1.0, 1.0, 1.0),
        title: str = "",
    ) -> None:
        self.table = table  # shape (N, N, N, 3), indexed [r, g, b] -> output rgb
        self.size = table.shape[0]
        self.domain_min = np.array(domain_min, dtype=np.float32)
        self.domain_max = np.array(domain_max, dtype=np.float32)
        self.title = title

    def apply(self, img: np.ndarray) -> np.ndarray:
        """img: (H,W,3) float32 in [0,1]. Returns the same shape, trilinearly
        interpolated through the LUT's 3D grid."""
        n = self.size
        span = np.maximum(self.domain_max - self.domain_min, 1e-6)
        normalized = np.clip((img - self.domain_min) / span, 0.0, 1.0)
        grid_pos = normalized * (n - 1)

        r0 = np.clip(np.floor(grid_pos[..., 0]).astype(np.int32), 0, n - 1)
        g0 = np.clip(np.floor(grid_pos[..., 1]).astype(np.int32), 0, n - 1)
        b0 = np.clip(np.floor(grid_pos[..., 2]).astype(np.int32), 0, n - 1)
        r1 = np.clip(r0 + 1, 0, n - 1)
        g1 = np.clip(g0 + 1, 0, n - 1)
        b1 = np.clip(b0 + 1, 0, n - 1)

        fr = (grid_pos[..., 0] - r0)[..., None]
        fg = (grid_pos[..., 1] - g0)[..., None]
        fb = (grid_pos[..., 2] - b0)[..., None]

        t = self.table
        c000, c100 = t[r0, g0, b0], t[r1, g0, b0]
        c010, c110 = t[r0, g1, b0], t[r1, g1, b0]
        c001, c101 = t[r0, g0, b1], t[r1, g0, b1]
        c011, c111 = t[r0, g1, b1], t[r1, g1, b1]

        c00 = c000 * (1 - fr) + c100 * fr
        c10 = c010 * (1 - fr) + c110 * fr
        c01 = c001 * (1 - fr) + c101 * fr
        c11 = c011 * (1 - fr) + c111 * fr

        c0 = c00 * (1 - fg) + c10 * fg
        c1 = c01 * (1 - fg) + c11 * fg

        out = c0 * (1 - fb) + c1 * fb
        return np.clip(out, 0.0, 1.0).astype(np.float32)


def load_cube(path: str | Path) -> Lut3D:
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    size: int | None = None
    domain_min = (0.0, 0.0, 0.0)
    domain_max = (1.0, 1.0, 1.0)
    title = ""
    values: list[tuple[float, float, float]] = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        key = parts[0].upper()
        if key == "TITLE":
            title = line.split(None, 1)[1].strip().strip('"')
        elif key == "LUT_3D_SIZE":
            size = int(parts[1])
        elif key == "LUT_1D_SIZE":
            raise ValueError(f"{path}: 1D .cube LUTs aren't supported, only 3D (LUT_3D_SIZE)")
        elif key == "DOMAIN_MIN":
            domain_min = tuple(float(x) for x in parts[1:4])
        elif key == "DOMAIN_MAX":
            domain_max = tuple(float(x) for x in parts[1:4])
        else:
            try:
                r, g, b = (float(x) for x in parts[:3])
            except ValueError:
                continue  # unrecognized line -- skip rather than hard-fail
            values.append((r, g, b))

    if size is None:
        raise ValueError(f"{path}: no LUT_3D_SIZE found -- not a valid 3D .cube file")
    expected = size**3
    if len(values) != expected:
        raise ValueError(f"{path}: expected {expected} data lines for LUT_3D_SIZE {size}, found {len(values)}")

    # .cube data-line order: R varies fastest, then G, then B. Reshaping a
    # flat (size**3, 3) array to (size,size,size,3) in C order naturally
    # gives axes [b, g, r, channel] (last axis before the trailing 3 varies
    # fastest) -- transpose to the [r, g, b, channel] indexing Lut3D.apply()
    # expects.
    arr = np.array(values, dtype=np.float32)
    reshaped = arr.reshape(size, size, size, 3)
    table = np.transpose(reshaped, (2, 1, 0, 3))

    return Lut3D(table, domain_min, domain_max, title)
