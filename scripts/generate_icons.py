"""Gera os ícones geométricos da PWA em PNG, sem dependências externas."""

from pathlib import Path
import struct
import zlib


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def icon(size: int) -> bytes:
    rows = bytearray()
    bars = [(19, 27, 37), (28, 19, 45), (37, 24, 40), (46, 28, 36)]
    for y in range(size):
        rows.append(0)
        sy = (y + 0.5) * 64 / size
        for x in range(size):
            sx = (x + 0.5) * 64 / size
            inside = any(
                (sx - center) ** 2 + (sy - min(max(sy, top), bottom)) ** 2 <= 2.2 ** 2
                for center, top, bottom in bars
            )
            rows.extend((217, 243, 206) if inside else (18, 78, 70))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "frontend" / "public"
    target.mkdir(parents=True, exist_ok=True)
    for filename, size in (("icon-192.png", 192), ("icon-512.png", 512), ("icon-maskable.png", 512)):
        (target / filename).write_bytes(icon(size))
