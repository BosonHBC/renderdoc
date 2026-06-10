#!/usr/bin/env python3
"""Extract VS/PS shader raw bytes, disassembly, optional HLSL, and signatures."""

import argparse
import json
import logging
import os
import subprocess
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
DEFAULT_DECOMPILER = Path("D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/tools/hlsl_decompiler/HLSLDecompiler.exe")
SCRIPT_NAME = Path(globals().get("__file__", "extract_shaders.py")).stem

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import app_config  # noqa: E402
import library_db  # noqa: E402
import rd_session  # noqa: E402
from gbuffer_layout_match import DEFAULT_LAYOUTS, match_gbuffer_layout  # noqa: E402


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


def encoding_to_extension(encoding_text: str) -> str:
    upper = encoding_text.upper()
    if "DXIL" in upper:
        return ".dxil"
    if "DXBC" in upper:
        return ".dxbc"
    if "SPIRV" in upper or "SPIR-V" in upper:
        return ".spv"
    if "GLSL" in upper:
        return ".glsl"
    if "HLSL" in upper:
        return ".hlsl_src"
    return ".bin"


def encoding_to_decompiler_arg(encoding_text: str) -> Optional[str]:
    upper = encoding_text.upper()
    if "DXBC" in upper:
        return "-dxbc"
    if "DXIL" in upper:
        return "-dxil"
    if "SPIRV" in upper or "SPIR-V" in upper:
        return "-spirv"
    return None


def sig_parameter_to_dict(param: Any) -> Dict[str, Any]:
    result = {
        "varName": str(getattr(param, "varName", "")),
        "semanticName": str(getattr(param, "semanticName", "")),
        "semanticIdxName": str(getattr(param, "semanticIdxName", "")),
        "semanticIndex": int(getattr(param, "semanticIndex", 0)),
        "regIndex": int(getattr(param, "regIndex", 0)),
        "systemValue": enum_to_string(getattr(param, "systemValue", "")),
        "varType": enum_to_string(getattr(param, "varType", "")),
        "regChannelMask": int(getattr(param, "regChannelMask", 0)),
        "channelUsedMask": int(getattr(param, "channelUsedMask", 0)),
        "compCount": int(getattr(param, "compCount", 0)),
        "stream": int(getattr(param, "stream", 0)),
        "perPrimitiveRate": bool(getattr(param, "perPrimitiveRate", False)),
    }

    # Some APIs/RenderDoc versions expose interpolation modifiers separately.
    for optional_name in ("interpolation", "interpolationMode", "noPerspective", "centroid", "sample", "noInterpolation"):
        if hasattr(param, optional_name):
            value = getattr(param, optional_name)
            result[optional_name] = enum_to_string(value) if not isinstance(value, (bool, int, float, str)) else value
    text = " ".join(str(result.get(k, "")) for k in result)
    result["isNoInterpolation"] = "nointerpolation" in text.lower() or "constant" in text.lower()
    return result


def constant_block_to_dict(cb: Any) -> Dict[str, Any]:
    return {
        "name": str(getattr(cb, "name", "")),
        "fixedBindNumber": int(getattr(cb, "fixedBindNumber", 0)),
        "fixedBindSetOrSpace": int(getattr(cb, "fixedBindSetOrSpace", 0)),
        "bindArraySize": int(getattr(cb, "bindArraySize", 1)),
        "byteSize": int(getattr(cb, "byteSize", 0)),
        "bufferBacked": bool(getattr(cb, "bufferBacked", True)),
        "inlineDataBytes": bool(getattr(cb, "inlineDataBytes", False)),
        "compileConstants": bool(getattr(cb, "compileConstants", False)),
        "variableCount": len(getattr(cb, "variables", [])),
    }


