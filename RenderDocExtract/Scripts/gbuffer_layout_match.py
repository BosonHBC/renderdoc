#!/usr/bin/env python3
"""Generic GBuffer layout matcher for PS HLSL + RenderDoc RT metadata."""

import argparse
import json
import math
import re
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path("D:/UGit/renderdoc/RenderDocExtract")
DEFAULT_LAYOUTS = PROJECT_ROOT / "Config" / "gbuffer_layouts.json"
SCRIPT_NAME = Path(globals().get("__file__", "gbuffer_layout_match.py")).stem

SV_TARGET_RE = re.compile(r"\bSV_Target\s*(\d*)\b", re.IGNORECASE)
STRUCT_RE = re.compile(r"struct\s+(\w+)\s*\{(?P<body>.*?)\};", re.IGNORECASE | re.DOTALL)
FIELD_RE = re.compile(r"(?P<type>[A-Za-z0-9_<>]+)\s+(?P<name>[A-Za-z0-9_]+)\s*:\s*(?P<semantic>SV_Target\d*)\s*;", re.IGNORECASE)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_format(fmt: str) -> str:
    s = str(fmt or "").upper()
    aliases = {
        "A2B10G10R10_UNORM": "R10G10B10A2_UNORM",
        "R8G8B8A8_UNORM": "B8G8R8A8_UNORM",
        "R8G8B8A8_SRGB": "B8G8R8A8_SRGB",
        "RGBA16F": "R16G16B16A16_FLOAT",
        "RGBA16_FLOAT": "R16G16B16A16_FLOAT",
        "RGBA16_UNORM": "R16G16B16A16_UNORM",
        "RG16_UNORM": "R16G16_UNORM",
        "RG16F": "R16G16_FLOAT",
    }
    return aliases.get(s, s)


def analyze_hlsl_text(text: str) -> Dict[str, Any]:
    targets = []
    fields = []
    for struct in STRUCT_RE.finditer(text):
        struct_name = struct.group(1)
        body = struct.group("body")
        for field in FIELD_RE.finditer(body):
            sem = field.group("semantic")
            m = SV_TARGET_RE.search(sem)
            index = int(m.group(1) or 0) if m else 0
            fields.append({
                "struct": struct_name,
                "type": field.group("type"),
                "name": field.group("name"),
                "semantic": sem,
                "index": index,
            })
            targets.append(index)
    # Fallback: search all SV_Target tokens if struct parsing misses decompiler style.
    if not targets:
        for m in SV_TARGET_RE.finditer(text):
            targets.append(int(m.group(1) or 0))
    unique_targets = sorted(set(targets))
    return {
        "sv_target_indices": unique_targets,
        "sv_target_count": len(unique_targets),
        "output_fields": sorted(fields, key=lambda x: x["index"]),
        "contains_discard_or_clip": bool(re.search(r"\b(discard|clip\s*\()", text, re.IGNORECASE)),
    }


