#!/usr/bin/env python3
"""Extract VS/PS texture resources for one RenderDoc EID as de-duplicated DDS files."""

import argparse
import json
import logging
import os
import shutil
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
TEMP_DIR = PROJECT_ROOT / "Temp"
DEFAULT_RDC = Path("D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc")
DEFAULT_EID = 7643
SCRIPT_NAME = Path(globals().get("__file__", "extract_textures.py")).stem

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import app_config  # noqa: E402
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


def texture_description_map(controller: Any) -> Dict[str, Any]:
    return {resource_id_to_string(tex.resourceId): tex for tex in controller.GetTextures()}


def texture_desc_to_dict(tex: Any) -> Dict[str, Any]:
    fmt = resource_format_to_dict(getattr(tex, "format", None))
    return {
        "resourceId": resource_id_to_string(getattr(tex, "resourceId", "")),
        "format": fmt.get("name", "Unknown"),
        "format_detail": fmt,
        "dimension": int(getattr(tex, "dimension", 0)),
        "type": enum_to_string(getattr(tex, "type", "")),
        "width": int(getattr(tex, "width", 0)),
        "height": int(getattr(tex, "height", 0)),
        "depth": int(getattr(tex, "depth", 0)),
        "mips": int(getattr(tex, "mips", 1)),
        "arraysize": int(getattr(tex, "arraysize", 1)),
        "cubemap": bool(getattr(tex, "cubemap", False)),
        "msQual": int(getattr(tex, "msQual", 0)),
        "msSamp": int(getattr(tex, "msSamp", 1)),
        "byteSize": int(getattr(tex, "byteSize", 0)),
        "creationFlags": enum_to_string(getattr(tex, "creationFlags", "")),
    }


def descriptor_to_dict(desc: Any) -> Dict[str, Any]:
    fmt = resource_format_to_dict(getattr(desc, "format", None))
    return {
        "type": enum_to_string(getattr(desc, "type", "")),
        "flags": enum_to_string(getattr(desc, "flags", "")),
        "resourceId": resource_id_to_string(getattr(desc, "resource", "")),
        "secondaryId": resource_id_to_string(getattr(desc, "secondary", "")),
        "viewId": resource_id_to_string(getattr(desc, "view", "")),
        "format": fmt.get("name", "Unknown"),
        "format_detail": fmt,
        "byteOffset": int(getattr(desc, "byteOffset", 0)),
        "byteSize": int(getattr(desc, "byteSize", 0)),
        "elementByteSize": int(getattr(desc, "elementByteSize", 0)),
        "firstSlice": int(getattr(desc, "firstSlice", 0)),
        "numSlices": int(getattr(desc, "numSlices", 0)),
        "firstMip": int(getattr(desc, "firstMip", 0)),
        "numMips": int(getattr(desc, "numMips", 0)),
        "textureType": enum_to_string(getattr(desc, "textureType", "")),
    }


def access_to_dict(access: Any) -> Dict[str, Any]:
    return {
        "stage": enum_to_string(getattr(access, "stage", "")),
        "type": enum_to_string(getattr(access, "type", "")),
        "index": int(getattr(access, "index", 0)),
        "arrayElement": int(getattr(access, "arrayElement", 0)),
        "descriptorStore": resource_id_to_string(getattr(access, "descriptorStore", "")),
        "byteOffset": int(getattr(access, "byteOffset", 0)),
        "byteSize": int(getattr(access, "byteSize", 0)),
        "staticallyUnused": bool(getattr(access, "staticallyUnused", False)),
    }


def sampler_to_dict(sampler: Any) -> Dict[str, Any]:
    return {
        "addressU": enum_to_string(getattr(sampler, "addressU", "")),
        "addressV": enum_to_string(getattr(sampler, "addressV", "")),
        "addressW": enum_to_string(getattr(sampler, "addressW", "")),
        "compareFunction": enum_to_string(getattr(sampler, "compareFunction", "")),
        "filter": enum_to_string(getattr(sampler, "filter", "")),
        "maxAnisotropy": float(getattr(sampler, "maxAnisotropy", 0.0)),
        "maxLOD": float(getattr(sampler, "maxLOD", 0.0)),
        "minLOD": float(getattr(sampler, "minLOD", 0.0)),
        "mipBias": float(getattr(sampler, "mipBias", 0.0)),
        "unnormalized": bool(getattr(sampler, "unnormalized", False)),
        "seamlessCubemaps": bool(getattr(sampler, "seamlessCubemaps", True)),
    }


def shader_resource_name(pipe: Any, stage: Any, access_index: int) -> Optional[str]:
    try:
        refl = pipe.GetShaderReflection(stage)
        if refl is None:
            return None
        resources = getattr(refl, "readOnlyResources", [])
        if access_index < len(resources):
            return str(getattr(resources[access_index], "name", ""))
    except Exception:
        return None
    return None


