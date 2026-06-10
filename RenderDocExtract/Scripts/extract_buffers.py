#!/usr/bin/env python3
"""Extract VS/PS buffer resources for one RenderDoc EID."""

import argparse
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path("D:/UGit/renderdoc/RenderDocExtract")
SCRIPT_DIR = PROJECT_ROOT / "Scripts"
OUTPUT_ROOT = PROJECT_ROOT / "Output"
LOG_DIR = PROJECT_ROOT / "Logs"
TEST_DIR = PROJECT_ROOT / "Tests"
DEFAULT_RDC = Path("D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc")
DEFAULT_EID = 7643
SCRIPT_NAME = Path(globals().get("__file__", "extract_buffers.py")).stem

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import app_config  # noqa: E402
import library_db  # noqa: E402
import rd_session  # noqa: E402
from extract_shaders import resource_format_to_dict, shader_resource_to_dict, constant_block_to_dict  # noqa: E402
from extract_textures import descriptor_to_dict, access_to_dict  # noqa: E402


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


def buffer_description_map(controller: Any) -> Dict[str, Any]:
    return {resource_id_to_string(buf.resourceId): buf for buf in controller.GetBuffers()}


def buffer_desc_to_dict(buf: Any) -> Dict[str, Any]:
    return {
        "resourceId": resource_id_to_string(getattr(buf, "resourceId", "")),
        "byteSize": int(getattr(buf, "length", 0)),
        "length": int(getattr(buf, "length", 0)),
        "creationFlags": enum_to_string(getattr(buf, "creationFlags", "")),
        "gpuAddress": int(getattr(buf, "gpuAddress", 0)),
    }


def shader_constant_type_to_dict(t: Any) -> Dict[str, Any]:
    data = {
        "baseType": enum_to_string(getattr(t, "baseType", "")),
        "rows": int(getattr(t, "rows", 0)),
        "columns": int(getattr(t, "columns", 0)),
        "elements": int(getattr(t, "elements", 0)),
        "arrayByteStride": int(getattr(t, "arrayByteStride", 0)),
        "matrixByteStride": int(getattr(t, "matrixByteStride", 0)),
        "rowMajorStorage": bool(getattr(t, "rowMajorStorage", False)),
        "name": str(getattr(t, "name", "")),
    }
    members = []
    for m in getattr(t, "members", []):
        members.append(shader_constant_to_dict(m))
    if members:
        data["members"] = members
    return data


def shader_constant_to_dict(c: Any) -> Dict[str, Any]:
    return {
        "name": str(getattr(c, "name", "")),
        "byteOffset": int(getattr(c, "byteOffset", 0)),
        "bitFieldOffset": int(getattr(c, "bitFieldOffset", 0)),
        "bitFieldSize": int(getattr(c, "bitFieldSize", 0)),
        "defaultValue": int(getattr(c, "defaultValue", 0)),
        "type": shader_constant_type_to_dict(getattr(c, "type", None)),
    }


