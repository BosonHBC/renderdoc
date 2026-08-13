#!/usr/bin/env python3
"""Build per-EID draw manifest from extracted RenderDocExtract libraries."""

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

DEFAULT_RDC = Path("D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc")
DEFAULT_EID = 7643
SCRIPT_NAME = Path(globals().get("__file__", "build_draw_manifest.py")).stem


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
from extract_shaders import output_targets_to_dict, resource_format_to_dict  # noqa: E402
from extract_textures import descriptor_to_dict  # noqa: E402


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


def find_latest_test_json(output_root: Path, stem: str, eid: int) -> Tuple[Optional[Path], Any]:
    path = PROJECT_ROOT / "Tests" / f"{stem}_eid_{eid}.json"
    return path if path.exists() else None, read_json(path, None)


def shader_refs(output_root: Path, eid: int) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    path, data = find_latest_test_json(output_root, "extract_shaders", eid)
    refs = {"source_test_json": str(path) if path else None, "vs": None, "ps": None}
    if not data:
        warnings.append("Missing extract_shaders test JSON")
        return refs, warnings
    refs["vs"] = data.get("shaders", {}).get("vs")
    refs["ps"] = data.get("shaders", {}).get("ps")
    refs["gbuffer_layout_match"] = (((refs.get("ps") or {}).get("item") or {}).get("gbuffer_layout_match"))
    refs["render_target_count"] = data.get("render_target_count")
    refs["render_targets"] = data.get("render_targets")
    return refs, warnings


def texture_refs(output_root: Path, eid: int) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    path, data = find_latest_test_json(output_root, "extract_textures", eid)
    refs = {"source_test_json": str(path) if path else None, "textures": []}
    if not data:
        warnings.append("Missing extract_textures test JSON")
        return refs, warnings
    refs["textures"] = data.get("texture_bindings", [])
    refs["texture_binding_count"] = data.get("texture_binding_count")
    refs["unique_texture_count"] = data.get("unique_texture_count")
    refs["stage_stats"] = data.get("stage_stats")
    return refs, warnings


def buffer_refs(output_root: Path, eid: int) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    path, data = find_latest_test_json(output_root, "extract_buffers", eid)
    refs = {"source_test_json": str(path) if path else None, "buffers": []}
    if not data:
        warnings.append("Missing extract_buffers test JSON")
        return refs, warnings
    refs["buffers"] = data.get("buffers", [])
    refs["buffer_count"] = data.get("buffer_count")
    refs["unique_buffer_count"] = data.get("unique_buffer_count")
    refs["stage_stats"] = data.get("stage_stats")
    return refs, warnings


def mesh_ref(output_root: Path, eid: int) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    path, data = find_latest_test_json(output_root, "extract_mesh", eid)
    ref = {"source_test_json": str(path) if path else None, "mesh": None}
    if not data:
        warnings.append("Missing extract_mesh test JSON")
        return ref, warnings
    ref["mesh"] = data.get("mesh")
    return ref, warnings


def viewport_to_dict(v: Any) -> Dict[str, Any]:
    return {
        "x": float(getattr(v, "x", 0.0)),
        "y": float(getattr(v, "y", 0.0)),
        "width": float(getattr(v, "width", 0.0)),
        "height": float(getattr(v, "height", 0.0)),
        "minDepth": float(getattr(v, "minDepth", 0.0)),
        "maxDepth": float(getattr(v, "maxDepth", 0.0)),
    }


def scissor_to_dict(s: Any) -> Dict[str, Any]:
    return {
        "x": int(getattr(s, "x", 0)),
        "y": int(getattr(s, "y", 0)),
        "width": int(getattr(s, "width", 0)),
        "height": int(getattr(s, "height", 0)),
        "enabled": bool(getattr(s, "enabled", False)),
    }


def blend_equation_to_dict(eq: Any) -> Dict[str, Any]:
    return {
        "source": enum_to_string(getattr(eq, "source", "")),
        "destination": enum_to_string(getattr(eq, "destination", "")),
        "operation": enum_to_string(getattr(eq, "operation", "")),
    }


