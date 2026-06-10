#!/usr/bin/env python3
"""One-click EID resource extraction orchestration.

This script intentionally runs the RenderDoc-dependent scripts via qrenderdoc.exe
because this repository build exposes replay through qrenderdoc's embedded
Python environment rather than a standalone Python module.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import app_config

PROJECT_ROOT = app_config.PROJECT_ROOT
SCRIPT_DIR = PROJECT_ROOT / "Scripts"
OUTPUT_ROOT = app_config.OUTPUT_ROOT
LOG_DIR = app_config.LOG_DIR
TEST_DIR = app_config.TEST_DIR
DEFAULT_RDC = app_config.FALLBACK_RDC
DEFAULT_QRENDERDOC = app_config.FALLBACK_QRENDERDOC
DEFAULT_RENDERDOC = app_config.FALLBACK_RENDERDOC
DEFAULT_EID = app_config.FALLBACK_EID
SCRIPT_NAME = Path(globals().get("__file__", "extract_eid.py")).stem
PIPELINE_STEPS = [
    ("shaders", "extract_shaders.py", "qrenderdoc"),
    ("textures", "extract_textures.py", "qrenderdoc"),
    ("buffers", "extract_buffers.py", "qrenderdoc"),
    ("mesh", "extract_mesh.py", "qrenderdoc"),
    ("manifest", "build_draw_manifest.py", "qrenderdoc"),
    ("validate_extraction", "validate_extraction.py", "qrenderdoc"),
    ("primitive_context", "extract_primitive_context.py", "qrenderdoc"),
    ("material_slices", "material_hlsl_slice.py", "python"),
    ("validate_material_slices", "validate_material_slices.py", "python"),
]


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


def build_step_command(qrenderdoc: Path, script_name: str, runner: str, args: argparse.Namespace) -> List[str]:
    script_path = SCRIPT_DIR / script_name
    if runner == "qrenderdoc":
        return [str(qrenderdoc), "--python", str(script_path)]
    command = [sys.executable, str(script_path), "--eid", str(args.eid), "--out", str(args.out)]
    if script_name == "material_hlsl_slice.py":
        command.extend(["--layouts", str(args.gbuffer_layouts)])
    if script_name == "reconstruct_svt.py":
        command.extend([
            "--tile-size", str(args.svt_tile_size),
            "--border", str(args.svt_border),
            "--tile-pitch", str(args.svt_tile_pitch),
        ])
    return command


def build_step_env(args: argparse.Namespace, env_base: Dict[str, str]) -> Dict[str, str]:
    env = dict(env_base)
    env["RENDERDOC_EXTRACT_RDC"] = str(args.rdc)
    env["RENDERDOC_EXTRACT_EID"] = str(args.eid)
    env["RENDERDOC_EXTRACT_OUT"] = str(args.out)
    env["RENDERDOC_EXTRACT_QRENDERDOC"] = str(args.qrenderdoc)
    env["RENDERDOC_EXTRACT_RENDERDOC"] = str(args.renderdoc)
    env["RENDERDOC_EXTRACT_DECOMPILER"] = str(args.decompiler)
    env["RENDERDOC_EXTRACT_GBUFFER_LAYOUTS"] = str(args.gbuffer_layouts)
    env["RENDERDOC_EXTRACT_MESH_UNIT"] = str(args.unit)
    env["RENDERDOC_EXTRACT_MESH_MAX_INDICES"] = str(args.max_indices)
    env["RENDERDOC_EXTRACT_JSON_VERTEX_LIMIT"] = str(args.json_vertex_limit)
    env["RENDERDOC_EXTRACT_TEXTURE_LIB"] = str(args.texture_lib or "")
    env["RENDERDOC_EXTRACT_TEXTURES_ONLY_USED"] = "1" if args.only_used else "0"
    env["RENDERDOC_EXTRACT_PRIMITIVE_SAMPLE_COUNT"] = str(args.primitive_sample_count)
    env["RENDERDOC_EXTRACT_SVT_TILE_SIZE"] = str(args.svt_tile_size)
    env["RENDERDOC_EXTRACT_SVT_BORDER"] = str(args.svt_border)
    env["RENDERDOC_EXTRACT_SVT_TILE_PITCH"] = str(args.svt_tile_pitch)
    if args.no_log:
        env["RENDERDOC_EXTRACT_NO_LOG"] = "1"
    module_dirs = [str(p) for p in args.renderdoc_module_dir if str(p)]
    if module_dirs:
        env["RENDERDOC_PYTHON_MODULE_DIR"] = os.pathsep.join(module_dirs)
    return env


def run_step(
    qrenderdoc: Path,
    step_name: str,
    script_name: str,
    args: argparse.Namespace,
    env_base: Dict[str, str],
    logger: logging.Logger,
    runner: str,
) -> Dict[str, Any]:
    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Step script missing: {script_path}")
    env = build_step_env(args, env_base)
    command = build_step_command(qrenderdoc, script_name, runner, args)
    logger.info("Running step %s [%s]: %s", step_name, runner, " ".join(command))
    start = time.perf_counter()
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=args.step_timeout)
    elapsed = round(time.perf_counter() - start, 3)
    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    if stdout:
        logger.debug("%s stdout:\n%s", step_name, stdout)
    if stderr:
        logger.debug("%s stderr:\n%s", step_name, stderr)
    result = {
        "step": step_name,
        "script": str(script_path),
        "returncode": proc.returncode,
        "elapsed_seconds": elapsed,
        "stdout": stdout,
        "stderr": stderr,
    }
    if proc.returncode != 0:
        raise RuntimeError(f"Step {step_name} failed with return code {proc.returncode}")
    logger.info("Step %s passed in %.3fs", step_name, elapsed)
    return result


def collect_outputs(out_root: Path, eid: int) -> Dict[str, Any]:
    tests = PROJECT_ROOT / "Tests"
    return {
        "shader_test": str(tests / f"extract_shaders_eid_{eid}.json"),
        "texture_test": str(tests / f"extract_textures_eid_{eid}.json"),
        "buffer_test": str(tests / f"extract_buffers_eid_{eid}.json"),
        "mesh_test": str(tests / f"extract_mesh_eid_{eid}.json"),
        "manifest_test": str(tests / f"build_manifest_eid_{eid}.json"),
        "validate_extraction_test": str(tests / f"validate_extraction_eid_{eid}.json"),
        "material_slices_validation": str(tests / f"validate_material_slices_eid_{eid}.json"),
        "draw_manifest": str(out_root / "draws" / f"eid_{eid}" / "draw_manifest.json"),
        "primitive_context": str(out_root / "draws" / f"eid_{eid}" / "primitive_context.json"),
        "material_slices_hlsl": str(out_root / "draws" / f"eid_{eid}" / "material_slices.hlsl"),
        "material_slices_json": str(out_root / "draws" / f"eid_{eid}" / "material_slices.json"),
        "svt_reconstruction_json": str(out_root / "draws" / f"eid_{eid}" / "svt_reconstruction" / "svt_reconstruction.json"),
        "svt_replacement_hlsl": str(out_root / "draws" / f"eid_{eid}" / "svt_reconstruction" / "svt_sampling_replacement.hlsl"),
        "shader_library": str(out_root / "libraries" / "shaders" / "shader_library.json"),
        "texture_library": str(out_root / "libraries" / "textures" / "texture_library.json"),
        "buffer_library": str(out_root / "libraries" / "buffers" / "buffer_library.json"),
        "mesh_library": str(out_root / "libraries" / "meshes" / "mesh_library.json"),
    }


def validate_outputs(outputs: Dict[str, str]) -> List[str]:
    warnings = []
    for name, path_text in outputs.items():
        path = Path(path_text)
        if not path.exists():
            warnings.append(f"Missing output {name}: {path}")
    manifest_path = Path(outputs["draw_manifest"])
    manifest = read_json(manifest_path, None)
    if not manifest:
        warnings.append(f"Cannot read draw manifest: {manifest_path}")
    else:
        warnings.extend(manifest.get("warnings", []))
    return warnings


def settings_from_args(args: argparse.Namespace) -> app_config.AppSettings:
    return app_config.AppSettings(
        rdc=str(args.rdc),
        eid=int(args.eid),
        out=str(args.out),
        qrenderdoc=str(args.qrenderdoc),
        renderdoc=str(args.renderdoc),
        decompiler=str(args.decompiler),
        gbuffer_layouts=str(args.gbuffer_layouts),
        step_timeout=int(args.step_timeout),
        no_log=bool(args.no_log),
        mesh_unit=str(args.unit),
        mesh_max_indices=int(args.max_indices),
        mesh_json_vertex_limit=int(args.json_vertex_limit),
        texture_lib=str(args.texture_lib or ""),
        textures_only_used=bool(args.only_used),
        primitive_sample_count=int(args.primitive_sample_count),
        renderdoc_module_dirs=[str(p) for p in args.renderdoc_module_dir if str(p)],
        run_svt_reconstruction=bool(args.run_svt_reconstruction),
        svt_tile_size=int(args.svt_tile_size),
        svt_border=int(args.svt_border),
        svt_tile_pitch=int(args.svt_tile_pitch),
    )


def run_pipeline(args: argparse.Namespace, logger: logging.Logger, log_path: Optional[Path]) -> Dict[str, Any]:
    if not args.qrenderdoc.exists():
        raise FileNotFoundError(f"qrenderdoc.exe not found: {args.qrenderdoc}")
    if not args.rdc.exists():
        raise FileNotFoundError(f"RDC not found: {args.rdc}")
    args.out.mkdir(parents=True, exist_ok=True)
    env_base = os.environ.copy()

    summary: Dict[str, Any] = {
        "script": SCRIPT_NAME,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rdc": str(args.rdc),
        "eid": args.eid,
        "out": str(args.out),
        "qrenderdoc": str(args.qrenderdoc),
        "renderdoc": str(args.renderdoc),
        "decompiler": str(args.decompiler),
        "gbuffer_layouts": str(args.gbuffer_layouts),
        "mesh_unit": args.unit,
        "mesh_max_indices": args.max_indices,
        "mesh_json_vertex_limit": args.json_vertex_limit,
        "texture_lib": str(args.texture_lib) if args.texture_lib else None,
        "textures_only_used": args.only_used,
        "primitive_sample_count": args.primitive_sample_count,
        "renderdoc_module_dir": [str(p) for p in args.renderdoc_module_dir],
        "log_file": str(log_path) if log_path else None,
        "steps": [],
        "outputs": {},
        "warnings": [],
    }
    start = time.perf_counter()
    # Build effective pipeline steps: add SVT step if enabled
    steps = list(PIPELINE_STEPS)
    if getattr(args, "run_svt_reconstruction", False):
        steps.append(("svt_reconstruction", "reconstruct_svt.py", "python"))
    for step_name, script_name, runner in steps:
        summary["steps"].append(run_step(args.qrenderdoc, step_name, script_name, args, env_base, logger, runner))
    summary["outputs"] = collect_outputs(args.out, args.eid)
    summary["warnings"] = validate_outputs(summary["outputs"])
    summary["elapsed_seconds"] = round(time.perf_counter() - start, 3)
    args.test_log.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.test_log, summary)
    logger.info("Wrote extract_eid summary: %s", args.test_log)
    if summary["warnings"]:
        logger.warning("extract_eid completed with warnings: %s", summary["warnings"])
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    settings = app_config.with_env_overrides(app_config.load_settings())
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="Run the full RenderDocExtract EID extraction pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--rdc", type=Path, default=Path(settings.rdc), help="Path to .rdc capture.")
    parser.add_argument("--eid", type=int, default=settings.eid, help="Target event ID.")
    parser.add_argument("--out", type=Path, default=Path(settings.out), help="Output root directory.")
    parser.add_argument("--qrenderdoc", type=Path, default=Path(settings.qrenderdoc), help="qrenderdoc.exe path.")
    parser.add_argument("--renderdoc", type=Path, default=Path(settings.renderdoc), help="renderdoc.exe path, stored for tooling/future use.")
    parser.add_argument("--decompiler", type=Path, default=Path(settings.decompiler), help="HLSLDecompiler.exe path.")
    parser.add_argument("--gbuffer-layouts", type=Path, default=Path(settings.gbuffer_layouts), help="GBuffer layout JSON path.")
    parser.add_argument("--unit", choices=["m", "cm"], default=settings.mesh_unit, help="Position unit for OBJ preview.")
    parser.add_argument("--max-indices", type=int, default=settings.mesh_max_indices, help="Safety cap for extracted mesh indices.")
    parser.add_argument("--json-vertex-limit", type=int, default=settings.mesh_json_vertex_limit, help="Max decoded vertices included in attributes JSON preview.")
    parser.add_argument("--texture-lib", type=Path, default=Path(settings.texture_lib) if settings.texture_lib else None, help="Optional external texture library directory.")
    parser.add_argument("--only-used", dest="only_used", action="store_true", default=settings.textures_only_used, help="Only extract descriptors not statically unused.")
    parser.add_argument("--all-bound", dest="only_used", action="store_false", help="Extract all bound/declarative texture descriptors.")
    parser.add_argument("--primitive-sample-count", type=int, default=settings.primitive_sample_count, help="PostVS primitive sample count.")
    parser.add_argument("--renderdoc-module-dir", action="append", default=list(settings.renderdoc_module_dirs), help="RenderDoc Python binding dir.")
    parser.add_argument("--step-timeout", type=int, default=settings.step_timeout, help="Timeout seconds for each qrenderdoc step.")
    parser.add_argument(
        "--test-log",
        type=Path,
        default=TEST_DIR / f"extract_eid_{settings.eid}.json",
        help="Pipeline summary JSON path.",
    )
    parser.add_argument("--save-config", action="store_true", help="Persist effective CLI settings to Config/app_settings.json before running.")
    parser.add_argument("--no-log", dest="no_log", action="store_true", default=settings.no_log, help="Disable orchestrator log file output.")
    parser.add_argument("-Nolog", dest="no_log", action="store_true", help="Disable orchestrator log file output.")
    # SVT reconstruction
    parser.add_argument("--run-svt-reconstruction", dest="run_svt_reconstruction", action="store_true",
                        default=settings.run_svt_reconstruction, help="Run SVT reconstruction step.")
    parser.add_argument("--no-svt-reconstruction", dest="run_svt_reconstruction", action="store_false",
                        help="Skip SVT reconstruction step.")
    parser.add_argument("--svt-tile-size", type=int, default=settings.svt_tile_size)
    parser.add_argument("--svt-border", type=int, default=settings.svt_border)
    parser.add_argument("--svt-tile-pitch", type=int, default=settings.svt_tile_pitch)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.save_config:
        app_config.save_settings(settings_from_args(args))
    logger, log_path = setup_logger(args.no_log)
    logger.info("Command line: %s", " ".join(getattr(sys, "argv", [SCRIPT_NAME])))
    logger.info("RDC path: %s", args.rdc)
    logger.info("EID: %s", args.eid)
    logger.info("Output root: %s", args.out)
    logger.info("qrenderdoc: %s", args.qrenderdoc)
    logger.info("renderdoc: %s", args.renderdoc)
    if log_path:
        logger.info("Log path: %s", log_path)
    try:
        summary = run_pipeline(args, logger, log_path)
        logger.info("extract_eid passed: elapsed=%ss warnings=%d", summary["elapsed_seconds"], len(summary["warnings"]))
        return 0 if not summary["warnings"] else 2
    except Exception as exc:
        logger.exception("extract_eid failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
