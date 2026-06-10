#!/usr/bin/env python3
"""Minimal DDS reader/writer helpers for RenderDocExtract.

Supported reads: R32G32_UINT, BC1/DXT1, BC3/DXT5.
Supported writes: uncompressed RGBA8 DDS.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Dict, List, Tuple

DDS_MAGIC = b"DDS "
DDSD_CAPS = 0x1
DDSD_HEIGHT = 0x2
DDSD_WIDTH = 0x4
DDSD_PITCH = 0x8
DDSD_PIXELFORMAT = 0x1000
DDSD_LINEARSIZE = 0x80000
DDSCAPS_TEXTURE = 0x1000
DDPF_ALPHAPIXELS = 0x1
DDPF_FOURCC = 0x4
DDPF_RGB = 0x40


@dataclass
class DDSImage:
    width: int
    height: int
    format: str
    pixels: bytes | None = None
    u32_pairs: List[Tuple[int, int]] | None = None
    mip_count: int = 1


def read_dds_header(path: Path) -> Dict[str, int | str]:
    data = path.read_bytes()
    if len(data) < 128 or data[:4] != DDS_MAGIC:
        raise ValueError(f"Not a DDS file: {path}")
    header = data[4:128]
    size = struct.unpack_from("<I", header, 0)[0]
    if size != 124:
        raise ValueError(f"Unsupported DDS header size {size}: {path}")
    flags, height, width, pitch_or_linear, depth, mip_count = struct.unpack_from("<IIIIII", header, 4)
    pf_off = 72
    pf_size, pf_flags = struct.unpack_from("<II", header, pf_off)
    fourcc = header[pf_off + 8: pf_off + 12]
    rgb_bits, r_mask, g_mask, b_mask, a_mask = struct.unpack_from("<IIIII", header, pf_off + 12)
    fmt = "UNKNOWN"
    if pf_flags & DDPF_FOURCC:
        if fourcc == b"DXT1":
            fmt = "BC1"
        elif fourcc == b"DXT5":
            fmt = "BC3"
        elif fourcc == b"DX10":
            if len(data) < 148:
                raise ValueError(f"Missing DX10 DDS header: {path}")
            dxgi_format = struct.unpack_from("<I", data, 128)[0]
            if dxgi_format == 17:
                fmt = "R32G32_UINT"
            elif dxgi_format == 71:
                fmt = "BC1_UNORM"
            elif dxgi_format == 72:
                fmt = "BC1_UNORM_SRGB"
            elif dxgi_format == 77:
                fmt = "BC3_UNORM"
            elif dxgi_format == 78:
                fmt = "BC3_UNORM_SRGB"
            else:
                fmt = f"DX10_{dxgi_format}"
    elif pf_flags & DDPF_RGB:
        if rgb_bits == 32 and r_mask == 0x000000FF and g_mask == 0x0000FF00 and b_mask == 0x00FF0000 and a_mask == 0xFF000000:
            fmt = "R8G8B8A8_UNORM"
    return {
        "width": width,
        "height": height,
        "mip_count": mip_count or 1,
        "format": fmt,
        "data_offset": 148 if fourcc == b"DX10" else 128,
        "pitch_or_linear": pitch_or_linear,
        "flags": flags,
    }


def _rgb565(c: int) -> Tuple[int, int, int, int]:
    r = ((c >> 11) & 31) * 255 // 31
    g = ((c >> 5) & 63) * 255 // 63
    b = (c & 31) * 255 // 31
    return r, g, b, 255


def _decode_bc1_block(block: bytes) -> List[Tuple[int, int, int, int]]:
    c0, c1, bits = struct.unpack_from("<HHI", block, 0)
    colors = [_rgb565(c0), _rgb565(c1)]
    if c0 > c1:
        colors.append(tuple((2 * colors[0][i] + colors[1][i]) // 3 for i in range(4)))
        colors.append(tuple((colors[0][i] + 2 * colors[1][i]) // 3 for i in range(4)))
    else:
        colors.append(tuple((colors[0][i] + colors[1][i]) // 2 for i in range(4)))
        colors.append((0, 0, 0, 0))
    out = []
    for i in range(16):
        out.append(colors[(bits >> (2 * i)) & 0x3])
    return out


def _decode_bc3_alpha(block: bytes) -> List[int]:
    a0 = block[0]
    a1 = block[1]
    code = int.from_bytes(block[2:8], "little")
    table = [a0, a1]
    if a0 > a1:
        for i in range(1, 7):
            table.append(((7 - i) * a0 + i * a1) // 7)
    else:
        for i in range(1, 5):
            table.append(((5 - i) * a0 + i * a1) // 5)
        table.extend([0, 255])
    return [table[(code >> (3 * i)) & 0x7] for i in range(16)]


def _decode_bc_image(data: bytes, width: int, height: int, bc: str) -> bytearray:
    out = bytearray(width * height * 4)
    block_w = (width + 3) // 4
    block_h = (height + 3) // 4
    offset = 0
    block_size = 8 if bc == "BC1" else 16
    for by in range(block_h):
        for bx in range(block_w):
            block = data[offset: offset + block_size]
            offset += block_size
            if bc == "BC1":
                pixels = _decode_bc1_block(block)
            else:
                alpha = _decode_bc3_alpha(block[:8])
                pixels = _decode_bc1_block(block[8:16])
                pixels = [(r, g, b, alpha[i]) for i, (r, g, b, _a) in enumerate(pixels)]
            for py in range(4):
                y = by * 4 + py
                if y >= height:
                    continue
                for px in range(4):
                    x = bx * 4 + px
                    if x >= width:
                        continue
                    r, g, b, a = pixels[py * 4 + px]
                    dst = (y * width + x) * 4
                    out[dst: dst + 4] = bytes((r, g, b, a))
    return out


def read_dds_rgba8(path: Path) -> DDSImage:
    header = read_dds_header(path)
    data = path.read_bytes()[int(header["data_offset"]):]
    width = int(header["width"])
    height = int(header["height"])
    fmt = str(header["format"])
    if fmt.startswith("BC1") or fmt == "BC1":
        pixels = bytes(_decode_bc_image(data, width, height, "BC1"))
    elif fmt.startswith("BC3") or fmt == "BC3":
        pixels = bytes(_decode_bc_image(data, width, height, "BC3"))
    elif fmt == "R8G8B8A8_UNORM":
        pixels = data[: width * height * 4]
    else:
        raise ValueError(f"Unsupported DDS RGBA read format {fmt}: {path}")
    return DDSImage(width=width, height=height, format=fmt, pixels=pixels, mip_count=int(header["mip_count"]))


def read_dds_r32g32_uint(path: Path) -> DDSImage:
    header = read_dds_header(path)
    if str(header["format"]) != "R32G32_UINT":
        raise ValueError(f"Expected R32G32_UINT DDS, got {header['format']}: {path}")
    width = int(header["width"])
    height = int(header["height"])
    data = path.read_bytes()[int(header["data_offset"]):]
    count = width * height
    pairs = [struct.unpack_from("<II", data, i * 8) for i in range(count)]
    return DDSImage(width=width, height=height, format="R32G32_UINT", u32_pairs=pairs, mip_count=int(header["mip_count"]))


def write_dds_rgba8(path: Path, width: int, height: int, pixels: bytes | bytearray) -> None:
    if len(pixels) < width * height * 4:
        raise ValueError("Not enough RGBA8 pixels")
    path.parent.mkdir(parents=True, exist_ok=True)
    pitch = width * 4
    header = bytearray()
    header += DDS_MAGIC
    header += struct.pack("<I", 124)
    header += struct.pack("<I", DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PITCH | DDSD_PIXELFORMAT)
    header += struct.pack("<I", height)
    header += struct.pack("<I", width)
    header += struct.pack("<I", pitch)
    header += struct.pack("<I", 0)  # depth
    header += struct.pack("<I", 1)  # mip count
    header += bytes(44)
    header += struct.pack("<I", 32)
    header += struct.pack("<I", DDPF_RGB | DDPF_ALPHAPIXELS)
    header += bytes(4)  # fourcc
    header += struct.pack("<I", 32)
    header += struct.pack("<I", 0x000000FF)
    header += struct.pack("<I", 0x0000FF00)
    header += struct.pack("<I", 0x00FF0000)
    header += struct.pack("<I", 0xFF000000)
    header += struct.pack("<I", DDSCAPS_TEXTURE)
    header += struct.pack("<I", 0)
    header += struct.pack("<I", 0)
    header += struct.pack("<I", 0)
    header += struct.pack("<I", 0)
    if len(header) != 128:
        raise AssertionError(len(header))
    with path.open("wb") as f:
        f.write(header)
        f.write(bytes(pixels[: width * height * 4]))


def copy_rgba_tile(src: bytes, src_w: int, src_h: int, sx: int, sy: int, dst: bytearray, dst_w: int, dst_h: int, dx: int, dy: int, size: int) -> bool:
    if sx < 0 or sy < 0 or dx < 0 or dy < 0:
        return False
    if sx + size > src_w or sy + size > src_h or dx + size > dst_w or dy + size > dst_h:
        return False
    row_bytes = size * 4
    for row in range(size):
        src_off = ((sy + row) * src_w + sx) * 4
        dst_off = ((dy + row) * dst_w + dx) * 4
        dst[dst_off: dst_off + row_bytes] = src[src_off: src_off + row_bytes]
    return True
