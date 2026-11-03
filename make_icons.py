# -*- coding: utf-8 -*-
"""生成 PWA 图标（纯标准库手写 PNG，不依赖 Pillow）。"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).parent / "static"


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(
        ">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _point_in_poly(x: float, y: float, pts: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def make_png(path: Path, size: int) -> None:
    W = H = size
    rr = size * 0.22
    cx = cy = size / 2.0
    R_out, R_in = size * 0.30, size * 0.128
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = R_out if i % 2 == 0 else R_in
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))

    raw = bytearray()
    for y in range(H):
        raw.append(0)  # filter type 0
        for x in range(W):
            # 圆角矩形遮罩
            dx = dy = 0.0
            if x < rr and y < rr:
                dx, dy = x - rr, y - rr
            elif x > W - 1 - rr and y < rr:
                dx, dy = x - (W - 1 - rr), y - rr
            elif x < rr and y > H - 1 - rr:
                dx, dy = x - rr, y - (H - 1 - rr)
            elif x > W - 1 - rr and y > H - 1 - rr:
                dx, dy = x - (W - 1 - rr), y - (H - 1 - rr)
            if dx or dy:
                if dx * dx + dy * dy > rr * rr:
                    raw += bytes((0, 0, 0, 0))
                    continue

            if _point_in_poly(x, y, pts):
                t = y / H
                raw += bytes((int(255), int(211 - 26 * t), int(78 - 40 * t), 255))
            else:
                t = (x + y) / (W + H)
                raw += bytes((int(108 + 34 * t), int(92 + 28 * t),
                              int(231 - 8 * t), 255))

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
           + _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _chunk(b"IEND", b""))
    path.write_bytes(png)
    print(f"  {path.name}  {size}x{size}  {len(png)/1024:.1f} KB")


if __name__ == "__main__":
    print("生成 PWA 图标：")
    for s in (180, 192, 512):
        make_png(OUT / f"icon-{s}.png", s)