def color_blend_to_dict(b: Any) -> Dict[str, Any]:
    return {
        "enabled": bool(getattr(b, "enabled", False)),
        "logicOperationEnabled": bool(getattr(b, "logicOperationEnabled", False)),
        "colorBlend": blend_equation_to_dict(getattr(b, "colorBlend", None)),
        "alphaBlend": blend_equation_to_dict(getattr(b, "alphaBlend", None)),
        "logicOperation": enum_to_string(getattr(b, "logicOperation", "")),
        "writeMask": int(getattr(b, "writeMask", 0)),
    }


def classify_blend(blends: List[Dict[str, Any]], ps_hlsl_path: Optional[Path]) -> str:
    if any(b.get("enabled") for b in blends):
        return "alpha_blend"
    text = ""
    if ps_hlsl_path and ps_hlsl_path.exists():
        try:
            text = ps_hlsl_path.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            pass
    if "discard" in text or "clip(" in text:
        return "masked"
    return "opaque"


def pipeline_state_summary(pipe: Any, output_root: Path, shader_refs_data: Dict[str, Any]) -> Dict[str, Any]:
    viewports = []
    scissors = []
    for i in range(16):
        try:
            v = pipe.GetViewport(i)
            if float(getattr(v, "width", 0.0)) > 0 and float(getattr(v, "height", 0.0)) > 0:
                viewports.append(viewport_to_dict(v))
        except Exception:
            break
    for i in range(16):
        try:
            s = pipe.GetScissor(i)
            if int(getattr(s, "width", 0)) > 0 and int(getattr(s, "height", 0)) > 0:
                scissors.append(scissor_to_dict(s))
        except Exception:
            break

    blends = []
    try:
        blends = [color_blend_to_dict(b) for b in pipe.GetColorBlends()]
    except Exception:
        pass

    ps_hlsl = None
    try:
        ps_file = shader_refs_data.get("ps", {}).get("item", {}).get("hlsl_file")
        if ps_file:
            ps_hlsl = output_root / "libraries" / ps_file
    except Exception:
        pass

    depth_state = None
    try:
        d = pipe.GetDepthTestState()
        depth_state = {
            "depthEnable": bool(getattr(d, "depthEnable", False)),
            "depthFunction": enum_to_string(getattr(d, "depthFunction", "")),
            "depthWrites": bool(getattr(d, "depthWrites", False)),
            "depthBounds": bool(getattr(d, "depthBounds", False)),
            "minDepthBounds": float(getattr(d, "minDepthBounds", 0.0)),
            "maxDepthBounds": float(getattr(d, "maxDepthBounds", 0.0)),
        }
    except Exception:
        pass

    raster_state = None
    try:
        r = pipe.GetRasterState()
        raster_state = {
            "frontCCW": bool(getattr(r, "frontCCW", False)),
            "fillMode": enum_to_string(getattr(r, "fillMode", "")),
            "cullMode": enum_to_string(getattr(r, "cullMode", "")),
        }
    except Exception:
        pass

    depth_target = None
    try:
        depth_target = descriptor_to_dict(pipe.GetDepthTarget())
    except Exception:
        pass

    return {
        "graphicsPipelineObject": resource_id_to_string(pipe.GetGraphicsPipelineObject()),
        "primitiveTopology": enum_to_string(pipe.GetPrimitiveTopology()),
        "viewports": viewports,
        "scissors": scissors,
        "render_targets": output_targets_to_dict(pipe),
        "depth_target": depth_target,
        "depth_state": depth_state,
        "raster_state": raster_state,
        "blend_state": {
            "raw": blends,
            "blendFactor": [float(x) for x in pipe.GetBlendFactor()] if hasattr(pipe, "GetBlendFactor") else None,
            "classification": classify_blend(blends, ps_hlsl),
            "independentBlending": bool(pipe.IsIndependentBlendingEnabled()) if hasattr(pipe, "IsIndependentBlendingEnabled") else None,
        },
    }