def shader_value_to_dict(value: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for name in ("f32v", "s32v", "u32v", "f64v", "u64v", "s64v", "u16v", "s16v", "u8v", "s8v"):
        try:
            arr = getattr(value, name)
            data[name] = [arr[i] for i in range(len(arr))]
        except Exception:
            continue
    return data


def shader_variable_to_dict(var: Any) -> Dict[str, Any]:
    result = {
        "name": str(getattr(var, "name", "")),
        "rows": int(getattr(var, "rows", 0)),
        "columns": int(getattr(var, "columns", 0)),
        "type": enum_to_string(getattr(var, "type", "")),
        "flags": enum_to_string(getattr(var, "flags", "")),
        "value": shader_value_to_dict(getattr(var, "value", None)),
        "members": [],
    }
    result["members"] = [shader_variable_to_dict(m) for m in getattr(var, "members", [])]
    return result


def get_raw_buffer(controller: Any, resource_id: Any, byte_offset: int, byte_size: int) -> bytes:
    return bytes(controller.GetBufferData(resource_id, int(byte_offset), int(byte_size)))


def save_buffer_payload(
    payload: bytes,
    buffer_dir: Path,
    db_path: Path,
    category: str,
    item: Dict[str, Any],
    logger: logging.Logger,
) -> Tuple[str, Dict[str, Any], bool]:
    digest = library_db.sha256_bytes(payload)
    stable_identity = (
        f"{category}|{item.get('stage')}|{item.get('resourceId')}|"
        f"{item.get('byteOffset')}|{item.get('byteSize')}|{item.get('access')}|{item.get('descriptor')}"
    )
    key = library_db.make_asset_key(category, library_db.sha256_bytes(stable_identity.encode("utf-8")))
    db = library_db.load_json_db(db_path, "buffer")
    existing = db.get("items", {}).get(key)
    if existing and existing.get("file"):
        file_rel = existing["file"]
        file_path = buffer_dir / file_rel
        created_file = False
    else:
        prefix = category
        file_rel = f"{prefix}_{key.split('_', 1)[1] if '_' in key else digest[:16]}.bin"
        file_path = buffer_dir / file_rel
        if not file_path.exists():
            file_path.write_bytes(payload)
        created_file = True

    final_item = dict(item)
    final_item.update({"id": key, "file": file_rel, "sha256": digest, "byteSizeSaved": len(payload)})
    registered, created_db = library_db.register_asset(db_path, key, final_item, "buffer", update_existing=True)
    logger.info("Saved buffer asset %s file=%s bytes=%d created=%s", key, file_rel, len(payload), created_file or created_db)
    return key, registered, bool(created_file or created_db)


def extract_constant_buffers(rd: Any, controller: Any, pipe: Any, stage_label: str, stage: Any, buffer_dir: Path, db_path: Path, logger: logging.Logger) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    refl = pipe.GetShaderReflection(stage)
    if refl is None:
        return out
    pipeline = pipe.GetGraphicsPipelineObject()
    shader = pipe.GetShader(stage)
    entry = pipe.GetShaderEntryPoint(stage)
    try:
        cblocks = pipe.GetConstantBlocks(stage, True)
    except TypeError:
        cblocks = pipe.GetConstantBlocks(stage)
    logger.info("%s constant buffer descriptors: %d", stage_label, len(cblocks))

    for used in cblocks:
        access_index = int(getattr(used.access, "index", 0))
        desc = used.descriptor
        resource_id = resource_id_to_string(getattr(desc, "resource", ""))
        cb_meta = None
        if access_index < len(getattr(refl, "constantBlocks", [])):
            cb_meta = refl.constantBlocks[access_index]
        byte_offset = int(getattr(desc, "byteOffset", 0))
        byte_size = int(getattr(desc, "byteSize", 0))
        if byte_size == 0 and cb_meta is not None:
            byte_size = int(getattr(cb_meta, "byteSize", 0))
        if byte_size == 0:
            byte_size = 0

        record: Dict[str, Any] = {
            "stage": stage_label,
            "category": "constant_buffer",
            "access": access_to_dict(used.access),
            "descriptor": descriptor_to_dict(desc),
            "constant_block": constant_block_to_dict(cb_meta) if cb_meta is not None else None,
            "variables_schema": [shader_constant_to_dict(v) for v in getattr(cb_meta, "variables", [])] if cb_meta is not None else [],
        }
        try:
            payload = get_raw_buffer(controller, getattr(desc, "resource"), byte_offset, byte_size)
            item = {
                "category": "constant_buffer",
                "stage": stage_label,
                "resourceId": resource_id,
                "byteOffset": byte_offset,
                "byteSize": byte_size,
                "descriptor": record["descriptor"],
                "access": record["access"],
                "constant_block": record["constant_block"],
                "variables_schema": record["variables_schema"],
            }
            key, registered, created = save_buffer_payload(payload, buffer_dir, db_path, "cbuffer", item, logger)
            record["library_id"] = key
            record["library_file"] = registered.get("file")
            record["sha256"] = registered.get("sha256")
            record["created"] = created

            decoded = controller.GetCBufferVariableContents(
                pipeline, shader, stage, entry, access_index, getattr(desc, "resource"), byte_offset, byte_size
            )
            decoded_json = [shader_variable_to_dict(v) for v in decoded]
            decoded_rel = f"decoded_{key}.json"
            decoded_path = buffer_dir / decoded_rel
            with decoded_path.open("w", encoding="utf-8") as f:
                json.dump(decoded_json, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
            record["decoded_variables_file"] = decoded_rel
            record["decoded_variable_count"] = len(decoded_json)
        except Exception as exc:
            logger.exception("Failed extracting cbuffer stage=%s index=%s resource=%s", stage_label, access_index, resource_id)
            record["error"] = str(exc)
        out.append(record)
    return out


def extract_resource_buffers(rd: Any, controller: Any, pipe: Any, stage_label: str, stage: Any, buffer_dir: Path, db_path: Path, logger: logging.Logger) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    refl = pipe.GetShaderReflection(stage)
    try:
        ro = pipe.GetReadOnlyResources(stage, True)
    except TypeError:
        ro = pipe.GetReadOnlyResources(stage)
    try:
        rw = pipe.GetReadWriteResources(stage, True)
    except TypeError:
        rw = pipe.GetReadWriteResources(stage)

    all_used = [("read_only_buffer", x) for x in ro] + [("read_write_buffer", x) for x in rw]
    logger.info("%s resource descriptors to inspect for buffers: %d", stage_label, len(all_used))

    for category, used in all_used:
        desc = used.descriptor
        resource_id = resource_id_to_string(getattr(desc, "resource", ""))
        if resource_id in ("0", "", "ResourceId::Null"):
            continue
        texture_type = str(getattr(desc, "textureType", ""))
        # Image descriptors are handled by extract_textures. Buffer descriptors use Buffer/Unknown texture type.
        if "Texture" in texture_type and "Buffer" not in texture_type:
            continue
        byte_offset = int(getattr(desc, "byteOffset", 0))
        byte_size = int(getattr(desc, "byteSize", 0))
        element_size = int(getattr(desc, "elementByteSize", 0))
        struct_count = int(getattr(desc, "bufferStructCount", 0))
        if byte_size == 0 and element_size > 0 and struct_count > 0:
            byte_size = element_size * struct_count
        if byte_size == 0:
            # 0 means rest-of-buffer in RenderDoc; cap at full returned size but record requested 0.
            logger.debug("Descriptor byteSize is 0 for %s resource=%s; reading rest of buffer", category, resource_id)

        access_index = int(getattr(used.access, "index", 0))
        shader_resource = None
        if refl is not None:
            source = getattr(refl, "readOnlyResources", []) if category == "read_only_buffer" else getattr(refl, "readWriteResources", [])
            if access_index < len(source):
                shader_resource = shader_resource_to_dict(source[access_index])

        record: Dict[str, Any] = {
            "stage": stage_label,
            "category": category,
            "access": access_to_dict(used.access),
            "descriptor": descriptor_to_dict(desc),
            "shader_resource": shader_resource,
        }
        try:
            payload = get_raw_buffer(controller, getattr(desc, "resource"), byte_offset, byte_size)
            item = {
                "category": category,
                "stage": stage_label,
                "resourceId": resource_id,
                "byteOffset": byte_offset,
                "byteSize": byte_size if byte_size else len(payload),
                "descriptor": record["descriptor"],
                "access": record["access"],
                "shader_resource": shader_resource,
            }
            key, registered, created = save_buffer_payload(payload, buffer_dir, db_path, "buffer", item, logger)
            record["library_id"] = key
            record["library_file"] = registered.get("file")
            record["sha256"] = registered.get("sha256")
            record["created"] = created
        except Exception as exc:
            logger.exception("Failed extracting buffer stage=%s category=%s resource=%s", stage_label, category, resource_id)
            record["error"] = str(exc)
        out.append(record)
    return out


def extract_buffers(args: argparse.Namespace, logger: logging.Logger, log_path: Optional[Path]) -> Dict[str, Any]:
    rd = rd_session.import_renderdoc(args.renderdoc_module_dir, logger)
    rd_session.initialise_replay_if_needed(rd, logger)
    cap = None
    controller = None
    start = time.perf_counter()
    try:
        cap, controller = rd_session.open_capture(rd, args.rdc, logger)
        action, pipe = rd_session.set_eid(controller, args.eid, logger)
        buffer_dir = args.out / "libraries" / "buffers"
        buffer_dir.mkdir(parents=True, exist_ok=True)
        db_path = buffer_dir / "buffer_library.json"

        result: Dict[str, Any] = {
            "script": SCRIPT_NAME,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rdc": str(args.rdc),
            "eid": args.eid,
            "out": str(args.out),
            "log_file": str(log_path) if log_path else None,
            "action": rd_session.action_to_summary(rd, controller, action),
            "buffers": [],
            "buffer_count": 0,
            "unique_buffer_count": 0,
            "warnings": [],
        }

        stages = [("VS", rd.ShaderStage.Vertex), ("PS", rd.ShaderStage.Pixel)]
        for stage_label, stage in stages:
            cbuffers = extract_constant_buffers(rd, controller, pipe, stage_label, stage, buffer_dir, db_path, logger)
            rbuffers = extract_resource_buffers(rd, controller, pipe, stage_label, stage, buffer_dir, db_path, logger)
            result["buffers"].extend(cbuffers)
            result["buffers"].extend(rbuffers)

        for rec in result["buffers"]:
            if rec.get("error"):
                result["warnings"].append(f"{rec.get('stage')} {rec.get('category')} failed: {rec.get('error')}")
        result["buffer_count"] = len(result["buffers"])
        result["unique_buffer_count"] = len({b.get("library_id") for b in result["buffers"] if b.get("library_id")})
        stage_stats = {}
        for stage_name in ("VS", "PS"):
            stage_buffers = [b for b in result["buffers"] if b.get("stage") == stage_name]
            by_category = {}
            for category in ("constant_buffer", "read_only_buffer", "read_write_buffer"):
                category_buffers = [b for b in stage_buffers if b.get("category") == category]
                by_category[category] = {
                    "binding_count": len(category_buffers),
                    "unique_buffer_count": len({b.get("library_id") for b in category_buffers if b.get("library_id")}),
                    "resource_ids": [b.get("descriptor", {}).get("resourceId") for b in category_buffers],
                    "shader_resource_names": [
                        (b.get("shader_resource") or {}).get("name")
                        or (b.get("constant_block") or {}).get("name")
                        for b in category_buffers
                    ],
                }
            stage_stats[stage_name] = {
                "buffer_binding_count": len(stage_buffers),
                "unique_buffer_count": len({b.get("library_id") for b in stage_buffers if b.get("library_id")}),
                "by_category": by_category,
            }
        result["stage_stats"] = stage_stats
        result["elapsed_seconds"] = round(time.perf_counter() - start, 3)

        args.test_log.parent.mkdir(parents=True, exist_ok=True)
        with args.test_log.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        logger.info("Wrote buffer extraction test log: %s", args.test_log)

        if result["warnings"]:
            raise RuntimeError(f"Buffer extraction completed with warnings: {result['warnings']}")
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
    default_no_log = app_config.env_bool("RENDERDOC_EXTRACT_NO_LOG", settings.no_log)
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="Extract VS/PS buffer resources for one RenderDoc EID.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--rdc", type=Path, default=default_rdc, help="Path to .rdc capture.")
    parser.add_argument("--eid", type=int, default=default_eid, help="Target event ID.")
    parser.add_argument("--out", type=Path, default=default_out, help="Output root directory.")
    parser.add_argument(
        "--test-log",
        type=Path,
        default=TEST_DIR / f"extract_buffers_eid_{default_eid}.json",
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
    if log_path:
        logger.info("Log path: %s", log_path)
    try:
        result = extract_buffers(args, logger, log_path)
        logger.info(
            "extract_buffers passed: buffers=%s unique=%s warnings=%s",
            result.get("buffer_count"),
            result.get("unique_buffer_count"),
            len(result.get("warnings", [])),
        )
        return 0
    except Exception as exc:
        logger.error("extract_buffers failed: %s", exc)
        logger.debug("Full traceback:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__" or "pyrenderdoc" in globals():
    raise SystemExit(main())