def save_texture_dds(rd: Any, controller: Any, resource_id: Any, temp_path: Path, logger: logging.Logger) -> bool:
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    texsave = rd.TextureSave()
    texsave.resourceId = resource_id
    texsave.destType = rd.FileType.DDS
    # Save all mips/slices where supported by this RenderDoc build.
    try:
        texsave.mip = -1
    except Exception:
        pass
    try:
        texsave.slice.sliceIndex = -1
    except Exception:
        pass
    try:
        texsave.alpha = rd.AlphaMapping.Preserve
    except Exception:
        pass
    try:
        texsave.sample.mapToArray = True
    except Exception:
        pass

    logger.info("Saving texture DDS temp: resource=%s path=%s", resource_id_to_string(resource_id), temp_path)
    result = controller.SaveTexture(texsave, str(temp_path))
    # Some Python bindings expose ResultDetails, some bool-like.
    if isinstance(result, bool):
        return result and temp_path.exists()
    try:
        return result == rd.ResultCode.Succeeded and temp_path.exists()
    except Exception:
        return bool(result) and temp_path.exists()


def collect_texture_bindings(rd: Any, pipe: Any, textures_by_id: Dict[str, Any], only_used: bool, logger: logging.Logger) -> List[Dict[str, Any]]:
    bindings: List[Dict[str, Any]] = []
    stage_pairs = [("VS", rd.ShaderStage.Vertex), ("PS", rd.ShaderStage.Pixel)]
    for stage_label, stage in stage_pairs:
        try:
            used_resources = pipe.GetReadOnlyResources(stage, only_used)
        except TypeError:
            used_resources = pipe.GetReadOnlyResources(stage)
        logger.info("%s read-only descriptors: %d", stage_label, len(used_resources))

        for ordinal, used in enumerate(used_resources):
            desc = used.descriptor
            resource_id = resource_id_to_string(getattr(desc, "resource", ""))
            if resource_id in ("0", "", "ResourceId::Null"):
                continue
            tex = textures_by_id.get(resource_id)
            if tex is None:
                logger.debug("Skipping non-texture read-only descriptor: stage=%s resource=%s", stage_label, resource_id)
                continue

            binding = {
                "stage": stage_label,
                "ordinal": ordinal,
                "shaderResourceName": shader_resource_name(pipe, stage, int(getattr(used.access, "index", 0))),
                "access": access_to_dict(used.access),
                "descriptor": descriptor_to_dict(desc),
                "sampler": sampler_to_dict(used.sampler),
                "texture": texture_desc_to_dict(tex),
            }
            bindings.append(binding)
    return bindings


