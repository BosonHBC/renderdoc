#!/usr/bin/env python3
"""Extract VS input mesh data for one RenderDoc EID.

Outputs an OBJ preview plus lossless sidecar files:
- mesh_<hash>.mesh.json
- mesh_<hash>.attributes.json
- mesh_<hash>.attributes.bin
"""

import argparse
import json
import logging
import os
import struct
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_RDC = Path("D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc")
DEFAULT_EID = 7643
SCRIPT_NAME = Path(globals().get("__file__", "extract_mesh.py")).stem


import inspect as _inspect
_SCRIPT_FILE = _inspect.currentframe().f_code.co_filename
_SCRIPT_DIR = str(Path(_SCRIPT_FILE).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
import app_config  # noqa: E402
PROJECT_ROOT = app_config.PROJECT_ROOT
SCRIPT_DIR = PROJECT_ROOT / "Scripts"
OUTPUT_ROOT = PROJECT_ROOT / "Output"
LOG_DIR = PROJECT_ROOT / "Logs"
TEST_DIR = PROJECT_ROOT / "Tests"
import library_db  # noqa: E402
import rd_session  # noqa: E402
from extract_shaders import resource_format_to_dict  # noqa: E402


def _now_string() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def setup_logger(no_log: bool) -> Tuple[logging.Logger, Optional[Path]]:
    logger = logging.getLogger(SCRIPT_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)
    if no_log:
        return logger, None
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{SCRIPT_NAME}_{_now_string()}.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger, log_path


def enum_to_string(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return repr(value)


def resource_id_to_string(value: Any) -> str:
    try:
        return str(int(value))
    except Exception:
        return str(value)


def is_indexed(rd: Any, action: Any) -> bool:
    try:
        return bool(action.flags & rd.ActionFlags.Indexed)
    except Exception:
        return int(getattr(action, "indexOffset", 0)) >= 0


def safe_format_name(fmt: Any) -> str:
    try:
        return str(fmt.Name())
    except Exception:
        return enum_to_string(fmt)


def bytes_per_element(fmt: Any) -> int:
    try:
        if fmt.Special():
            return max(1, int(getattr(fmt, "byteStride", 0)))
    except Exception:
        pass
    try:
        return int(fmt.compByteWidth) * int(fmt.compCount)
    except Exception:
        return 0


def unpack_data(rd: Any, fmt: Any, data: bytes, data_offset: int) -> Optional[Tuple[Any, ...]]:
    if data_offset < 0 or data_offset >= len(data):
        return None
    try:
        if fmt.Special():
            return None
    except Exception:
        return None

    format_chars = {
        rd.CompType.UInt: "xBHxIxxxQ",
        rd.CompType.SInt: "xbhxixxxq",
        rd.CompType.Float: "xxexfxxxd",
    }
    format_chars[rd.CompType.UNorm] = format_chars[rd.CompType.UInt]
    format_chars[rd.CompType.UScaled] = format_chars[rd.CompType.UInt]
    format_chars[rd.CompType.SNorm] = format_chars[rd.CompType.SInt]
    format_chars[rd.CompType.SScaled] = format_chars[rd.CompType.SInt]

    try:
        comp_type = fmt.compType
        comp_width = int(fmt.compByteWidth)
        comp_count = int(fmt.compCount)
        vertex_format = "=" + str(comp_count) + format_chars[comp_type][comp_width]
        value = struct.unpack_from(vertex_format, data, data_offset)
        if comp_type == rd.CompType.UNorm:
            divisor = float((1 << (comp_width * 8)) - 1)
            value = tuple(float(i) / divisor for i in value)
        elif comp_type == rd.CompType.SNorm:
            max_neg = -(1 << (comp_width * 8 - 1))
            divisor = -float(max_neg + 1)
            value = tuple(-1.0 if i == max_neg else float(i / divisor) for i in value)
        elif comp_type == rd.CompType.UScaled or comp_type == rd.CompType.SScaled:
            value = tuple(float(i) for i in value)
        try:
            if fmt.BGRAOrder():
                value = tuple(value[i] for i in [2, 1, 0, 3])
        except Exception:
            pass
        return value
    except Exception:
        return None


def classify_attribute(name: str) -> str:
    upper = name.upper()
    if (
        "POSITION" in upper
        or upper in ("POS", "ATTRIBUTE", "ATTRIBUTE0")
        or upper.startswith("POSITION")
    ):
        return "position"
    if "NORMAL" in upper:
        return "normal"
    if "TANGENT" in upper:
        return "tangent"
    if "TEXCOORD" in upper or upper.startswith("UV"):
        return "texcoord"
    if "COLOR" in upper:
        return "color"
    return "custom"


def get_indices(rd: Any, controller: Any, action: Any, ib: Any, num_indices: int) -> Tuple[List[int], Dict[str, Any], bytes]:
    indexed = is_indexed(rd, action)
    info = {
        "indexed": indexed,
        "resourceId": resource_id_to_string(getattr(ib, "resourceId", "")),
        "byteOffset": int(getattr(ib, "byteOffset", 0)),
        "byteStride": int(getattr(ib, "byteStride", 0)),
        "indexOffset": int(getattr(action, "indexOffset", 0)),
        "baseVertex": int(getattr(action, "baseVertex", 0)),
    }
    if not indexed or int(getattr(ib, "byteStride", 0)) == 0:
        return list(range(num_indices)), info, b""

    stride = int(ib.byteStride)
    offset = int(ib.byteOffset) + int(action.indexOffset) * stride
    read_size = num_indices * stride
    raw = bytes(controller.GetBufferData(ib.resourceId, offset, read_size))
    fmt = "B" if stride == 1 else "H" if stride == 2 else "I"
    count = int(len(raw) / stride)
    unpacked = struct.unpack_from("=" + str(count) + fmt, raw) if count else []
    base = int(getattr(action, "baseVertex", 0))
    return [int(i) + base for i in unpacked], info, raw


def collect_attributes(pipe: Any, action: Any, extracted_instance: int) -> Tuple[List[Dict[str, Any]], List[Any]]:
    vbs = pipe.GetVBuffers()
    attrs = []
    raw_attrs = []
    for attr in pipe.GetVertexInputs():
        try:
            if not attr.used:
                continue
        except Exception:
            pass
        vb_index = int(attr.vertexBuffer)
        if vb_index < 0 or vb_index >= len(vbs):
            continue
        vb = vbs[vb_index]
        per_instance = bool(getattr(attr, "perInstance", False))
        instance_rate = int(getattr(attr, "instanceRate", 1)) or 1
        vertex_base = int(getattr(action, "vertexOffset", 0))
        instance_base = int(getattr(action, "instanceOffset", 0))
        element_base = vertex_base
        if per_instance:
            element_base = instance_base + int(extracted_instance / max(instance_rate, 1))
        absolute_offset = int(vb.byteOffset) + int(attr.byteOffset) + element_base * int(vb.byteStride)
        meta = {
            "name": str(attr.name),
            "role": classify_attribute(str(attr.name)),
            "vertexBuffer": vb_index,
            "resourceId": resource_id_to_string(vb.resourceId),
            "resourceObj": vb.resourceId,
            "vbByteOffset": int(vb.byteOffset),
            "vbByteSize": int(getattr(vb, "byteSize", 0)),
            "byteOffsetInVertex": int(attr.byteOffset),
            "absoluteByteOffset": absolute_offset,
            "byteStride": int(vb.byteStride),
            "perInstance": per_instance,
            "instanceRate": instance_rate,
            "format": safe_format_name(attr.format),
            "format_detail": resource_format_to_dict(attr.format),
            "elementByteSize": bytes_per_element(attr.format),
            "genericEnabled": bool(getattr(attr, "genericEnabled", False)),
        }
        attrs.append(meta)
        raw_attrs.append(attr)
    return attrs, raw_attrs


def fetch_attribute_ranges(controller: Any, attrs: List[Dict[str, Any]], indices: List[int], extracted_instance: int) -> Tuple[Dict[str, bytes], Dict[str, Dict[str, int]]]:
    ranges: Dict[str, Dict[str, int]] = {}
    if not indices:
        return {}, ranges
    min_index = min(i for i in indices if i is not None)
    max_index = max(i for i in indices if i is not None)
    for attr in attrs:
        rid = attr["resourceId"]
        stride = int(attr["byteStride"])
        elem = max(1, int(attr["elementByteSize"]))
        if attr["perInstance"]:
            begin = int(attr["absoluteByteOffset"])
            end = begin + elem
        else:
            begin = int(attr["absoluteByteOffset"]) + min_index * stride
            end = int(attr["absoluteByteOffset"]) + max_index * stride + elem
        if rid not in ranges:
            ranges[rid] = {"begin": begin, "end": end}
        else:
            ranges[rid]["begin"] = min(ranges[rid]["begin"], begin)
            ranges[rid]["end"] = max(ranges[rid]["end"], end)
    data = {}
    resource_objs = {attr["resourceId"]: attr.get("resourceObj") for attr in attrs}
    for rid, r in ranges.items():
        data[rid] = bytes(controller.GetBufferData(resource_objs[rid], r["begin"], max(0, r["end"] - r["begin"])))
    return data, ranges


def decode_attribute_values(rd: Any, raw_attrs: List[Any], attrs: List[Dict[str, Any]], buffer_data: Dict[str, bytes], ranges: Dict[str, Dict[str, int]], indices: List[int]) -> Tuple[List[Dict[str, Any]], bytes]:
    vertices = []
    blob = bytearray()
    for vertex_id, idx in enumerate(indices):
        vert = {"vertex_id": vertex_id, "index": idx, "attributes": {}}
        for raw_attr, attr in zip(raw_attrs, attrs):
            rid = attr["resourceId"]
            elem = max(1, int(attr["elementByteSize"]))
            if rid not in buffer_data:
                raw = b""
                value = None
            else:
                if attr["perInstance"]:
                    abs_offset = int(attr["absoluteByteOffset"])
                else:
                    abs_offset = int(attr["absoluteByteOffset"]) + int(idx) * int(attr["byteStride"])
                offset = abs_offset - ranges[rid]["begin"]
                raw = buffer_data[rid][offset : offset + elem]
                value = unpack_data(rd, raw_attr.format, buffer_data[rid], offset)
            blob.extend(raw)
            vert["attributes"][attr["name"]] = value
        vertices.append(vert)
    return vertices, bytes(blob)


def choose_attr(attrs: List[Dict[str, Any]], role: str) -> Optional[Dict[str, Any]]:
    for attr in attrs:
        if attr["role"] == role and not attr["perInstance"]:
            return attr
    return None


def build_obj(vertices: List[Dict[str, Any]], attrs: List[Dict[str, Any]], indices: List[int], unit_scale: float) -> str:
    pos_attr = choose_attr(attrs, "position")
    normal_attr = choose_attr(attrs, "normal")
    uv_attr = choose_attr(attrs, "texcoord")
    lines = ["# RenderDocExtract OBJ preview", f"# vertices {len(vertices)}"]
    if pos_attr is None:
        lines.append("# No position-like attribute found; OBJ contains placeholder positions.")
    for v in vertices:
        pos = v["attributes"].get(pos_attr["name"]) if pos_attr else None
        if pos is None or len(pos) < 3:
            lines.append("v 0 0 0")
        else:
            lines.append("v %.9g %.9g %.9g" % (float(pos[0]) * unit_scale, float(pos[1]) * unit_scale, float(pos[2]) * unit_scale))
    if uv_attr:
        for v in vertices:
            uv = v["attributes"].get(uv_attr["name"])
            if uv is None or len(uv) < 2:
                lines.append("vt 0 0")
            else:
                lines.append("vt %.9g %.9g" % (float(uv[0]), 1.0 - float(uv[1])))
    if normal_attr:
        for v in vertices:
            n = v["attributes"].get(normal_attr["name"])
            if n is None or len(n) < 3:
                lines.append("vn 0 0 1")
            else:
                lines.append("vn %.9g %.9g %.9g" % (float(n[0]), float(n[1]), float(n[2])))
    # Treat input as triangle list preview. Non-triangle topologies will still be marked in mesh.json.
    for i in range(0, len(vertices) - 2, 3):
        a, b, c = i + 1, i + 2, i + 3
        if uv_attr and normal_attr:
            lines.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
        elif uv_attr:
            lines.append(f"f {a}/{a} {b}/{b} {c}/{c}")
        elif normal_attr:
            lines.append(f"f {a}//{a} {b}//{b} {c}//{c}")
        else:
            lines.append(f"f {a} {b} {c}")
    return "\n".join(lines) + "\n"


def extract_mesh(args: argparse.Namespace, logger: logging.Logger, log_path: Optional[Path]) -> Dict[str, Any]:
    rd = rd_session.import_renderdoc(args.renderdoc_module_dir, logger)
    rd_session.initialise_replay_if_needed(rd, logger)
    cap = None
    controller = None
    start = time.perf_counter()
    try:
        cap, controller = rd_session.open_capture(rd, args.rdc, logger)
        action, pipe = rd_session.set_eid(controller, args.eid, logger)
        mesh_dir = args.out / "libraries" / "meshes"
        mesh_dir.mkdir(parents=True, exist_ok=True)
        db_path = mesh_dir / "mesh_library.json"

        num_indices = min(int(getattr(action, "numIndices", 0)), int(args.max_indices))
        num_instances = int(getattr(action, "numInstances", 0))
        extracted_instance = 0 if num_instances > 1 else None
        unit_scale = 100.0 if args.unit == "cm" else 1.0
        ib = pipe.GetIBuffer()
        indices, index_info, index_raw = get_indices(rd, controller, action, ib, num_indices)
        attrs, raw_attrs = collect_attributes(pipe, action, 0)
        logger.info("Mesh EID %s: numIndices=%s sampled=%s attrs=%s instances=%s", args.eid, getattr(action, "numIndices", 0), len(indices), len(attrs), num_instances)

        result: Dict[str, Any] = {
            "script": SCRIPT_NAME,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rdc": str(args.rdc),
            "eid": args.eid,
            "out": str(args.out),
            "log_file": str(log_path) if log_path else None,
            "action": rd_session.action_to_summary(rd, controller, action),
            "mesh": None,
            "warnings": [],
        }

        if not attrs:
            result["mesh"] = {"status": "unsupported_vertex_pulling", "reason": "No used vertex input attributes"}
        else:
            buffer_data, ranges = fetch_attribute_ranges(controller, attrs, indices, 0)
            vertices, attr_blob = decode_attribute_values(rd, raw_attrs, attrs, buffer_data, ranges, indices)
            attrs_jsonable = [{k: v for k, v in attr.items() if k != "resourceObj"} for attr in attrs]
            identity = json.dumps(
                {
                    "eid": args.eid,
                    "index_info": index_info,
                    "index_hash": library_db.sha256_bytes(index_raw),
                    "attrs": attrs_jsonable,
                    "ranges": ranges,
                    "unit": args.unit,
                    "num_indices": len(indices),
                },
                sort_keys=True,
            ).encode("utf-8")
            mesh_key = library_db.make_asset_key("mesh", library_db.sha256_bytes(identity))
            prefix = mesh_key
            obj_rel = f"{prefix}.obj"
            mesh_rel = f"{prefix}.mesh.json"
            attr_json_rel = f"{prefix}.attributes.json"
            attr_bin_rel = f"{prefix}.attributes.bin"
            obj_path = mesh_dir / obj_rel
            mesh_path = mesh_dir / mesh_rel
            attr_json_path = mesh_dir / attr_json_rel
            attr_bin_path = mesh_dir / attr_bin_rel

            mesh_manifest = {
                "id": mesh_key,
                "eid": args.eid,
                "status": "ok" if choose_attr(attrs, "position") else "no_position_attribute_preview_only",
                "unit": args.unit,
                "unit_scale": unit_scale,
                "topology": enum_to_string(pipe.GetPrimitiveTopology()),
                "numIndicesOriginal": int(getattr(action, "numIndices", 0)),
                "numIndicesExtracted": len(indices),
                "numInstancesOriginal": num_instances,
                "extracted_instance": extracted_instance,
                "index_buffer": index_info,
                "index_hash": library_db.sha256_bytes(index_raw),
                "attributes": attrs_jsonable,
                "buffer_ranges": ranges,
                "files": {"obj": obj_rel, "mesh_json": mesh_rel, "attributes_json": attr_json_rel, "attributes_bin": attr_bin_rel},
            }
            attr_json = {
                "id": mesh_key,
                "layout": attrs_jsonable,
                "vertices": vertices[: min(len(vertices), args.json_vertex_limit)],
                "vertex_count_full": len(vertices),
                "note": "vertices list may be truncated; attributes.bin contains packed raw attribute bytes in vertex/index order",
            }
            obj_text = build_obj(vertices, attrs, indices, unit_scale)
            obj_path.write_text(obj_text, encoding="utf-8")
            mesh_path.write_text(json.dumps(mesh_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            attr_json_path.write_text(json.dumps(attr_json, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            attr_bin_path.write_bytes(attr_blob)

            item = {
                "id": mesh_key,
                "status": mesh_manifest["status"],
                "unit": args.unit,
                "topology": mesh_manifest["topology"],
                "numIndicesOriginal": mesh_manifest["numIndicesOriginal"],
                "numIndicesExtracted": mesh_manifest["numIndicesExtracted"],
                "numInstancesOriginal": num_instances,
                "extracted_instance": extracted_instance,
                "obj_file": obj_rel,
                "mesh_json": mesh_rel,
                "attributes_json": attr_json_rel,
                "attributes_bin": attr_bin_rel,
                "identity_sha256": mesh_key.split("_", 1)[1],
            }
            registered, created = library_db.register_asset(db_path, mesh_key, item, "mesh", update_existing=True)
            result["mesh"] = dict(item)
            result["mesh"]["created"] = created
            if mesh_manifest["status"] != "ok":
                result["warnings"].append(mesh_manifest["status"])

        result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        args.test_log.parent.mkdir(parents=True, exist_ok=True)
        with args.test_log.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        logger.info("Wrote mesh extraction test log: %s", args.test_log)
        return result
    finally:
        if controller is not None or cap is not None:
            rd_session.close_capture(rd, cap, controller, logger)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    if argv is None and not hasattr(sys, "argv"):
        argv = []
    settings = app_config.with_env_overrides(app_config.load_settings())
    default_eid = int(os.environ.get("RENDERDOC_EXTRACT_EID", settings.eid))
    default_rdc = Path(os.environ.get("RENDERDOC_EXTRACT_RDC", settings.rdc))
    default_out = Path(os.environ.get("RENDERDOC_EXTRACT_OUT", settings.out))
    default_unit = os.environ.get("RENDERDOC_EXTRACT_MESH_UNIT", settings.mesh_unit)
    default_max_indices = app_config.env_int("RENDERDOC_EXTRACT_MESH_MAX_INDICES", settings.mesh_max_indices)
    default_json_vertex_limit = app_config.env_int("RENDERDOC_EXTRACT_JSON_VERTEX_LIMIT", settings.mesh_json_vertex_limit)
    default_no_log = app_config.env_bool("RENDERDOC_EXTRACT_NO_LOG", settings.no_log)
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="Extract VS input mesh for one RenderDoc EID.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--rdc", type=Path, default=default_rdc, help="Path to .rdc capture.")
    parser.add_argument("--eid", type=int, default=default_eid, help="Target event ID.")
    parser.add_argument("--out", type=Path, default=default_out, help="Output root directory.")
    parser.add_argument("--unit", choices=["m", "cm"], default=default_unit, help="Position unit for OBJ preview.")
    parser.add_argument("--max-indices", type=int, default=default_max_indices, help="Safety cap for extracted indices.")
    parser.add_argument("--json-vertex-limit", type=int, default=default_json_vertex_limit, help="Max decoded vertices included in attributes JSON preview.")
    parser.add_argument(
        "--test-log",
        type=Path,
        default=TEST_DIR / f"extract_mesh_eid_{default_eid}.json",
        help="JSON test log output path.",
    )
    parser.add_argument("--renderdoc-module-dir", action="append", default=[], help="RenderDoc Python binding dir.")
    parser.add_argument("--no-log", dest="no_log", action="store_true", default=default_no_log, help="Disable log file output.")
    parser.add_argument("-Nolog", dest="no_log", action="store_true", help="Disable log file output, RenderDoc-style alias.")
    args, unknown = parser.parse_known_args(argv)
    setattr(args, "unknown_args", unknown)
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logger, log_path = setup_logger(args.no_log)
    logger.info("Command line: %s", " ".join(getattr(sys, "argv", [SCRIPT_NAME])))
    if getattr(args, "unknown_args", None):
        logger.info("Ignored unknown host arguments: %s", args.unknown_args)
    logger.info("RDC path: %s", args.rdc)
    logger.info("EID: %s", args.eid)
    logger.info("Output root: %s", args.out)
    logger.info("Unit: %s", args.unit)
    if log_path:
        logger.info("Log path: %s", log_path)
    try:
        result = extract_mesh(args, logger, log_path)
        logger.info("extract_mesh completed: status=%s warnings=%s", result.get("mesh", {}).get("status"), len(result.get("warnings", [])))
        return 0
    except Exception as exc:
        logger.error("extract_mesh failed: %s", exc)
        logger.debug("Full traceback:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__" or "pyrenderdoc" in globals():
    raise SystemExit(main())
