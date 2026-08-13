#!/usr/bin/env python3
"""Reconstruct a Streaming Virtual Texture (SVT) from page table, physical atlases,
and cbuffer constants extracted by RenderDocExtract.

SVT layout rules for EID 7643 (generalised):
  - Page table  : R32G32_UINT 128x128, 8 mip levels. Loaded via _15.Load(int3(px, py, mip)).
  - Physical atlases: _16 (BC3, 60x60 tiles), _17 (BC1, 85x85 tiles).
  - Tile pitch   : 136 px (128 content + 4 border on each side).
  - Each descriptor uint32:
      bits[3:0]  = mip_bits (= page-table mip index this page belongs to; also controls tile size)
      bits[11:4] = tile_x (8-bit if _415=True, 6-bit otherwise)
      bits[19:12]= tile_y (8-bit if _415=True, 6-bit otherwise)  -- for 8-bit mode
   OR bits[15:10]= tile_y for 6-bit mode

  mip_bits meaning:
    A descriptor in page-table mip level pt_mip is VALID only when its mip_bits == pt_mip.
    One physical tile (128px) covers 128 * 2^mip_bits virtual pixels at the base-mip level.

Reconstruction strategy (from coarse to fine, later passes overwrite earlier ones):
  For pt_mip from max_pt_mip down to 0:
    For each page-table entry at this mip level that has mip_bits == pt_mip:
      virtual_region_size = tile_size * (2 ^ pt_mip)   (e.g. mip=2 → 512 virtual px)
      page_origin_vx = local_page_u * tile_size * (2 ^ pt_mip)  (virtual pixel origin)
      page_origin_vy = local_page_v * tile_size * (2 ^ pt_mip)
      For every virtual pixel (vx, vy) in [page_origin_vx, page_origin_vx+virtual_region_size):
        src_px = (vx - page_origin_vx) * tile_size // virtual_region_size  (nearest-neighbour in tile)
        src_py = (vy - page_origin_vy) * tile_size // virtual_region_size
        dst_pixels[vx][vy] = phys_atlas[tile_x * pitch + border + src_px][tile_y * pitch + border + src_py]

  This guarantees:
    - High-mip (coarse) entries fill large blank regions first.
    - Low-mip (fine) entries overwrite with better data.
    - Missing entries stay black.
"""

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