def extract_textures(args: argparse.Namespace, logger: logging.Logger, log_path: Optional[Path]) -> Dict[str, Any]:
    rd = rd_session.import_renderdoc(args.renderdoc_module_dir, logger)
    rd_session.initialise_replay_if_needed(rd, logger)
    cap = None
    controller = None
    start = time.perf_counter()
    try:
        cap, controller = rd_session.open_capture(rd, args.rdc, logger)
        action, pipe = rd_session.set_eid(controller, args.eid, logger)
        textures_by_id = texture_description_map(controller)
        logger.info("Capture texture count: %d", len(textures_by_id))

        texture_dir = args.texture_lib or (args.out / "libraries" / "textures")
        texture_dir.mkdir(parents=True, exist_ok=True)
        db_path = texture_dir / "texture_library.json"
        temp_dir = TEMP_DIR / SCRIPT_NAME / f"eid_{args.eid}_{_now_string()}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        bindings = collect_texture_bindings(rd, pipe, textures_by_id, args.only_used, logger)
        logger.info("Texture bindings collected: %d", len(bindings))

        result: Dict[str, Any] = {
            "script": SCRIPT_NAME,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rdc": str(args.rdc),
            "eid": args.eid,
            "out": str(args.out),
            "texture_library_dir": str(texture_dir),
            "log_file": str(log_path) if log_path else None,
            "action": rd_session.action_to_summary(rd, controller, action),
            "texture_bindings": [],
            "texture_binding_count": len(bindings),
            "unique_texture_count": 0,
            "warnings": [],
        }

        unique_ids = set()
        for binding in bindings:
            tex_meta = binding["texture"]
            resource_id = tex_meta["resourceId"]
            fmt_name = library_db.normalise_format_name(tex_meta["format"])
            temp_dds = temp_dir / f"resource_{resource_id}.dds"
            try:
                ok = save_texture_dds(rd, controller, getattr(textures_by_id[resource_id], "resourceId"), temp_dds, logger)
                if not ok:
                    raise RuntimeError("SaveTexture returned failure or no file was produced")
                dds_hash = library_db.sha256_file(temp_dds)
                db = library_db.load_json_db(db_path, "texture")
                identity_hash = library_db.sha256_bytes(f"{fmt_name}|{dds_hash}".encode("utf-8"))
                key = library_db.make_asset_key("tex", identity_hash)
                existing = db.get("items", {}).get(key)
                if existing and existing.get("file"):
                    final_rel = existing["file"]
                    final_path = texture_dir / final_rel
                    created = False
                else:
                    index = library_db.next_index_by_format(db, fmt_name)
                    final_name = f"{fmt_name}_{index:06d}.dds"
                    final_rel = final_name
                    final_path = texture_dir / final_name
                    if not final_path.exists():
                        shutil.move(str(temp_dds), str(final_path))
                    created = True

                item = {
                    "id": key,
                    "file": final_rel,
                    "sha256": dds_hash,
                    "identity_sha256": identity_hash,
                    "format": tex_meta["format"],
                    "format_detail": tex_meta["format_detail"],
                    "index": existing.get("index") if existing else int(final_path.stem.split("_")[-1]),
                    "width": tex_meta["width"],
                    "height": tex_meta["height"],
                    "depth": tex_meta["depth"],
                    "mips": tex_meta["mips"],
                    "arraysize": tex_meta["arraysize"],
                    "dimension": tex_meta["dimension"],
                    "type": tex_meta["type"],
                    "byteSize": tex_meta["byteSize"],
                    "resource_ids_seen": sorted(set([resource_id] + list(existing.get("resource_ids_seen", [])))) if existing else [resource_id],
                }
                registered, was_created = library_db.register_asset(db_path, key, item, "texture", update_existing=True)
                binding["library_id"] = key
                binding["library_file"] = registered.get("file")
                binding["dds_sha256"] = registered.get("sha256")
                binding["created"] = bool(created and was_created)
                unique_ids.add(key)
                logger.info(
                    "Texture %s stage=%s resource=%s format=%s file=%s created=%s",
                    key,
                    binding["stage"],
                    resource_id,
                    tex_meta["format"],
                    registered.get("file"),
                    binding["created"],
                )
            except Exception as exc:
                warning = f"Texture extraction failed for resource {resource_id}: {exc}"
                logger.exception(warning)
                binding["error"] = str(exc)
                result["warnings"].append(warning)
            result["texture_bindings"].append(binding)

        result["unique_texture_count"] = len(unique_ids)
        stage_stats = {}
        for stage_name in ("VS", "PS"):
            stage_bindings = [b for b in result["texture_bindings"] if b.get("stage") == stage_name]
            stage_stats[stage_name] = {
                "texture_binding_count": len(stage_bindings),
                "unique_texture_count": len({b.get("library_id") for b in stage_bindings if b.get("library_id")}),
                "resource_ids": [b.get("texture", {}).get("resourceId") for b in stage_bindings],
                "shader_resource_names": [b.get("shaderResourceName") for b in stage_bindings],
            }
        result["stage_stats"] = stage_stats
        result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        args.test_log.parent.mkdir(parents=True, exist_ok=True)
        with args.test_log.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        logger.info("Wrote texture extraction test log: %s", args.test_log)

        if result["warnings"]:
            raise RuntimeError(f"Texture extraction completed with warnings: {result['warnings']}")
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
    texture_lib_text = os.environ.get("RENDERDOC_EXTRACT_TEXTURE_LIB", settings.texture_lib)
    default_texture_lib = Path(texture_lib_text) if texture_lib_text else None
    default_only_used = app_config.env_bool("RENDERDOC_EXTRACT_TEXTURES_ONLY_USED", settings.textures_only_used)
    default_no_log = app_config.env_bool("RENDERDOC_EXTRACT_NO_LOG", settings.no_log)

    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="Extract VS/PS texture resources for one RenderDoc EID as DDS.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--rdc", type=Path, default=default_rdc, help="Path to .rdc capture.")
    parser.add_argument("--eid", type=int, default=default_eid, help="Target event ID.")
    parser.add_argument("--out", type=Path, default=default_out, help="Output root directory.")
    parser.add_argument("--texture-lib", type=Path, default=default_texture_lib, help="Optional external texture library directory.")
    parser.add_argument("--only-used", dest="only_used", action="store_true", default=default_only_used, help="Only extract descriptors not statically unused.")
    parser.add_argument("--all-bound", dest="only_used", action="store_false", help="Extract all bound/declarative read-only descriptors.")
    parser.add_argument(
        "--test-log",
        type=Path,
        default=TEST_DIR / f"extract_textures_eid_{default_eid}.json",
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
    logger.info("Texture library dir: %s", args.texture_lib or (args.out / "libraries" / "textures"))
    if log_path:
        logger.info("Log path: %s", log_path)
    try:
        result = extract_textures(args, logger, log_path)
        logger.info(
            "extract_textures passed: bindings=%s unique=%s warnings=%s",
            result.get("texture_binding_count"),
            result.get("unique_texture_count"),
            len(result.get("warnings", [])),
        )
        return 0
    except Exception as exc:
        logger.error("extract_textures failed: %s", exc)
        logger.debug("Full traceback:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__" or "pyrenderdoc" in globals():
    raise SystemExit(main())