def analyze_hlsl(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {"error": f"HLSL file missing: {path}", "sv_target_indices": [], "sv_target_count": 0, "output_fields": []}
    return analyze_hlsl_text(path.read_text(encoding="utf-8", errors="ignore"))


def layout_slot_match(actual_format: str, slot: Dict[str, Any]) -> bool:
    actual = normalize_format(actual_format)
    return actual in {normalize_format(f) for f in slot.get("formats", [])}


def score_layout(layout: Dict[str, Any], actual_rts: List[Dict[str, Any]], hlsl_info: Dict[str, Any]) -> Dict[str, Any]:
    slots = layout.get("render_targets", [])
    actual_count = len(actual_rts)
    hlsl_count = int(hlsl_info.get("sv_target_count") or 0)
    compared = min(len(slots), actual_count)
    slot_results = []
    format_matches = 0
    for i in range(compared):
        actual_format = actual_rts[i].get("format") or actual_rts[i].get("format_detail", {}).get("name")
        slot = slots[i]
        ok = layout_slot_match(actual_format, slot)
        if ok:
            format_matches += 1
        slot_results.append({
            "index": i,
            "actual_format": actual_format,
            "layout_name": slot.get("name"),
            "layout_semantic": slot.get("semantic"),
            "expected_formats": slot.get("formats", []),
            "format_match": ok,
        })
    count_match = actual_count == int(layout.get("rt_count", len(slots)))
    hlsl_count_match = (hlsl_count == 0) or (hlsl_count == actual_count)
    exact_match = count_match and hlsl_count_match and format_matches == actual_count and compared == actual_count
    return {
        "layout_id": layout.get("layout_id"),
        "description": layout.get("description"),
        "params": layout.get("params", {}),
        "layout_rt_count": int(layout.get("rt_count", len(slots))),
        "actual_rt_count": actual_count,
        "hlsl_sv_target_count": hlsl_count,
        "count_match": count_match,
        "hlsl_count_match": hlsl_count_match,
        "format_match_count": format_matches,
        "compared_rt_count": compared,
        "exact_match": exact_match,
        "slot_results": slot_results,
        "score_tuple": [1 if exact_match else 0, 1 if count_match else 0, format_matches, -abs(int(layout.get("rt_count", len(slots))) - actual_count)],
    }


def choose_layout(layouts: List[Dict[str, Any]], actual_rts: List[Dict[str, Any]], hlsl_info: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [score_layout(layout, actual_rts, hlsl_info) for layout in layouts]
    candidates.sort(key=lambda c: tuple(c["score_tuple"]), reverse=True)
    selected = candidates[0] if candidates else None
    reason = "no_layouts"
    if selected:
        if selected["exact_match"]:
            reason = "exact_count_and_format_match"
        elif selected["count_match"]:
            reason = "same_rt_count_best_format_match"
        else:
            reason = "fallback_best_format_match_count"
    return {
        "selected_layout_id": selected.get("layout_id") if selected else None,
        "selected_reason": reason,
        "selected": selected,
        "candidate_count": len(candidates),
        "top_candidates": candidates[: min(5, len(candidates))],
        "hlsl_analysis": hlsl_info,
    }


def match_gbuffer_layout(layout_path: Path, hlsl_path: Optional[Path], render_targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    data = read_json(layout_path)
    hlsl_info = analyze_hlsl(hlsl_path)
    result = choose_layout(data.get("layouts", []), render_targets, hlsl_info)
    result["layout_file"] = str(layout_path)
    result["actual_render_targets"] = [
        {"index": rt.get("index", i), "resourceId": rt.get("resourceId"), "format": rt.get("format")}
        for i, rt in enumerate(render_targets)
    ]
    return result


def get_layout(data: Dict[str, Any], layout_id: str) -> Dict[str, Any]:
    for layout in data.get("layouts", []):
        if layout.get("layout_id") == layout_id:
            return layout
    raise KeyError(f"Unknown layout_id: {layout_id}")


def get_rt_info(data: Dict[str, Any], layout_id: str, rt_index: int) -> Dict[str, Any]:
    layout = get_layout(data, layout_id)
    for rt in layout.get("render_targets", []):
        if int(rt.get("index", -1)) == int(rt_index):
            schema = data.get("channel_schemas", {}).get(rt.get("channel_schema") or rt.get("semantic"), {})
            out = dict(rt)
            out["channel_schema_detail"] = schema
            return out
    raise KeyError(f"RT{rt_index} not found in {layout_id}")


def get_channel_info(data: Dict[str, Any], layout_id: str, rt_index: int, channel: str) -> Dict[str, Any]:
    rt = get_rt_info(data, layout_id, rt_index)
    ch = channel.upper()
    schema = rt.get("channel_schema_detail", {})
    info = schema.get("channels", {}).get(ch)
    if info is None:
        raise KeyError(f"Channel {ch} not defined for {layout_id} RT{rt_index}")
    return {"layout_id": layout_id, "rt_index": rt_index, "rt_name": rt.get("name"), "rt_semantic": rt.get("semantic"), "channel": ch, "channel_info": info, "schema_description": schema.get("description"), "shading_model_table": schema.get("shading_model_table")}


def _to_byte(v: Any) -> int:
    x = float(v)
    if 0.0 <= x <= 1.0:
        return max(0, min(255, int(round(x * 255.0))))
    return max(0, min(255, int(round(x))))


def _to_unorm16(v: Any) -> int:
    x = float(v)
    if 0.0 <= x <= 1.0:
        return max(0, min(65535, int(round(x * 65535.0))))
    return max(0, min(65535, int(round(x))))


def _asfloat_u32(u: int) -> float:
    return struct.unpack("=f", struct.pack("=I", u & 0xFFFFFFFF))[0]


def decode_channel_value(decode: str, value: Any = None, pixel: Optional[Dict[str, Any]] = None, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options = options or {}
    pixel = pixel or {}
    if decode == "identity":
        return {"decoded": value}
    if decode == "encoded_normal_component":
        x = float(value)
        return {"decoded": x * 2.0 - 1.0}
    if decode == "srgb_to_linear_optional":
        x = float(value)
        if x <= 0.04045:
            lin = x / 12.92
        else:
            lin = ((x + 0.055) / 1.055) ** 2.4
        return {"encoded_srgb": x, "linear": lin}
    if decode == "indirect_irradiance_log2_or_ao":
        x = float(value)
        return {"encoded": x, "approx_indirect_irradiance_times_ao": math.exp2((x - 0.5) * 16.0) - math.exp2(-8.0), "also_possible": "AO or diffuse sample occlusion depending compile flags"}
    if decode == "per_object_gbuffer_data_2bit":
        b = max(0, min(3, int(round(float(value) * 3.0)) if 0.0 <= float(value) <= 1.0 else int(value)))
        return {"packed": b, "CastContactShadow": bool(b & 1), "HasDynamicIndirectShadowCasterRepresentation": bool(b & 2)}
    if decode == "gbuffer_b_alpha_packed":
        b = _to_byte(value)
        shading_models = {0:"Unlit",1:"DefaultLit",2:"Subsurface",3:"PreintegratedSkin",4:"ClearCoat",5:"SubsurfaceProfile",6:"TwoSidedFoliage",7:"Hair",8:"Cloth",9:"Eye",10:"SingleLayerWater",11:"ThinTranslucent",12:"Substrate"}
        sm = b & 0x0F
        mask = (b >> 4) & 0x0F
        return {"packed_byte": b, "ShadingModelID": sm, "ShadingModel": shading_models.get(sm, "Unknown"), "SelectiveOutputMask": mask, "HAS_ANISOTROPY_MASK": bool(b & 0x10), "SKIP_PRECSHADOW_MASK": bool(b & 0x20), "ZERO_PRECSHADOW_or_IS_FIRST_PERSON": bool(b & 0x40), "SKIP_VELOCITY_MASK": bool(b & 0x80)}
    if decode == "velocity_xy":
        x = float(value)
        bias = 32767.0 / 65535.0
        encoded_linear = (x - bias) / 0.2495
        gamma_decoded = (encoded_linear * abs(encoded_linear)) * 0.5
        return {"encoded": x, "linear_without_gamma_decode": encoded_linear, "gamma_decoded_velocity": gamma_decoded}
    if decode in ("velocity_depth_high16", "velocity_depth_low16_flags"):
        z = _to_unorm16(pixel.get("B", 0))
        w = _to_unorm16(pixel.get("A", value if value is not None else 0))
        low_mask = int(options.get("velocity_z_low_mask", 0xFFFC))
        temporal_mask = int(options.get("temporal_responsiveness_mask", 0x3))
        u = ((z & 0xFFFF) << 16) | (w & low_mask)
        return {"high16": z, "low16_raw": w, "low_mask": low_mask, "pixel_animation_flag": bool(w & 0x1), "temporal_responsiveness_flag": bool(w & 0x2) if temporal_mask & 0x2 else None, "device_z_delta": _asfloat_u32(u), "combined_u32_hex": f"0x{u:08X}"}
    if decode == "custom_data_by_shading_model":
        sm = options.get("shading_model_id")
        return {"raw": value, "requires_shading_model_id": sm is None, "shading_model_id": sm, "note": "Interpret using channel_info.shading_model_table and GBufferB.A unpack result."}
    return {"raw": value, "warning": f"No decoder implemented for {decode}"}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=SCRIPT_NAME, description="Match/query UE GBuffer layouts.")
    sub = parser.add_subparsers(dest="command")

    match = sub.add_parser("match", help="Match PS HLSL and RT formats to a known GBuffer layout.")
    match.add_argument("--layouts", type=Path, default=DEFAULT_LAYOUTS)
    match.add_argument("--hlsl", type=Path, required=True)
    match.add_argument("--render-targets-json", type=Path, required=True, help="JSON file containing a render_targets array or full manifest/test JSON.")
    match.add_argument("--out", type=Path, default=None)

    query = sub.add_parser("query", help="Query a layout RT/channel semantic and unpack rule.")
    query.add_argument("--layouts", type=Path, default=DEFAULT_LAYOUTS)
    query.add_argument("--layout-id", required=True)
    query.add_argument("--rt", type=int, required=True)
    query.add_argument("--channel", required=True)
    query.add_argument("--value", default=None, help="Optional numeric channel value for decode.")
    query.add_argument("--pixel", default=None, help="Optional JSON object with R/G/B/A values for packed multi-channel decode.")
    query.add_argument("--options", default=None, help="Optional JSON object, e.g. {\"shading_model_id\":7} or velocity masks.")
    query.add_argument("--out", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.error("command required: match or query")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.command == "match":
        rt_json = read_json(args.render_targets_json)
        render_targets = rt_json.get("render_targets") or rt_json.get("pipeline", {}).get("render_targets") or []
        result = match_gbuffer_layout(args.layouts, args.hlsl, render_targets)
    else:
        data = read_json(args.layouts)
        result = get_channel_info(data, args.layout_id, args.rt, args.channel)
        if args.value is not None:
            pixel = json.loads(args.pixel) if args.pixel else None
            options = json.loads(args.options) if args.options else None
            result["decoded_value"] = decode_channel_value(result["channel_info"].get("decode"), args.value, pixel, options)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