import inspect as _inspect
_SCRIPT_FILE = _inspect.currentframe().f_code.co_filename
_SCRIPT_DIR = str(Path(_SCRIPT_FILE).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
import app_config
PROJECT_ROOT = app_config.PROJECT_ROOT
SCRIPT_DIR = PROJECT_ROOT / "Scripts"
OUTPUT_ROOT = PROJECT_ROOT / "Output"
LOG_DIR = PROJECT_ROOT / "Logs"
TEST_DIR = PROJECT_ROOT / "Tests"
import library_db
from dds_utils import copy_rgba_tile, read_dds_rgba8, write_dds_rgba8

SCRIPT_NAME = Path(__file__).stem
OUTPUT_ROOT = app_config.OUTPUT_ROOT
LOG_DIR = app_config.LOG_DIR
TEST_DIR = app_config.TEST_DIR

DEFAULT_TILE_SIZE = 128
DEFAULT_BORDER = 4
DEFAULT_TILE_PITCH = 136  # 128 + 4 + 4

# texconv search paths (Microsoft DirectXTex)
TEXCONV_SEARCH_PATHS = [
    Path("D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/tools/texconv.exe"),
    Path("C:/Program Files/texconv/texconv.exe"),
]


def find_texconv() -> Optional[Path]:
    found = shutil.which("texconv")
    if found:
        return Path(found)
    for p in TEXCONV_SEARCH_PATHS:
        if p.exists():
            return p
    return None


def compress_dds(src: Path, dxgi_format: str, logger: logging.Logger) -> bool:
    """Convert src DDS to the given DXGI BC format using texconv.
    Overwrites src in-place. Returns True on success."""
    texconv = find_texconv()
    if texconv is None:
        logger.warning("texconv not found; keeping RGBA8 output (format not converted to %s)", dxgi_format)
        return False
    cmd = [
        str(texconv),
        "-f", dxgi_format,
        "-dx10",
        "-y",
        "-m", "0",   # generate full mip chain
        "-o", str(src.parent),
        str(src),
    ]
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("texconv failed: %s", result.stdout + result.stderr)
        return False
    logger.info("texconv OK -> %s (%s)", src.name, dxgi_format)
    return True


# ---------------------------------------------------------------------------
# SVT detection
# ---------------------------------------------------------------------------

SVT_PAGE_PITCHES = (136, 130, 132, 128)  # common vtpage atlas row pitches to probe


def detect_svt(manifest: Dict[str, Any], tile_pitch: int = 136) -> Optional[Dict[str, Any]]:
    """Detect SVT resources in a draw manifest.

    Returns a dict with 'page_table', 'phys_a', 'phys_b' (texture binding records)
    or None if no SVT is detected.

    Detection heuristics:
      page_table : R32G32_UINT format, width AND height <= 256, has multiple mip levels.
      phys_atlas : BC-family format, width or height > 1024,
                   and (width % tile_pitch == 0 or height % tile_pitch == 0).
    """
    textures = manifest.get("resources", {}).get("textures", {}).get("textures", [])
    page_table: Optional[Dict[str, Any]] = None
    phys_candidates: List[Dict[str, Any]] = []

    for t in textures:
        tex = t.get("texture", {})
        fmt: str = tex.get("format", "")
        w: int = int(tex.get("width") or 0)
        h: int = int(tex.get("height") or 0)
        mips: int = int(tex.get("mipCount") or tex.get("numMips") or 1)

        # Page table: small R32G32 texture with multiple mip levels
        if "R32G32" in fmt and w <= 256 and h <= 256:
            page_table = t
            continue

        # Physical atlas: large BC-compressed texture whose size divides tile_pitch
        # Use the specific tile_pitch (default 136), NOT just 128, to avoid
        # matching regular (non-atlas) BC textures that are power-of-2 multiples of 128.
        if fmt.startswith("BC") and (w > 1024 or h > 1024):
            if (w > 0 and w % tile_pitch == 0) or (h > 0 and h % tile_pitch == 0):
                phys_candidates.append(t)

    if page_table is None or len(phys_candidates) == 0:
        return None

    return {
        "page_table": page_table,
        "phys_a": phys_candidates[0] if len(phys_candidates) > 0 else None,
        "phys_b": phys_candidates[1] if len(phys_candidates) > 1 else None,
    }


# ---------------------------------------------------------------------------
# Manifest updater
# ---------------------------------------------------------------------------

def update_manifest_with_svt(
    manifest: Dict[str, Any],
    svt_info: Dict[str, Any],
    recon_result: Dict[str, Any],
    recon_dir: Path,
    tex_root: Path,
) -> Dict[str, Any]:
    """Patch the draw manifest in-place with SVT reconstruction results.

    - phys_a / phys_b library_file → reconstructed DDS (original saved as library_file_original)
    - page_table binding → marked svt_replaced: true
    - Top-level svt_reconstruction summary added
    """
    textures = manifest.get("resources", {}).get("textures", {}).get("textures", [])

    def match_binding(binding: Dict[str, Any], ref: Optional[Dict[str, Any]]) -> bool:
        if ref is None:
            return False
        return (binding.get("shaderResourceName") == ref.get("shaderResourceName")
                or binding.get("library_id") == ref.get("library_id"))

    for t in textures:
        if match_binding(t, svt_info.get("page_table")):
            t["svt_page_table"] = True
        elif match_binding(t, svt_info.get("phys_a")):
            phys_a_result = recon_result.get("physical_a", {})
            if phys_a_result.get("out_file"):
                out_path = Path(phys_a_result["out_file"])
                rel = str(out_path.relative_to(tex_root)).replace("\\", "/")
                t["library_file_original"] = t.get("library_file")
                t["library_file"] = rel
                t["svt_reconstructed"] = True
                t["svt_format"] = phys_a_result.get("format", "BC3_UNORM")
        elif match_binding(t, svt_info.get("phys_b")):
            phys_b_result = recon_result.get("physical_b", {})
            if phys_b_result.get("out_file"):
                out_path = Path(phys_b_result["out_file"])
                rel = str(out_path.relative_to(tex_root)).replace("\\", "/")
                t["library_file_original"] = t.get("library_file")
                t["library_file"] = rel
                t["svt_reconstructed"] = True
                t["svt_format"] = phys_b_result.get("format", "BC1_UNORM")

    manifest["svt_reconstruction"] = {
        "detected": True,
        "virtual_texture_size": recon_result.get("virtual_texture_size"),
        "svt_params": recon_result.get("svt_params"),
        "physical_a": recon_result.get("physical_a"),
        "physical_b": recon_result.get("physical_b"),
        "replacement_hlsl": str(recon_dir / "svt_sampling_replacement.hlsl"),
    }
    return manifest


# ---------------------------------------------------------------------------
# material_slices.hlsl SVT patch
# ---------------------------------------------------------------------------

def _build_svt_sampling_block(
    phys_a_name: str,
    phys_b_name: str,
    original_expr_a: str,
    original_expr_b: str,
) -> str:
    """Build a macro-guarded SVT replacement block for one Sample field."""
    res_a = f"ReconstructedSVT{phys_a_name}"
    res_b = f"ReconstructedSVT{phys_b_name}"
    return (
        f"#if RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT\n"
        f"    // SVT replaced: direct sample from reconstructed virtual texture\n"
        f"    // Original: {original_expr_a}\n"
        f"    // Original: {original_expr_b}\n"
        f"    {{PLACEHOLDER_A}} = {res_a}.SampleLevel(ReconstructedSVT_Sampler, virtual_uv, 0.0f);\n"
        f"    {{PLACEHOLDER_B}} = {res_b}.SampleLevel(ReconstructedSVT_Sampler, virtual_uv, 0.0f);\n"
        f"#else\n"
        f"    // Original SVT page-table path (preserved below):\n"
        f"    {{PLACEHOLDER_A}} = {original_expr_a};\n"
        f"    {{PLACEHOLDER_B}} = {original_expr_b};\n"
        f"#endif"
    )


def patch_material_slices(
    material_slices_path: Path,
    recon_result: Dict[str, Any],
    svt_info: Dict[str, Any],
    svt_params: Dict[str, Any],
    replacement_hlsl_path: Path,
    logger: logging.Logger,
) -> bool:
    """Patch material_slices.hlsl to add macro-controlled SVT sampling.

    Looks for the SampleMaterialTextures() function body, finds lines that
    sample the physical atlas textures (_16.SampleLevel / _17.SampleLevel),
    and wraps them in RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT guards with the
    reconstructed texture as the enabled path.

    Returns True if any replacements were made.
    """
    if not material_slices_path.exists():
        logger.warning("material_slices.hlsl not found; skipping SVT patch: %s", material_slices_path)
        return False

    phys_a_binding = svt_info.get("phys_a") or {}
    phys_b_binding = svt_info.get("phys_b") or {}
    phys_a_res = (phys_a_binding.get("shaderResourceName") or "").replace("Texture2D", "_")
    phys_b_res = (phys_b_binding.get("shaderResourceName") or "").replace("Texture2D", "_")

    text = material_slices_path.read_text(encoding="utf-8")

    # Find the HLSL names for phys_a and phys_b from resource declarations
    # e.g. Texture2D<float4> _16 : register(t3, space0);
    phys_a_library_file = phys_a_binding.get("library_file_original") or phys_a_binding.get("library_file", "")
    phys_b_library_file = phys_b_binding.get("library_file_original") or phys_b_binding.get("library_file", "")

    # Extract HLSL resource names by matching register slot against resource decls
    def find_hlsl_name_by_slot(text: str, slot: int) -> Optional[str]:
        m = re.search(
            rf"(?:Texture\w*<[^>]+>)\s+(_\d+)\s*:\s*register\(t{slot}(?:,\s*space\d+)?\)\s*;",
            text,
        )
        return m.group(1) if m else None

    phys_a_slot = int((phys_a_binding.get("access") or {}).get("index") or 3)
    phys_b_slot = int((phys_b_binding.get("access") or {}).get("index") or 4)
    phys_a_hlsl = find_hlsl_name_by_slot(text, phys_a_slot) or "_16"
    phys_b_hlsl = find_hlsl_name_by_slot(text, phys_b_slot) or "_17"

    logger.info("SVT patch: phys_a=%s (slot t%d) phys_b=%s (slot t%d)", phys_a_hlsl, phys_a_slot, phys_b_hlsl, phys_b_slot)

    pages_u = svt_params.get("pages_per_axis_u", 16)
    pages_v = svt_params.get("pages_per_axis_v", 16)

    # Build virtual_uv helper line
    virtual_uv_decl = (
        "    // SVT virtual UV: frac(TEXCOORD * pages) normalised to [0,1]\n"
        "    float2 virtual_uv = float2(frac(TEXCOORD.x), frac(TEXCOORD.y));\n"
        "#if RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT"
    )

    patched = False
    lines = text.splitlines(keepends=True)
    out_lines: List[str] = []
    in_sample_fn = False
    inserted_virtual_uv = False
    brace_depth = 0

    # Find and patch inside SampleMaterialTextures()
    for i, line in enumerate(lines):
        if "MaterialTextureSamples SampleMaterialTextures()" in line:
            in_sample_fn = True
            inserted_virtual_uv = False
            out_lines.append(line)
            continue

        if in_sample_fn:
            if "{" in line:
                brace_depth += line.count("{")
            if "}" in line:
                brace_depth -= line.count("}")
                if brace_depth < 0:
                    in_sample_fn = False
                    brace_depth = 0
                    out_lines.append(line)
                    continue

            # Inject virtual_uv after the opening brace line
            if not inserted_virtual_uv and brace_depth == 1 and line.strip() == "{":
                out_lines.append(line)
                out_lines.append(
                    "    // SVT virtual UV: frac(TEXCOORD) normalised to [0,1]\n"
                    "    float2 virtual_uv = float2(frac(TEXCOORD.x), frac(TEXCOORD.y));\n"
                )
                inserted_virtual_uv = True
                continue

            # Patch SampleLevel lines for phys_a and phys_b
            if phys_a_hlsl + ".SampleLevel(" in line or phys_b_hlsl + ".SampleLevel(" in line:
                # Determine which physical atlas this line samples
                is_a = phys_a_hlsl + ".SampleLevel(" in line
                rec_name = f"ReconstructedSVT{phys_a_hlsl}" if is_a else f"ReconstructedSVT{phys_b_hlsl}"
                # Extract the assignment target (samples.Sample_N = ...)
                assign_m = re.match(r"(\s*samples\.\w+)\s*=\s*(.*)", line.rstrip())
                if assign_m:
                    lhs = assign_m.group(1)
                    original_rhs = assign_m.group(2).rstrip(";")
                    out_lines.append(
                        f"#if RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT\n"
                        f"    {lhs.strip()} = {rec_name}.SampleLevel(ReconstructedSVT_Sampler, virtual_uv, 0.0f);\n"
                        f"#else\n"
                        f"    {lhs.strip()} = {original_rhs};\n"
                        f"#endif\n"
                    )
                    patched = True
                    continue

        out_lines.append(line)

    if not patched:
        logger.warning("SVT patch: no SampleLevel lines found for %s/%s; HLSL not patched.", phys_a_hlsl, phys_b_hlsl)
        return False

    # Prepend include of replacement HLSL relative path (or inline)
    include_comment = (
        f"// SVT sampling replacement: generated by reconstruct_svt.py\n"
        f"// Macro RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT controls sampling path.\n"
        f"// 1 = use reconstructed virtual texture; 0 = original page-table path.\n"
        f"#ifndef RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT\n"
        f"#define RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT 1\n"
        f"#endif\n"
    )

    # Inject SVT resource declarations (they are in svt_sampling_replacement.hlsl, inline a short version)
    phys_a_res_name = f"ReconstructedSVT{phys_a_hlsl}"
    phys_b_res_name = f"ReconstructedSVT{phys_b_hlsl}"
    svt_decls = (
        f"Texture2D<float4> {phys_a_res_name} : register(t100, space0);\n"
        f"Texture2D<float4> {phys_b_res_name} : register(t101, space0);\n"
        f"SamplerState ReconstructedSVT_Sampler : register(s100, space0);\n"
    )

    # Insert after the "End copied declarations" comment
    final = "".join(out_lines)
    marker = "// ---- End copied declarations ----"
    if marker in final:
        final = final.replace(
            marker,
            f"{marker}\n\n{include_comment}\n{svt_decls}",
            1,
        )
    else:
        final = include_comment + "\n" + svt_decls + "\n" + final

    material_slices_path.write_text(final, encoding="utf-8")
    logger.info("SVT patch applied to %s", material_slices_path.name)
    return True


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(no_log: bool) -> Tuple[logging.Logger, Optional[Path]]:
    logger = logging.getLogger(SCRIPT_NAME)
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    log_path: Optional[Path] = None
    if not no_log:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"{SCRIPT_NAME}_{ts}.log"
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger, log_path


# ---------------------------------------------------------------------------
# DDS mip reader (R32G32_UINT, multi-mip)
# ---------------------------------------------------------------------------

def read_r32g32_uint_all_mips(path: Path) -> List[Tuple[int, int, List[Tuple[int, int]]]]:
    """Return list of (width, height, pairs) for each mip level."""
    data = path.read_bytes()
    if data[:4] != b"DDS ":
        raise ValueError(f"Not a DDS file: {path}")
    header = data[4:128]
    _size, _flags, height, width, _pitch, _depth, mip_count = struct.unpack_from("<IIIIIII", header, 0)
    fourcc = header[72 + 8: 72 + 12]
    data_start = 148 if fourcc == b"DX10" else 128
    mip_count = max(1, mip_count)

    results = []
    offset = data_start
    for m in range(mip_count):
        w = max(1, width >> m)
        h = max(1, height >> m)
        size = w * h * 8  # R32G32 = 8 bytes
        chunk = data[offset: offset + size]
        pairs = [struct.unpack_from("<II", chunk, i * 8) for i in range(w * h)]
        results.append((w, h, pairs))
        offset += size
    return results


# ---------------------------------------------------------------------------
# Cbuffer parameter decode
# ---------------------------------------------------------------------------

def decode_cbuffer_svt_params(cbuffer_path: Path) -> Dict[str, Any]:
    """Extract SVT layout parameters from the PS cbuffer b2 (_36_m0)."""
    raw = cbuffer_path.read_bytes()

    def f(idx: int, comp: int) -> float:
        return struct.unpack_from("<f", raw, idx * 16 + comp * 4)[0]

    def u(idx: int, comp: int) -> int:
        return struct.unpack_from("<I", raw, idx * 16 + comp * 4)[0]

    # _36_m0[0]: x=1.0(uv_scale_u_inv), y=1.0(uv_scale_v_inv), z=_302=pages_u, w=_303=pages_v
    pages_u = f(0, 2)   # _302 = 16.0
    pages_v = f(0, 3)   # _303 = 16.0

    # _36_m0[1]: y=_290 (packed page_base), z: &15 = max_mip
    _290 = u(1, 1)
    page_base_x = _290 & 4095
    page_base_y = (_290 >> 12) & 4095
    max_mip = u(1, 2) & 15

    # _36_m0[2]: w=_411 (atlas pitch UV for _16), y=_413, z=_414, x=_407 fallback color
    _411 = f(2, 3)
    _412 = abs(_411)     # UV step per atlas tile = 1/tiles_per_axis
    _413 = f(2, 1)       # UV step per page within tile
    _414 = f(2, 2)       # UV bias (half-pixel)
    _415 = _411 > 0.0    # True -> 8-bit coords
    _407 = u(2, 0)       # fallback RGBA color for _16 (not loaded)

    # _36_m0[3]: same for _17
    _608 = f(3, 3)
    _609 = abs(_608)
    _610 = f(3, 1)
    _611 = f(3, 2)
    _612 = _608 > 0.0
    _604 = u(3, 0)       # fallback color for _17

    # Infer atlas dimensions
    atlas16_tiles = round(1.0 / _412) if _412 > 0 else 0
    atlas17_tiles = round(1.0 / _609) if _609 > 0 else 0

    return {
        "pages_per_axis_u": int(pages_u),
        "pages_per_axis_v": int(pages_v),
        "page_base_x": page_base_x,
        "page_base_y": page_base_y,
        "max_mip": max_mip,
        "use_8bit_tiles_a": bool(_415),
        "use_8bit_tiles_b": bool(_612),
        "atlas_a_tiles_per_axis": atlas16_tiles,
        "atlas_b_tiles_per_axis": atlas17_tiles,
        "atlas_a_uv_pitch": _412,
        "atlas_a_uv_intra": _413,
        "atlas_a_uv_bias": _414,
        "atlas_b_uv_pitch": _609,
        "atlas_b_uv_intra": _610,
        "atlas_b_uv_bias": _611,
        "fallback_color_a": _407,
        "fallback_color_b": _604,
    }


# ---------------------------------------------------------------------------
# Core reconstruction logic
# ---------------------------------------------------------------------------

def decode_descriptor_a(d: int, params: Dict[str, Any]) -> Tuple[bool, int, int, int]:
    """Decode a _16 page table descriptor.
    Returns (valid, mip_bits, tile_x, tile_y)."""
    if d <= 15:
        return False, 0, 0, 0
    mip_bits = d & 15
    if params["use_8bit_tiles_a"]:
        tx = (d >> 4) & 255
        ty = (d >> 12) & 255
    else:
        tx = (d >> 4) & 63
        ty = (d >> 10) & 63
    return True, mip_bits, tx, ty


def decode_descriptor_b(d: int, params: Dict[str, Any]) -> Tuple[bool, int, int, int]:
    """Decode a _17 page table descriptor."""
    if d <= 15:
        return False, 0, 0, 0
    mip_bits = d & 15
    if params["use_8bit_tiles_b"]:
        tx = (d >> 4) & 255
        ty = (d >> 12) & 255
    else:
        tx = (d >> 4) & 63
        ty = (d >> 10) & 63
    return True, mip_bits, tx, ty


def reconstruct_channel(
    mip_table: List[Tuple[int, int, List[Tuple[int, int]]]],
    phys_pixels: bytes,
    phys_w: int,
    phys_h: int,
    params: Dict[str, Any],
    decode_fn,
    atlas_tiles: int,
    tile_size: int,
    tile_pitch: int,
    border: int,
    logger: logging.Logger,
    channel_name: str,
) -> Tuple[bytearray, Dict[str, int]]:
    """
    Reconstruct a 2D virtual texture using a coarse-to-fine approach.

    Iteration order: from highest pt_mip (coarsest) down to 0 (finest).
    A descriptor at page-table mip level pt_mip is valid ONLY when its
    embedded mip_bits field == pt_mip.  That tile then covers a virtual
    region of (tile_size * 2^pt_mip) × (tile_size * 2^pt_mip) pixels.
    Later (finer) passes overwrite earlier (coarser) data in the same area,
    so the final image uses the highest-resolution data available for each
    virtual pixel.
    """
    pages_u = params["pages_per_axis_u"]
    pages_v = params["pages_per_axis_v"]
    base_x = params["page_base_x"]
    base_y = params["page_base_y"]
    max_pt_mip = len(mip_table) - 1

    out_w = pages_u * tile_size
    out_h = pages_v * tile_size
    out = bytearray(out_w * out_h * 4)  # all black initially

    stats: Dict[str, int] = {"valid": 0, "missing": 0, "oor": 0, "scaled_tiles": 0}

    # Process from coarse (high mip) to fine (mip 0) so finer data overwrites coarser.
    for pt_mip in range(max_pt_mip, -1, -1):
        pt_w, pt_h, pairs = mip_table[pt_mip]
        # At this mip level, one page-table entry covers 2^pt_mip base pages
        pages_per_entry = 1 << pt_mip  # e.g. pt_mip=2 → 4 base-page-sized regions

        for local_pv in range(pages_v):
            for local_pu in range(pages_u):
                # Map base-mip page indices to this mip level
                page_x = (base_x + local_pu) >> pt_mip
                page_y = (base_y + local_pv) >> pt_mip

                # Only process entries where this page is the canonical owner at this mip
                # (i.e. local_pu/local_pv are aligned to the mip block boundary)
                if (local_pu % pages_per_entry) != 0 or (local_pv % pages_per_entry) != 0:
                    continue

                if page_x >= pt_w or page_y >= pt_h:
                    continue

                d_a, d_b = pairs[page_y * pt_w + page_x]
                d = d_a if channel_name == "a" else d_b
                ok, mip_bits, tx, ty = decode_fn(d, params)

                # A descriptor is valid for this pt_mip ONLY when mip_bits == pt_mip.
                if not ok or mip_bits != pt_mip:
                    continue

                # Check tile is within physical atlas bounds.
                if tx >= atlas_tiles or ty >= atlas_tiles:
                    stats["oor"] += 1
                    continue

                # Virtual region this tile covers (in output image coordinates):
                #   origin = local_pu * tile_size  (for pt_mip=0, each page = tile_size)
                #   but for pt_mip=2 this entry covers 4 pages = 4*tile_size virtual pixels
                virt_size = tile_size * pages_per_entry  # e.g. 512 for pt_mip=2
                dst_x0 = local_pu * tile_size
                dst_y0 = local_pv * tile_size
                src_x0 = tx * tile_pitch + border
                src_y0 = ty * tile_pitch + border

                if pt_mip > 0:
                    stats["scaled_tiles"] += 1

                # Blit tile into output with nearest-neighbour upscale.
                # Build a lookup table: virtual dx -> source dx (within tile)
                scale = pages_per_entry  # 2^pt_mip: virtual pixels per physical pixel
                vx_to_src = [min((dx * tile_size) // virt_size, tile_size - 1)
                              for dx in range(virt_size)]
                # Pre-compute a scaled source row for each unique source-y
                # (avoids redundant row computation when scale > 1)
                last_src_vy = -1
                scaled_row: bytearray = bytearray(virt_size * 4)

                for dy in range(virt_size):
                    src_vy = (dy * tile_size) // virt_size
                    dst_y = dst_y0 + dy
                    if dst_y < 0 or dst_y >= out_h:
                        continue
                    src_y = src_y0 + src_vy
                    if src_y >= phys_h:
                        continue

                    # Rebuild scaled_row only when src_vy changes
                    if src_vy != last_src_vy:
                        src_row_base = src_y * phys_w
                        for dx, src_vx in enumerate(vx_to_src):
                            src_x = src_x0 + src_vx
                            if src_x >= phys_w:
                                continue
                            src_off = (src_row_base + src_x) * 4
                            dst_pos = dx * 4
                            scaled_row[dst_pos: dst_pos + 4] = phys_pixels[src_off: src_off + 4]
                        last_src_vy = src_vy

                    # Write scaled_row into the output buffer row
                    dst_row_base = dst_y * out_w
                    clipped_w = min(virt_size, out_w - dst_x0)
                    if clipped_w <= 0:
                        continue
                    dst_off = (dst_row_base + dst_x0) * 4
                    out[dst_off: dst_off + clipped_w * 4] = scaled_row[: clipped_w * 4]

                stats["valid"] += 1

    # Count pages that had no valid entry at any mip level
    for local_pv in range(pages_v):
        for local_pu in range(pages_u):
            # Check if this pixel region is still all-black (never written)
            # Quick heuristic: check one pixel at the centre of the page.
            cx = local_pu * tile_size + tile_size // 2
            cy = local_pv * tile_size + tile_size // 2
            off = (cy * out_w + cx) * 4
            if out[off: off + 4] == b'\x00\x00\x00\x00':
                # May be genuinely black content; we count it as 'missing' only if
                # no descriptor at any mip had mip_bits matching.
                stats["missing"] += 1

    return out, stats


# ---------------------------------------------------------------------------
# HLSL replacement writer
# ---------------------------------------------------------------------------

def write_replacement_hlsl(
    path: Path,
    phys_a_name: str,
    phys_b_name: str,
    virtual_size: int,
    pages_u: int,
    pages_v: int,
    page_base_x: int,
    page_base_y: int,
) -> None:
    res_a = f"ReconstructedSVT{phys_a_name}"
    res_b = f"ReconstructedSVT{phys_b_name}"
    field_a = f"Physical{phys_a_name}"
    field_b = f"Physical{phys_b_name}"
    text = f"""\
// Auto-generated SVT replacement sampling helper.
// EID source: from reconstruct_svt.py
//
// Virtual texture size : {virtual_size}x{virtual_size} px (pages {pages_u}x{pages_v} * tile 128)
// Page table region    : base_x={page_base_x} base_y={page_base_y} in 128x128 shared page table
//
// Define RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT=1 to sample reconstructed virtual textures.
// Without the define the original SVT path (_15 page-table + _16/_17 SampleLevel) is used.
#ifndef RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT
#define RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT 1
#endif

Texture2D<float4> {res_a} : register(t100, space0);
Texture2D<float4> {res_b} : register(t101, space0);
SamplerState ReconstructedSVT_Sampler : register(s100, space0);

struct ReconstructedSVTSamples
{{
    float4 {field_a};
    float4 {field_b};
}};

ReconstructedSVTSamples SampleReconstructedSVT(float2 virtual_uv, float mip)
{{
    ReconstructedSVTSamples s;
#if RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT
    s.{field_a} = {res_a}.SampleLevel(ReconstructedSVT_Sampler, virtual_uv, mip);
    s.{field_b} = {res_b}.SampleLevel(ReconstructedSVT_Sampler, virtual_uv, mip);
#else
    // Original page-table path (keep commented for reference):
    //   uint4 _390 = _15.Load(int3(page_x, page_y, mip_level));
    //   float4 _470 = _16.SampleLevel(_40, atlas_uv(_390.x), 0.0f);
    //   float4 _654 = _17.SampleLevel(_41, atlas_uv(_390.y), 0.0f);
    s.{field_a} = 0;
    s.{field_b} = 0;
#endif
    return s;
}}
"""
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Library registration
# ---------------------------------------------------------------------------

def register_reconstructed_texture(
    library_path: Path,
    dds_path: Path,
    phys_name: str,
    eid: int,
    virtual_size: int,
    stats: Dict[str, int],
) -> str:
    sha = hashlib.sha256(dds_path.read_bytes()).hexdigest()
    rel = str(dds_path.relative_to(library_path.parent)).replace("\\", "/")
    item = {
        "file": rel,
        "sha256": sha,
        "eid": eid,
        "physical_channel": phys_name,
        "virtual_size": virtual_size,
        "kind": "reconstructed_svt",
        "stats": stats,
    }
    key = library_db.make_asset_key("reconstructed_svt", sha[:32])
    registered, _ = library_db.register_asset(library_path, key, item, "texture", update_existing=True)
    return key


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    settings = app_config.with_env_overrides(app_config.load_settings())
    p = argparse.ArgumentParser(prog=SCRIPT_NAME, description="Reconstruct SVT from page table and physical atlas.")
    p.add_argument("--eid", type=int, default=settings.eid)
    p.add_argument("--out", type=Path, default=Path(settings.out))
    p.add_argument("--page-table", default="_15", help="HLSL name of the page table resource.")
    p.add_argument("--physical-a", default="_16", help="HLSL name of physical atlas A.")
    p.add_argument("--physical-b", default="_17", help="HLSL name of physical atlas B.")
    p.add_argument("--tile-size", type=int, default=DEFAULT_TILE_SIZE)
    p.add_argument("--border", type=int, default=DEFAULT_BORDER)
    p.add_argument("--tile-pitch", type=int, default=DEFAULT_TILE_PITCH)
    p.add_argument("--cbuffer-file", type=Path, default=None,
                   help="Override the PS cbuffer b2 bin path.")
    p.add_argument("--no-log", action="store_true", default=settings.no_log)
    p.add_argument("--detect-only", action="store_true", default=False,
                   help="Only detect SVT presence and print result; do not reconstruct.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logger, log_path = setup_logging(args.no_log)

    eid = args.eid
    out_root = args.out
    tile_size = args.tile_size
    border = args.border
    tile_pitch = args.tile_pitch

    manifest_path = out_root / "draws" / f"eid_{eid}" / "draw_manifest.json"
    if not manifest_path.exists():
        logger.error("draw_manifest.json not found: %s", manifest_path)
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # ---- auto-detect SVT in this manifest ----
    svt_detected = detect_svt(manifest, tile_pitch=tile_pitch)
    if svt_detected is None:
        logger.info("No SVT detected in EID %d manifest; skipping SVT reconstruction.", eid)
        print(json.dumps({"eid": eid, "svt_detected": False, "message": "No SVT in manifest"}))
        return 0

    logger.info("SVT detected: page_table=%s  phys_a=%s  phys_b=%s",
                (svt_detected["page_table"] or {}).get("shaderResourceName"),
                (svt_detected.get("phys_a") or {}).get("shaderResourceName"),
                (svt_detected.get("phys_b") or {}).get("shaderResourceName"))

    if args.detect_only:
        result = {
            "eid": eid,
            "svt_detected": True,
            "page_table": svt_detected.get("page_table"),
            "phys_a": svt_detected.get("phys_a"),
            "phys_b": svt_detected.get("phys_b"),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # ---- locate resources from manifest ----
    tex_root = out_root / "libraries" / "textures"
    buf_root = out_root / "libraries" / "buffers"

    def find_texture_file(slot_name: str) -> Optional[Path]:
        for t in manifest["resources"]["textures"]["textures"]:
            if t.get("shaderResourceName") == slot_name and t.get("library_file"):
                return tex_root / t["library_file"]
        return None

    def find_ps_cbuffer_b2() -> Optional[Path]:
        """Find the PS cbuffer at register b2."""
        for b in manifest["resources"]["buffers"]["buffers"]:
            if b.get("stage") == "PS" and b.get("category") == "constant_buffer":
                idx = int(b.get("access", {}).get("index", -1))
                if idx == 2 and b.get("library_file"):
                    return buf_root / b["library_file"]
        return None

    page_table_file = find_texture_file("Texture2D2")   # _15 is t2 slot
    phys_a_file = find_texture_file("Texture2D3")       # _16 is t3
    phys_b_file = find_texture_file("Texture2D4")       # _17 is t4
    cbuffer_file = args.cbuffer_file or find_ps_cbuffer_b2()

    # Fallback: use svt_detected results to locate files by library_file
    if page_table_file is None:
        pt = svt_detected.get("page_table")
        if pt and pt.get("library_file"):
            page_table_file = tex_root / pt["library_file"]
    if phys_a_file is None:
        pa = svt_detected.get("phys_a")
        if pa and pa.get("library_file"):
            phys_a_file = tex_root / pa["library_file"]
    if phys_b_file is None:
        pb = svt_detected.get("phys_b")
        if pb and pb.get("library_file"):
            phys_b_file = tex_root / pb["library_file"]

    logger.info("Page table: %s", page_table_file)
    logger.info("Physical A: %s", phys_a_file)
    logger.info("Physical B: %s", phys_b_file)
    logger.info("CBuffer b2: %s", cbuffer_file)

    if not page_table_file or not page_table_file.exists():
        logger.error("Page table DDS not found")
        return 2
    if not cbuffer_file or not cbuffer_file.exists():
        logger.error("CBuffer b2 not found")
        return 2

    # ---- decode cbuffer SVT params ----
    params = decode_cbuffer_svt_params(cbuffer_file)
    logger.info("SVT params: %s", params)

    pages_u = params["pages_per_axis_u"]
    pages_v = params["pages_per_axis_v"]
    virtual_size_u = pages_u * tile_size
    virtual_size_v = pages_v * tile_size
    logger.info("Virtual texture size: %dx%d", virtual_size_u, virtual_size_v)

    # ---- read page table all mips ----
    logger.info("Reading page table mips...")
    mip_table = read_r32g32_uint_all_mips(page_table_file)
    logger.info("Page table mips: %d (%s)", len(mip_table),
                ", ".join(f"{w}x{h}" for w, h, _ in mip_table))

    # ---- read physical atlases ----
    out_dir = out_root / "draws" / f"eid_{eid}" / "svt_reconstruction"
    out_dir.mkdir(parents=True, exist_ok=True)
    recon_dir = tex_root / "reconstructed_svt"
    recon_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "eid": eid,
        "svt_params": params,
        "virtual_texture_size": {"u": virtual_size_u, "v": virtual_size_v},
        "tile_size": tile_size,
        "border": border,
        "tile_pitch": tile_pitch,
        "page_table_file": str(page_table_file),
        "physical_a": {},
        "physical_b": {},
        "replacement_hlsl": str(out_dir / "svt_sampling_replacement.hlsl"),
    }

    library_path = tex_root / "texture_library.json"

    def reconstruct_one(
        phys_file: Optional[Path],
        channel_name: str,
        decode_fn,
        atlas_tiles: int,
        out_key: str,
        res_name: str,
        target_dxgi_format: str,
    ) -> None:
        if not phys_file or not phys_file.exists():
            logger.warning("Physical atlas %s not found, skipping.", phys_file)
            result[out_key] = {"error": "file not found"}
            return

        logger.info("Reading physical atlas %s ...", phys_file.name)
        img = read_dds_rgba8(phys_file)
        logger.info("Atlas: %dx%d fmt=%s", img.width, img.height, img.format)

        logger.info("Reconstructing channel %s ...", channel_name)
        out_pixels, stats = reconstruct_channel(
            mip_table, img.pixels, img.width, img.height,
            params, decode_fn, atlas_tiles,
            tile_size, tile_pitch, border, logger, channel_name,
        )
        logger.info("Stats %s: %s", channel_name, stats)

        out_file = recon_dir / f"eid_{eid}_{res_name}_virtual.dds"
        # Write RGBA8 first, then compress to target BC format via texconv
        write_dds_rgba8(out_file, virtual_size_u, virtual_size_v, out_pixels)
        logger.info("Written RGBA8: %s (%dx%d)", out_file.name, virtual_size_u, virtual_size_v)

        compressed = compress_dds(out_file, target_dxgi_format, logger)
        final_format = target_dxgi_format if compressed else "R8G8B8A8_UNORM"
        logger.info("Final format: %s", final_format)

        library_key = register_reconstructed_texture(
            library_path, out_file, res_name, eid,
            max(virtual_size_u, virtual_size_v), stats,
        )
        result[out_key] = {
            "out_file": str(out_file),
            "out_size": f"{virtual_size_u}x{virtual_size_v}",
            "format": final_format,
            "stats": stats,
            "library_key": library_key,
        }

    # _16 physical atlas: BC3_UNORM (used as normal/mask data, linear)
    # _17 physical atlas: BC1_UNORM (used as color data, linear in this shader)
    reconstruct_one(phys_a_file, "a", decode_descriptor_a,
                    params["atlas_a_tiles_per_axis"], "physical_a", args.physical_a,
                    "BC3_UNORM")
    reconstruct_one(phys_b_file, "b", decode_descriptor_b,
                    params["atlas_b_tiles_per_axis"], "physical_b", args.physical_b,
                    "BC1_UNORM")

    # ---- write replacement HLSL ----
    write_replacement_hlsl(
        out_dir / "svt_sampling_replacement.hlsl",
        args.physical_a, args.physical_b,
        max(virtual_size_u, virtual_size_v),
        pages_u, pages_v,
        params["page_base_x"], params["page_base_y"],
    )

    # ---- save reconstruction JSON ----
    recon_json = out_dir / "svt_reconstruction.json"
    recon_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("Reconstruction JSON: %s", recon_json)

    # ---- update draw_manifest.json ----
    manifest = update_manifest_with_svt(manifest, svt_detected, result, out_dir, tex_root)
    import tempfile as _tempfile
    manifest_tmp = manifest_path.with_suffix(".tmp")
    manifest_tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_tmp.replace(manifest_path)
    logger.info("draw_manifest.json updated with SVT reconstruction references.")

    # ---- patch material_slices.hlsl with SVT macro guards ----
    material_slices_path = out_root / "draws" / f"eid_{eid}" / "material_slices.hlsl"
    patch_result = patch_material_slices(
        material_slices_path,
        result,
        svt_detected,
        params,
        out_dir / "svt_sampling_replacement.hlsl",
        logger,
    )
    result["material_slices_patched"] = patch_result

    result["svt_detected"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__" or "pyrenderdoc" in globals():
    raise SystemExit(main())
