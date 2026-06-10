#!/usr/bin/env python3
"""RenderDoc replay session helper for the EID Draw resource extractor.

This script is the first gate in RenderDocExtract. It verifies that a target
RDC can be opened, lists draw actions, and validates fixed smoke-test EIDs.
"""

import argparse
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path("D:/UGit/renderdoc/RenderDocExtract")
DEFAULT_TEST_RDC = Path(
    "D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc"
)
DEFAULT_TARGET_EIDS = [7643, 7955]
LOG_DIR = PROJECT_ROOT / "Logs"
TEST_DIR = PROJECT_ROOT / "Tests"
SCRIPT_NAME = Path(globals().get("__file__", "rd_session.py")).stem

if str(PROJECT_ROOT / "Scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "Scripts"))
import app_config  # noqa: E402


def _now_string() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def setup_logger(no_log: bool) -> Tuple[logging.Logger, Optional[Path]]:
    """Create console + optional file logger."""

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


def add_renderdoc_module_paths(extra_paths: Sequence[str], logger: logging.Logger) -> None:
    """Add likely RenderDoc Python module directories to sys.path.

    RenderDoc scripts can run inside qrenderdoc where `renderdoc` is already
    injected, or standalone where PYTHONPATH/module paths must be configured.
    This helper does not assume one fixed install layout.
    """

    candidates: List[Path] = []

    for p in extra_paths:
        if p:
            candidates.append(Path(p))

    env_paths = os.environ.get("RENDERDOC_PYTHON_MODULE_DIR", "")
    for p in env_paths.split(os.pathsep):
        if p:
            candidates.append(Path(p))

    candidates.extend(
        [
            Path("D:/UGit/renderdoc/x64/Release"),
            Path("D:/UGit/renderdoc/x64/Release/obj/qrenderdoc/generated"),
            Path("C:/LQTech/RenderDoc_1.44_64"),
            Path("C:/Program Files/RenderDoc"),
        ]
    )

    for candidate in candidates:
        try:
            if candidate.exists():
                text = str(candidate)
                if text not in sys.path:
                    sys.path.insert(0, text)
                    logger.debug("Added RenderDoc module candidate to sys.path: %s", text)
        except OSError:
            logger.debug("Failed probing module candidate: %s", candidate)


def import_renderdoc(extra_paths: Sequence[str], logger: logging.Logger):
    """Import the RenderDoc Python module with useful diagnostics on failure."""

    def validate_module(module: Any) -> Any:
        required = ["OpenCaptureFile", "ReplayOptions", "ResultCode"]
        missing = [name for name in required if not hasattr(module, name)]
        if missing:
            raise AttributeError(f"RenderDoc Python module is missing required attributes: {missing}")
        return module

    if "renderdoc" in sys.modules:
        return validate_module(sys.modules["renderdoc"])

    add_renderdoc_module_paths(extra_paths, logger)

    try:
        import renderdoc as rd  # type: ignore

        validate_module(rd)
        logger.info("Imported RenderDoc Python module: %s", getattr(rd, "__file__", "<builtin>"))
        return rd
    except Exception as exc:  # noqa: BLE001 - we want full import diagnostics
        logger.error("Failed to import usable RenderDoc Python module: %s", exc)
        logger.debug("sys.path during import failure:\n%s", "\n".join(sys.path))
        raise RuntimeError(
            "Cannot import a usable RenderDoc Python module. Run via qrenderdoc --python, "
            "or set RENDERDOC_PYTHON_MODULE_DIR / --renderdoc-module-dir to the directory "
            "containing RenderDoc's Python bindings that match the Python runtime."
        ) from exc


def result_succeeded(rd: Any, result: Any) -> bool:
    return result == rd.ResultCode.Succeeded


def resource_id_to_string(value: Any) -> str:
    try:
        return str(int(value))
    except Exception:  # noqa: BLE001
        return str(value)


def enum_to_string(value: Any) -> str:
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        return repr(value)


def action_flags_to_strings(rd: Any, flags: Any) -> List[str]:
    names = [
        "Drawcall",
        "Dispatch",
        "CmdList",
        "SetMarker",
        "PushMarker",
        "PopMarker",
        "MultiAction",
        "Copy",
        "Resolve",
        "Present",
        "Indexed",
        "Instanced",
        "Indirect",
        "Clear",
    ]
    out: List[str] = []
    for name in names:
        try:
            flag = getattr(rd.ActionFlags, name)
            if flags & flag:
                out.append(name)
        except Exception:  # noqa: BLE001
            continue
    if not out:
        out.append(enum_to_string(flags))
    return out


def iter_actions(actions: Iterable[Any]) -> Iterable[Any]:
    for action in actions:
        yield action
        for child in getattr(action, "children", []):
            yield from iter_actions(child.children if False else [child])


def flatten_actions(controller: Any) -> List[Any]:
    return list(iter_actions(controller.GetRootActions()))


def get_action_name(controller: Any, action: Any) -> str:
    try:
        return str(action.GetName(controller.GetStructuredFile()))
    except Exception:  # noqa: BLE001
        return str(getattr(action, "customName", ""))


def action_to_summary(rd: Any, controller: Any, action: Any, include_children_count: bool = True) -> Dict[str, Any]:
    flags = getattr(action, "flags", None)
    summary: Dict[str, Any] = {
        "eventId": int(getattr(action, "eventId", 0)),
        "actionId": int(getattr(action, "actionId", 0)),
        "name": get_action_name(controller, action),
        "flags": action_flags_to_strings(rd, flags),
        "numIndices": int(getattr(action, "numIndices", 0)),
        "numInstances": int(getattr(action, "numInstances", 0)),
        "baseVertex": int(getattr(action, "baseVertex", 0)),
        "indexOffset": int(getattr(action, "indexOffset", 0)),
        "vertexOffset": int(getattr(action, "vertexOffset", 0)),
        "instanceOffset": int(getattr(action, "instanceOffset", 0)),
        "drawIndex": int(getattr(action, "drawIndex", 0)),
        "outputs": [resource_id_to_string(x) for x in getattr(action, "outputs", [])],
        "depthOut": resource_id_to_string(getattr(action, "depthOut", "")),
        "isInstanced": int(getattr(action, "numInstances", 0)) > 1,
        "extracted_instance": 0 if int(getattr(action, "numInstances", 0)) > 1 else None,
    }
    if include_children_count:
        summary["childrenCount"] = len(getattr(action, "children", []))
        summary["eventCount"] = len(getattr(action, "events", []))
    return summary


def find_action_by_eid(controller: Any, eid: int) -> Optional[Any]:
    for action in flatten_actions(controller):
        if int(getattr(action, "eventId", 0)) == int(eid):
            return action
    return None


def open_capture(rd: Any, rdc_path: Path, logger: logging.Logger) -> Tuple[Any, Any]:
    if not rdc_path.exists():
        raise FileNotFoundError(f"RDC file does not exist: {rdc_path}")

    logger.info("Opening capture: %s", rdc_path)
    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(str(rdc_path), "", None)
    if not result_succeeded(rd, result):
        raise RuntimeError(f"Could not open capture {rdc_path}: {result}")

    if not cap.LocalReplaySupport():
        raise RuntimeError(f"Capture cannot be replayed locally: {rdc_path}")

    logger.info("Initialising replay controller")
    result, controller = cap.OpenCapture(rd.ReplayOptions(), None)
    if not result_succeeded(rd, result):
        raise RuntimeError(f"Could not initialise replay: {result}")

    return cap, controller


def close_capture(rd: Any, cap: Any, controller: Any, logger: logging.Logger) -> None:
    try:
        if controller is not None:
            controller.Shutdown()
    finally:
        if cap is not None:
            cap.Shutdown()

    if "pyrenderdoc" in globals():
        logger.debug("Running inside qrenderdoc; skipping global ShutdownReplay")
        return

    if hasattr(rd, "ShutdownReplay"):
        try:
            rd.ShutdownReplay()
        except Exception:  # noqa: BLE001
            logger.debug("ShutdownReplay failed or was not needed", exc_info=True)


def initialise_replay_if_needed(rd: Any, logger: logging.Logger) -> bool:
    """Initialise standalone replay. Returns True if this function initialised it."""

    if "pyrenderdoc" in globals():
        logger.info("Running inside qrenderdoc; standalone InitialiseReplay not needed")
        return False
    if not hasattr(rd, "InitialiseReplay"):
        raise RuntimeError(
            "The imported RenderDoc module cannot run standalone replay because it lacks "
            "InitialiseReplay. Use qrenderdoc.exe --python for this build, or provide a "
            "matching standalone RenderDoc Python module."
        )
    logger.info("Initialising standalone RenderDoc replay")
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    return True


def set_eid(controller: Any, eid: int, logger: logging.Logger) -> Tuple[Any, Any]:
    action = find_action_by_eid(controller, eid)
    if action is None:
        raise KeyError(f"EID {eid} was not found in action tree")
    logger.info("Setting frame event to EID %s", eid)
    controller.SetFrameEvent(int(eid), True)
    pipe = controller.GetPipelineState()
    return action, pipe


def pipeline_summary(rd: Any, controller: Any, eid: int, logger: logging.Logger) -> Dict[str, Any]:
    action, pipe = set_eid(controller, eid, logger)
    data: Dict[str, Any] = {"action": action_to_summary(rd, controller, action)}

    try:
        data["graphicsPipelineObject"] = resource_id_to_string(pipe.GetGraphicsPipelineObject())
    except Exception as exc:  # noqa: BLE001
        data["graphicsPipelineObject_error"] = str(exc)

    try:
        data["primitiveTopology"] = enum_to_string(pipe.GetPrimitiveTopology())
    except Exception as exc:  # noqa: BLE001
        data["primitiveTopology_error"] = str(exc)

    for stage_name in ["Vertex", "Pixel"]:
        try:
            stage = getattr(rd.ShaderStage, stage_name)
            refl = pipe.GetShaderReflection(stage)
            data[f"{stage_name.lower()}Shader"] = {
                "resourceId": resource_id_to_string(pipe.GetShader(stage)),
                "entryPoint": str(pipe.GetShaderEntryPoint(stage)),
                "hasReflection": refl is not None,
                "inputSignatureCount": len(getattr(refl, "inputSignature", [])) if refl else 0,
                "outputSignatureCount": len(getattr(refl, "outputSignature", [])) if refl else 0,
                "constantBlockCount": len(getattr(refl, "constantBlocks", [])) if refl else 0,
                "readOnlyResourceCount": len(getattr(refl, "readOnlyResources", [])) if refl else 0,
                "readWriteResourceCount": len(getattr(refl, "readWriteResources", [])) if refl else 0,
            }
        except Exception as exc:  # noqa: BLE001
            data[f"{stage_name.lower()}Shader_error"] = str(exc)

    try:
        data["vertexInputCount"] = len(pipe.GetVertexInputs())
        data["vertexBufferCount"] = len(pipe.GetVBuffers())
        ibuffer = pipe.GetIBuffer()
        data["indexBuffer"] = {
            "resourceId": resource_id_to_string(ibuffer.resourceId),
            "byteOffset": int(ibuffer.byteOffset),
            "byteStride": int(ibuffer.byteStride),
        }
    except Exception as exc:  # noqa: BLE001
        data["inputAssembly_error"] = str(exc)

    try:
        outputs = pipe.GetOutputTargets()
        data["outputTargetCount"] = len(outputs)
        data["outputTargets"] = [
            {
                "resourceId": resource_id_to_string(o.resource),
                "viewId": resource_id_to_string(o.view),
                "format": enum_to_string(o.format),
                "firstMip": int(getattr(o, "firstMip", 0)),
                "numMips": int(getattr(o, "numMips", 0)),
                "firstSlice": int(getattr(o, "firstSlice", 0)),
                "numSlices": int(getattr(o, "numSlices", 0)),
            }
            for o in outputs
        ]
    except Exception as exc:  # noqa: BLE001
        data["outputTargets_error"] = str(exc)

    try:
        blends = pipe.GetColorBlends()
        data["colorBlendCount"] = len(blends)
        data["colorBlends"] = [
            {
                "enabled": bool(b.enabled),
                "logicOperationEnabled": bool(b.logicOperationEnabled),
                "colorBlend": enum_to_string(b.colorBlend),
                "alphaBlend": enum_to_string(b.alphaBlend),
                "logicOperation": enum_to_string(b.logicOperation),
                "writeMask": int(b.writeMask),
            }
            for b in blends
        ]
    except Exception as exc:  # noqa: BLE001
        data["colorBlends_error"] = str(exc)

    return data


def build_report(rd: Any, controller: Any, limit: int, target_eids: Sequence[int], logger: logging.Logger) -> Dict[str, Any]:
    logger.info("Flattening action tree")
    actions = flatten_actions(controller)
    logger.info("Found %d actions", len(actions))

    draw_like = [a for a in actions if int(getattr(a, "numIndices", 0)) > 0 or int(getattr(a, "numInstances", 0)) > 0]
    logger.info("Found %d draw-like actions", len(draw_like))

    report: Dict[str, Any] = {
        "script": SCRIPT_NAME,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "action_count": len(actions),
        "draw_like_action_count": len(draw_like),
        "limit": limit,
        "draws": [action_to_summary(rd, controller, a) for a in draw_like[: max(limit, 0)]],
        "target_eids": list(target_eids),
        "target_actions": {},
        "validation": {
            "required_eids_found": True,
            "eid_7955_instanced": None,
            "errors": [],
        },
    }

    for eid in target_eids:
        action = find_action_by_eid(controller, eid)
        if action is None:
            report["target_actions"][str(eid)] = None
            report["validation"]["required_eids_found"] = False
            report["validation"]["errors"].append(f"EID {eid} not found")
            logger.warning("Target EID %s not found", eid)
            continue

        summary = action_to_summary(rd, controller, action)
        try:
            summary["pipeline"] = pipeline_summary(rd, controller, eid, logger)
        except Exception as exc:  # noqa: BLE001
            summary["pipeline_error"] = str(exc)
            logger.warning("Pipeline summary failed for EID %s: %s", eid, exc)
        report["target_actions"][str(eid)] = summary
        logger.info("Target EID %s found: numInstances=%s", eid, summary.get("numInstances"))

    eid_7955 = report["target_actions"].get("7955")
    if eid_7955:
        report["validation"]["eid_7955_instanced"] = int(eid_7955.get("numInstances", 0)) > 1
        if not report["validation"]["eid_7955_instanced"]:
            report["validation"]["errors"].append("EID 7955 exists but numInstances <= 1")
    else:
        report["validation"]["eid_7955_instanced"] = False

    return report


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    if argv is None and not hasattr(sys, "argv"):
        argv = []

    settings = app_config.with_env_overrides(app_config.load_settings())
    default_rdc = Path(os.environ.get("RENDERDOC_EXTRACT_RDC", settings.rdc))
    module_defaults = list(settings.renderdoc_module_dirs or [])
    default_no_log = app_config.env_bool("RENDERDOC_EXTRACT_NO_LOG", settings.no_log)

    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="Open a RenderDoc capture, list draw actions, and validate fixed EID smoke tests.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--rdc", type=Path, default=default_rdc, help="Path to the .rdc capture file.")
    parser.add_argument("--list-draws", action="store_true", help="List draw-like actions to JSON output.")
    parser.add_argument("--limit", type=int, default=50, help="Number of draw-like actions to include.")
    parser.add_argument("--eid", type=int, action="append", default=[], help="Extra EID to locate and summarise. Can be repeated.")
    parser.add_argument(
        "--out",
        type=Path,
        default=TEST_DIR / "rd_session_draws.json",
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--renderdoc-module-dir",
        action="append",
        default=module_defaults,
        help="Directory containing RenderDoc's Python bindings. Can be repeated.",
    )
    parser.add_argument("--no-log", dest="no_log", action="store_true", default=default_no_log, help="Disable log file output.")
    parser.add_argument("-Nolog", dest="no_log", action="store_true", help="Disable log file output, RenderDoc-style alias.")
    args, unknown = parser.parse_known_args(argv)
    setattr(args, "unknown_args", unknown)
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logger, log_path = setup_logger(args.no_log)
    start = time.perf_counter()

    logger.info("Command line: %s", " ".join(getattr(sys, "argv", [SCRIPT_NAME])))
    if getattr(args, "unknown_args", None):
        logger.info("Ignored unknown host arguments: %s", args.unknown_args)
    logger.info("RDC path: %s", args.rdc)
    logger.info("Output path: %s", args.out)
    if log_path:
        logger.info("Log path: %s", log_path)

    rd = None
    cap = None
    controller = None

    try:
        rd = import_renderdoc(args.renderdoc_module_dir, logger)
        initialise_replay_if_needed(rd, logger)
        cap, controller = open_capture(rd, args.rdc, logger)

        target_eids = sorted(set(DEFAULT_TARGET_EIDS + list(args.eid)))
        report = build_report(rd, controller, args.limit, target_eids, logger)
        report["rdc"] = str(args.rdc)
        report["log_file"] = str(log_path) if log_path else None
        report["elapsed_seconds"] = round(time.perf_counter() - start, 3)

        write_json(args.out, report)
        logger.info("Wrote report: %s", args.out)

        validation_errors = report.get("validation", {}).get("errors", [])
        if validation_errors:
            logger.error("Validation failed: %s", validation_errors)
            return 2

        logger.info("rd_session validation passed")
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("rd_session failed: %s", exc)
        logger.debug("Full traceback:\n%s", traceback.format_exc())
        return 1
    finally:
        if rd is not None:
            try:
                close_capture(rd, cap, controller, logger)
            except Exception:  # noqa: BLE001
                logger.debug("Failed during capture shutdown", exc_info=True)
        logger.info("Elapsed seconds: %.3f", time.perf_counter() - start)


if __name__ == "__main__" or "pyrenderdoc" in globals():
    raise SystemExit(main())