def shader_resource_to_dict(res: Any) -> Dict[str, Any]:
    return {
        "name": str(getattr(res, "name", "")),
        "textureType": enum_to_string(getattr(res, "textureType", "")),
        "descriptorType": enum_to_string(getattr(res, "descriptorType", "")),
        "fixedBindNumber": int(getattr(res, "fixedBindNumber", 0)),
        "fixedBindSetOrSpace": int(getattr(res, "fixedBindSetOrSpace", 0)),
        "bindArraySize": int(getattr(res, "bindArraySize", 1)),
        "isTexture": bool(getattr(res, "isTexture", False)),
        "isReadOnly": bool(getattr(res, "isReadOnly", False)),
    }


def resource_format_to_dict(fmt: Any) -> Dict[str, Any]:
    if fmt is None:
        return {"name": "Unknown"}
    data: Dict[str, Any] = {}
    try:
        data["name"] = str(fmt.Name())
    except Exception:
        data["name"] = enum_to_string(fmt)
    for field in (
        "type",
        "compType",
        "compCount",
        "compByteWidth",
        "byteStride",
        "strname",
        "special",
    ):
        if hasattr(fmt, field):
            try:
                value = getattr(fmt, field)
                data[field] = enum_to_string(value) if field in ("type", "compType") else value
            except Exception:
                pass
    return data


def output_targets_to_dict(pipe: Any) -> List[Dict[str, Any]]:
    outputs = []
    for index, desc in enumerate(pipe.GetOutputTargets()):
        fmt = resource_format_to_dict(getattr(desc, "format", None))
        outputs.append(
            {
                "index": index,
                "resourceId": resource_id_to_string(getattr(desc, "resource", "")),
                "viewId": resource_id_to_string(getattr(desc, "view", "")),
                "type": enum_to_string(getattr(desc, "type", "")),
                "format": fmt.get("name", "Unknown"),
                "format_detail": fmt,
                "firstMip": int(getattr(desc, "firstMip", 0)),
                "numMips": int(getattr(desc, "numMips", 0)),
                "firstSlice": int(getattr(desc, "firstSlice", 0)),
                "numSlices": int(getattr(desc, "numSlices", 0)),
                "writeMask": None,
            }
        )
    try:
        blends = pipe.GetColorBlends()
        for index, blend in enumerate(blends):
            if index < len(outputs):
                outputs[index]["writeMask"] = int(getattr(blend, "writeMask", 0))
    except Exception:
        pass
    return outputs


def disassemble_shader(controller: Any, pipeline_id: Any, refl: Any, logger: logging.Logger) -> Tuple[str, str]:
    target = ""
    try:
        targets = controller.GetDisassemblyTargets(True)
        if targets:
            target = str(targets[0])
            logger.debug("Using disassembly target: %s", target)
    except Exception as exc:
        logger.warning("GetDisassemblyTargets failed, using default target: %s", exc)
    text = controller.DisassembleShader(pipeline_id, refl, target)
    return target, str(text)