def validate_refs(output_root: Path, manifest: Dict[str, Any]) -> List[str]:
    warnings = []
    library_root = output_root / "libraries"
    files_to_check: List[Path] = []
    for stage in ("vs", "ps"):
        item = manifest.get("resources", {}).get("shaders", {}).get(stage, {}).get("item")
        if item:
            for key in ("raw_file", "disasm_file", "hlsl_file"):
                rel = item.get(key)
                if rel:
                    files_to_check.append(library_root / rel)
    for tex in manifest.get("resources", {}).get("textures", {}).get("textures", []):
        rel = tex.get("library_file")
        if rel:
            files_to_check.append(library_root / "textures" / rel)
    for buf in manifest.get("resources", {}).get("buffers", {}).get("buffers", []):
        rel = buf.get("library_file")
        if rel:
            files_to_check.append(library_root / "buffers" / rel)
        decoded = buf.get("decoded_variables_file")
        if decoded:
            files_to_check.append(library_root / "buffers" / decoded)
    mesh = manifest.get("resources", {}).get("mesh", {}).get("mesh")
    if mesh:
        for key in ("obj_file", "mesh_json", "attributes_json", "attributes_bin"):
            rel = mesh.get(key)
            if rel:
                files_to_check.append(library_root / "meshes" / rel)
    for path in files_to_check:
        if not path.exists():
            warnings.append(f"Missing referenced file: {path}")
    return warnings


def build_manifest(args: argparse.Namespace, logger: logging.Logger, log_path: Optional[Path]) -> Dict[str, Any]:
    rd = rd_session.import_renderdoc(args.renderdoc_module_dir, logger)
    rd_session.initialise_replay_if_needed(rd, logger)
    cap = None
    controller = None
    start = time.perf_counter()
    try:
        cap, controller = rd_session.open_capture(rd, args.rdc, logger)
        action, pipe = rd_session.set_eid(controller, args.eid, logger)

        shaders, sw = shader_refs(args.out, args.eid)
        textures, tw = texture_refs(args.out, args.eid)
        buffers, bw = buffer_refs(args.out, args.eid)
        mesh, mw = mesh_ref(args.out, args.eid)
        warnings = sw + tw + bw + mw

        manifest = {
            "version": 1,
            "script": SCRIPT_NAME,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rdc": str(args.rdc),
            "eid": args.eid,
            "log_file": str(log_path) if log_path else None,
            "action": rd_session.action_to_summary(rd, controller, action),
            "pipeline": pipeline_state_summary(pipe, args.out, shaders),
            "resources": {
                "shaders": shaders,
                "textures": textures,
                "buffers": buffers,
                "mesh": mesh,
            },
            "warnings": warnings,
        }
        manifest["warnings"].extend(validate_refs(args.out, manifest))
        manifest["elapsed_seconds"] = round(time.perf_counter() - start, 3)

        out_path = args.out / "draws" / f"eid_{args.eid}" / "draw_manifest.json"
        write_json(out_path, manifest)
        args.test_log.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.test_log, {"manifest_path": str(out_path), "warnings": manifest["warnings"], "eid": args.eid})
        logger.info("Wrote draw manifest: %s", out_path)
        logger.info("Wrote manifest test log: %s", args.test_log)
        return manifest
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
        description="Build per-EID draw_manifest.json from extracted resources.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--rdc", type=Path, default=default_rdc, help="Path to .rdc capture.")
    parser.add_argument("--eid", type=int, default=default_eid, help="Target event ID.")
    parser.add_argument("--out", type=Path, default=default_out, help="Output root directory.")
    parser.add_argument(
        "--test-log",
        type=Path,
        default=TEST_DIR / f"build_manifest_eid_{default_eid}.json",
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
        manifest = build_manifest(args, logger, log_path)
        logger.info("build_draw_manifest passed: warnings=%d", len(manifest.get("warnings", [])))
        return 0 if not manifest.get("warnings") else 2
    except Exception as exc:
        logger.error("build_draw_manifest failed: %s", exc)
        logger.debug("Full traceback:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__" or "pyrenderdoc" in globals():
    raise SystemExit(main())
