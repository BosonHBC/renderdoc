#!/usr/bin/env python3
"""Validate extracted EID resources against live RenderDoc PipeState and files."""

import argparse
import json
import logging
import os
import sys
import time
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
SCRIPT_NAME = Path(globals().get("__file__", "validate_extraction.py")).stem

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import app_config  # noqa: E402
import library_db  # noqa: E402
import rd_session  # noqa: E402
from extract_textures import texture_description_map, collect_texture_bindings  # noqa: E402
from extract_buffers import extract_constant_buffers, extract_resource_buffers  # noqa: E402


def _now_string() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def setup_logger(no_log: bool) -> Tuple[logging.Logger, Optional[Path]]:
    logger = logging.getLogger(SCRIPT_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)
    if no_log:
        return logger, None
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{SCRIPT_NAME}_{_now_string()}.log"
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger, log_path


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def file_checks(output_root: Path, manifest: Dict[str, Any]) -> List[str]:
    errors = []
    library_root = output_root / "libraries"
    files = []
    for stage in ("vs", "ps"):
        item = (((manifest.get("resources") or {}).get("shaders") or {}).get(stage) or {}).get("item")
        if item:
            for k in ("raw_file", "disasm_file", "hlsl_file"):
                if item.get(k):
                    files.append(library_root / item[k])
    for tex in (((manifest.get("resources") or {}).get("textures") or {}).get("textures") or []):
        if tex.get("library_file"):
            files.append(library_root / "textures" / tex["library_file"])
    for buf in (((manifest.get("resources") or {}).get("buffers") or {}).get("buffers") or []):
        if buf.get("library_file"):
            files.append(library_root / "buffers" / buf["library_file"])
        if buf.get("decoded_variables_file"):
            files.append(library_root / "buffers" / buf["decoded_variables_file"])
    mesh = (((manifest.get("resources") or {}).get("mesh") or {}).get("mesh") or {})
    for k in ("obj_file", "mesh_json", "attributes_json", "attributes_bin"):
        if mesh.get(k):
            files.append(library_root / "meshes" / mesh[k])
    for f in files:
        if not f.exists():
            errors.append(f"Missing referenced file: {f}")
    return errors


def hash_checks(output_root: Path, manifest: Dict[str, Any]) -> List[str]:
    errors = []
    library_root = output_root / "libraries"
    for tex in (((manifest.get("resources") or {}).get("textures") or {}).get("textures") or []):
        rel = tex.get("library_file")
        expected = tex.get("dds_sha256")
        if rel and expected:
            path = library_root / "textures" / rel
            if path.exists() and library_db.sha256_file(path) != expected:
                errors.append(f"Texture hash mismatch: {path}")
    for buf in (((manifest.get("resources") or {}).get("buffers") or {}).get("buffers") or []):
        rel = buf.get("library_file")
        expected = buf.get("sha256")
        if rel and expected:
            path = library_root / "buffers" / rel
            if path.exists() and library_db.sha256_file(path) != expected:
                errors.append(f"Buffer hash mismatch: {path}")
    return errors


def live_texture_stage_stats(rd: Any, pipe: Any, controller: Any, logger: logging.Logger) -> Dict[str, Any]:
    textures_by_id = texture_description_map(controller)
    bindings = collect_texture_bindings(rd, pipe, textures_by_id, True, logger)
    stats = {}
    for stage in ("VS", "PS"):
        bs = [b for b in bindings if b.get("stage") == stage]
        stats[stage] = {
            "texture_binding_count": len(bs),
            "resource_ids": [b.get("texture", {}).get("resourceId") for b in bs],
            "shader_resource_names": [b.get("shaderResourceName") for b in bs],
        }
    return stats


def manifest_texture_stage_stats(manifest: Dict[str, Any]) -> Dict[str, Any]:
    bs = (((manifest.get("resources") or {}).get("textures") or {}).get("textures") or [])
    stats = {}
    for stage in ("VS", "PS"):
        s = [b for b in bs if b.get("stage") == stage]
        stats[stage] = {
            "texture_binding_count": len(s),
            "resource_ids": [b.get("texture", {}).get("resourceId") for b in s],
            "shader_resource_names": [b.get("shaderResourceName") for b in s],
        }
    return stats


def live_buffer_stage_stats(rd: Any, pipe: Any) -> Dict[str, Any]:
    stats = {}
    for stage_name, stage in (("VS", rd.ShaderStage.Vertex), ("PS", rd.ShaderStage.Pixel)):
        try:
            cb = pipe.GetConstantBlocks(stage, True)
        except TypeError:
            cb = pipe.GetConstantBlocks(stage)
        try:
            ro = pipe.GetReadOnlyResources(stage, True)
        except TypeError:
            ro = pipe.GetReadOnlyResources(stage)
        try:
            rw = pipe.GetReadWriteResources(stage, True)
        except TypeError:
            rw = pipe.GetReadWriteResources(stage)
        ro_buf = [u for u in ro if "Texture" not in str(getattr(u.descriptor, "textureType", "")) or "Buffer" in str(getattr(u.descriptor, "textureType", ""))]
        rw_buf = [u for u in rw if "Texture" not in str(getattr(u.descriptor, "textureType", "")) or "Buffer" in str(getattr(u.descriptor, "textureType", ""))]
        stats[stage_name] = {
            "constant_buffer": len(cb),
            "read_only_buffer": len(ro_buf),
            "read_write_buffer": len(rw_buf),
            "buffer_binding_count": len(cb) + len(ro_buf) + len(rw_buf),
        }
    return stats