def run_hlsl_decompiler(raw_path: Path, hlsl_path: Path, encoding_text: str, decompiler: Path, logger: logging.Logger) -> Dict[str, Any]:
    arg = encoding_to_decompiler_arg(encoding_text)
    result = {
        "attempted": False,
        "succeeded": False,
        "tool": str(decompiler),
        "arg": arg,
        "stdout": "",
        "stderr": "",
        "returncode": None,
        "error": None,
    }
    if arg is None:
        result["error"] = f"Unsupported encoding for HLSLDecompiler: {encoding_text}"
        return result
    if not decompiler.exists():
        result["error"] = f"Decompiler not found: {decompiler}"
        return result

    result["attempted"] = True
    cmd = [str(decompiler), str(raw_path), arg, str(hlsl_path)]
    logger.info("Running HLSL decompiler: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        result["returncode"] = proc.returncode
        result["stdout"] = proc.stdout.decode("utf-8", errors="replace")
        result["stderr"] = proc.stderr.decode("utf-8", errors="replace")
        result["succeeded"] = proc.returncode == 0 and hlsl_path.exists()
        if not result["succeeded"]:
            result["error"] = f"Decompiler failed with return code {proc.returncode}"
    except Exception as exc:
        result["error"] = str(exc)
        logger.warning("HLSL decompiler failed: %s", exc)
    return result


def extract_shader_stage(
    rd: Any,
    controller: Any,
    pipe: Any,
    stage: Any,
    stage_label: str,
    shader_dir: Path,
    db_path: Path,
    decompiler: Path,
    logger: logging.Logger,
    render_targets: Optional[List[Dict[str, Any]]] = None,
    gbuffer_layouts: Path = DEFAULT_LAYOUTS,
) -> Optional[Dict[str, Any]]:
    refl = pipe.GetShaderReflection(stage)
    if refl is None:
        logger.warning("No %s shader reflection bound", stage_label)
        return None

    raw_bytes = bytes(getattr(refl, "rawBytes", b""))
    encoding_text = enum_to_string(getattr(refl, "encoding", "Unknown"))
    entry = str(getattr(refl, "entryPoint", "")) or str(pipe.GetShaderEntryPoint(stage))
    shader_resource_id = resource_id_to_string(getattr(refl, "resourceId", pipe.GetShader(stage)))
    digest = library_db.sha256_bytes(raw_bytes)
    key = library_db.make_asset_key(stage_label.lower(), digest)
    ext = encoding_to_extension(encoding_text)

    stage_dir = shader_dir / stage_label
    stage_dir.mkdir(parents=True, exist_ok=True)
    raw_path = stage_dir / f"{stage_label}_{digest[:16]}{ext}"
    disasm_path = stage_dir / f"{stage_label}_{digest[:16]}.disasm.txt"
    hlsl_path = stage_dir / f"{stage_label}_{digest[:16]}.hlsl"

    if not raw_path.exists():
        raw_path.write_bytes(raw_bytes)
    pipeline_id = pipe.GetGraphicsPipelineObject()
    disasm_target, disasm = disassemble_shader(controller, pipeline_id, refl, logger)
    if not disasm_path.exists():
        disasm_path.write_text(disasm, encoding="utf-8", errors="replace")

    decompile_result = run_hlsl_decompiler(raw_path, hlsl_path, encoding_text, decompiler, logger)

    shader_item = {
        "stage": stage_label,
        "resourceId": shader_resource_id,
        "entryPoint": entry,
        "encoding": encoding_text,
        "sha256": digest,
        "raw_file": str(raw_path.relative_to(shader_dir.parent)),
        "disasm_file": str(disasm_path.relative_to(shader_dir.parent)),
        "hlsl_file": str(hlsl_path.relative_to(shader_dir.parent)) if hlsl_path.exists() else None,
        "disasm_target": disasm_target,
        "input_signature": [sig_parameter_to_dict(p) for p in getattr(refl, "inputSignature", [])],
        "output_signature": [sig_parameter_to_dict(p) for p in getattr(refl, "outputSignature", [])],
        "constant_blocks": [constant_block_to_dict(cb) for cb in getattr(refl, "constantBlocks", [])],
        "read_only_resources": [shader_resource_to_dict(r) for r in getattr(refl, "readOnlyResources", [])],
        "read_write_resources": [shader_resource_to_dict(r) for r in getattr(refl, "readWriteResources", [])],
        "samplers": [
            {
                "name": str(getattr(s, "name", "")),
                "fixedBindNumber": int(getattr(s, "fixedBindNumber", 0)),
                "fixedBindSetOrSpace": int(getattr(s, "fixedBindSetOrSpace", 0)),
                "bindArraySize": int(getattr(s, "bindArraySize", 1)),
            }
            for s in getattr(refl, "samplers", [])
        ],
        "decompile": decompile_result,
    }
    if stage_label == "PS" and render_targets is not None:
        shader_item["render_target_count"] = len(render_targets)
        shader_item["render_targets"] = render_targets
        try:
            shader_item["gbuffer_layout_match"] = match_gbuffer_layout(gbuffer_layouts, hlsl_path if hlsl_path.exists() else None, render_targets)
        except Exception as exc:
            shader_item["gbuffer_layout_match"] = {"error": str(exc), "layout_file": str(gbuffer_layouts)}

    registered, created = library_db.register_asset(db_path, key, shader_item, "shader", update_existing=True)
    logger.info(
        "%s shader %s: raw=%s disasm=%s hlsl=%s created=%s",
        stage_label,
        key,
        raw_path,
        disasm_path,
        hlsl_path if hlsl_path.exists() else "<failed>",
        created,
    )
    return {"id": key, "created": created, "item": registered}


def extract_shaders(args: argparse.Namespace, logger: logging.Logger, log_path: Optional[Path]) -> Dict[str, Any]:
    rd = rd_session.import_renderdoc(args.renderdoc_module_dir, logger)
    rd_session.initialise_replay_if_needed(rd, logger)
    cap = None
    controller = None
    start = time.perf_counter()
    try:
        cap, controller = rd_session.open_capture(rd, args.rdc, logger)
        action, pipe = rd_session.set_eid(controller, args.eid, logger)
        shader_dir = args.out / "libraries" / "shaders"
        shader_dir.mkdir(parents=True, exist_ok=True)
        db_path = shader_dir / "shader_library.json"

        render_targets = output_targets_to_dict(pipe)
        result: Dict[str, Any] = {
            "script": SCRIPT_NAME,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rdc": str(args.rdc),
            "eid": args.eid,
            "out": str(args.out),
            "log_file": str(log_path) if log_path else None,
            "action": rd_session.action_to_summary(rd, controller, action),
            "shaders": {},
            "render_target_count": len(render_targets),
            "render_targets": render_targets,
            "warnings": [],
        }

        stages = [("VS", rd.ShaderStage.Vertex), ("PS", rd.ShaderStage.Pixel)]
        for label, stage in stages:
            try:
                extracted = extract_shader_stage(
                    rd,
                    controller,
                    pipe,
                    stage,
                    label,
                    shader_dir,
                    db_path,
                    args.decompiler,
                    logger,
                    render_targets if label == "PS" else None,
                    args.gbuffer_layouts,
                )
                result["shaders"][label.lower()] = extracted
                if extracted and not extracted["item"].get("hlsl_file"):
                    result["warnings"].append(f"{label} HLSL output missing")
            except Exception as exc:
                logger.exception("Failed extracting %s shader", label)
                result["shaders"][label.lower()] = None
                result["warnings"].append(f"{label} extraction failed: {exc}")

        result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        args.test_log.parent.mkdir(parents=True, exist_ok=True)
        with args.test_log.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        logger.info("Wrote shader extraction test log: %s", args.test_log)

        if not result["shaders"].get("vs") or not result["shaders"].get("ps"):
            raise RuntimeError("VS/PS extraction did not both succeed")
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
    default_decompiler = Path(os.environ.get("RENDERDOC_EXTRACT_DECOMPILER", settings.decompiler))
    default_gbuffer_layouts = Path(os.environ.get("RENDERDOC_EXTRACT_GBUFFER_LAYOUTS", settings.gbuffer_layouts))
    default_no_log = app_config.env_bool("RENDERDOC_EXTRACT_NO_LOG", settings.no_log)

    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="Extract VS/PS shaders for one RenderDoc EID.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--rdc", type=Path, default=default_rdc, help="Path to .rdc capture.")
    parser.add_argument("--eid", type=int, default=default_eid, help="Target event ID.")
    parser.add_argument("--out", type=Path, default=default_out, help="Output root directory.")
    parser.add_argument(
        "--test-log",
        type=Path,
        default=TEST_DIR / f"extract_shaders_eid_{default_eid}.json",
        help="JSON test log output path.",
    )
    parser.add_argument("--decompiler", type=Path, default=default_decompiler, help="HLSLDecompiler.exe path.")
    parser.add_argument("--gbuffer-layouts", type=Path, default=default_gbuffer_layouts, help="GBuffer layout JSON path.")
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
        result = extract_shaders(args, logger, log_path)
        logger.info("extract_shaders passed with warnings=%s", len(result.get("warnings", [])))
        return 0
    except Exception as exc:
        logger.error("extract_shaders failed: %s", exc)
        logger.debug("Full traceback:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__" or "pyrenderdoc" in globals():
    raise SystemExit(main())