def manifest_buffer_stage_stats(manifest: Dict[str, Any]) -> Dict[str, Any]:
    bs = (((manifest.get("resources") or {}).get("buffers") or {}).get("buffers") or [])
    stats = {}
    for stage in ("VS", "PS"):
        s = [b for b in bs if b.get("stage") == stage]
        stats[stage] = {
            "constant_buffer": len([b for b in s if b.get("category") == "constant_buffer"]),
            "read_only_buffer": len([b for b in s if b.get("category") == "read_only_buffer"]),
            "read_write_buffer": len([b for b in s if b.get("category") == "read_write_buffer"]),
            "buffer_binding_count": len(s),
        }
    return stats


def validate(args: argparse.Namespace, logger: logging.Logger, log_path: Optional[Path]) -> Dict[str, Any]:
    rd = rd_session.import_renderdoc(args.renderdoc_module_dir, logger)
    rd_session.initialise_replay_if_needed(rd, logger)
    cap = None
    controller = None
    start = time.perf_counter()
    try:
        cap, controller = rd_session.open_capture(rd, args.rdc, logger)
        action, pipe = rd_session.set_eid(controller, args.eid, logger)
        manifest_path = args.out / "draws" / f"eid_{args.eid}" / "draw_manifest.json"
        manifest = read_json(manifest_path, None)
        errors = []
        warnings = []
        if not manifest:
            errors.append(f"Manifest missing or unreadable: {manifest_path}")
            manifest = {}
        else:
            errors.extend(file_checks(args.out, manifest))
            errors.extend(hash_checks(args.out, manifest))
        live_tex = live_texture_stage_stats(rd, pipe, controller, logger)
        man_tex = manifest_texture_stage_stats(manifest)
        live_buf = live_buffer_stage_stats(rd, pipe)
        man_buf = manifest_buffer_stage_stats(manifest)
        if live_tex != man_tex:
            errors.append(f"Texture stage stats mismatch: live={live_tex}, manifest={man_tex}")
        if live_buf != man_buf:
            errors.append(f"Buffer stage stats mismatch: live={live_buf}, manifest={man_buf}")
        if int(getattr(action, "numInstances", 0)) > 1:
            extracted = ((manifest.get("resources") or {}).get("mesh") or {}).get("mesh", {}).get("extracted_instance")
            if extracted != 0:
                errors.append("Instanced draw manifest must record extracted_instance=0")
        result = {
            "script": SCRIPT_NAME,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rdc": str(args.rdc),
            "eid": args.eid,
            "manifest": str(manifest_path),
            "log_file": str(log_path) if log_path else None,
            "live_texture_stage_stats": live_tex,
            "manifest_texture_stage_stats": man_tex,
            "live_buffer_stage_stats": live_buf,
            "manifest_buffer_stage_stats": man_buf,
            "errors": errors,
            "warnings": warnings,
            "status": "passed" if not errors else "failed",
            "elapsed_seconds": round(time.perf_counter() - start, 3),
        }
        write_json(args.test_log, result)
        logger.info("Wrote validation result: %s", args.test_log)
        if errors:
            raise RuntimeError("Validation failed: " + "; ".join(errors))
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
    parser = argparse.ArgumentParser(prog=SCRIPT_NAME, description="Validate extracted EID resources.")
    parser.add_argument("--rdc", type=Path, default=default_rdc)
    parser.add_argument("--eid", type=int, default=default_eid)
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--test-log", type=Path, default=TEST_DIR / f"validate_extraction_eid_{default_eid}.json")
    parser.add_argument("--renderdoc-module-dir", action="append", default=[])
    parser.add_argument("--no-log", dest="no_log", action="store_true", default=default_no_log)
    parser.add_argument("-Nolog", dest="no_log", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    setattr(args, "unknown_args", unknown)
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logger, log_path = setup_logger(args.no_log)
    logger.info("RDC path: %s", args.rdc)
    logger.info("EID: %s", args.eid)
    try:
        result = validate(args, logger, log_path)
        logger.info("validate_extraction passed: %s", result["test_log"] if "test_log" in result else args.test_log)
        return 0
    except Exception as exc:
        logger.exception("validate_extraction failed: %s", exc)
        return 1


if __name__ == "__main__" or "pyrenderdoc" in globals():
    raise SystemExit(main())
