#!/usr/bin/env python3
"""Extract a representative PS PRIMITIVE_ID from RenderDoc PostVS data."""

import argparse
import json
import logging
import os
import struct
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

PROJECT_ROOT = Path("D:/UGit/renderdoc/RenderDocExtract")
SCRIPT_DIR = PROJECT_ROOT / "Scripts"
OUTPUT_ROOT = PROJECT_ROOT / "Output"
LOG_DIR = PROJECT_ROOT / "Logs"
TEST_DIR = PROJECT_ROOT / "Tests"
DEFAULT_RDC = Path("D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc")
DEFAULT_EID = 7643
SCRIPT_NAME = Path(globals().get("__file__", "extract_primitive_context.py")).stem
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import app_config  # noqa: E402
import rd_session  # noqa: E402


def _now_string():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def setup_logger(no_log: bool):
    logger = logging.getLogger(SCRIPT_NAME)
    logger.handlers.clear(); logger.setLevel(logging.DEBUG); logger.propagate = False
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    ch = logging.StreamHandler(); ch.setLevel(logging.INFO); ch.setFormatter(fmt); logger.addHandler(ch)
    if no_log: return logger, None
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / f"{SCRIPT_NAME}_{_now_string()}.log"
    fh = logging.FileHandler(log, encoding="utf-8"); fh.setLevel(logging.DEBUG); fh.setFormatter(fmt); logger.addHandler(fh)
    return logger, log


def var_byte_width(rd: Any, var_type: Any) -> int:
    try:
        return int(rd.VarTypeByteSize(var_type))
    except Exception:
        return 4


def extract_context(args, logger, log_path):
    rd = rd_session.import_renderdoc(args.renderdoc_module_dir, logger)
    rd_session.initialise_replay_if_needed(rd, logger)
    cap = controller = None
    start = time.perf_counter()
    try:
        cap, controller = rd_session.open_capture(rd, args.rdc, logger)
        action, pipe = rd_session.set_eid(controller, args.eid, logger)
        mesh = controller.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
        refl = pipe.GetShaderReflection(rd.ShaderStage.Vertex)
        attrs = []
        posidx = 0
        for sig in refl.outputSignature:
            if pipe.GetRasterizedStream() >= 0:
                if sig.stream != pipe.GetRasterizedStream(): continue
            else:
                if sig.stream != 0: continue
            if sig.systemValue == rd.ShaderBuiltin.OutputIndices: continue
            if sig.systemValue == rd.ShaderBuiltin.Position: posidx = len(attrs)
            attrs.append({"semantic": str(sig.semanticName), "semanticIdxName": str(sig.semanticIdxName), "regIndex": int(sig.regIndex), "compCount": int(sig.compCount), "varType": str(sig.varType), "systemValue": str(sig.systemValue), "byteWidth": var_byte_width(rd, sig.varType), "sig": sig})
        if posidx > 0:
            pos = attrs[posidx]; del attrs[posidx]; attrs.insert(0, pos)
        acc = 0; primitive_offset = None
        aligned = bool(pipe.HasAlignedPostVSData(rd.MeshDataStage.VSOut))
        for a in attrs:
            elem = 8 if int(a["byteWidth"]) > 4 else 4
            comp = int(a["compCount"])
            align = elem * 2 if comp == 2 else elem * 4 if comp > 2 else elem
            if aligned and (acc % align) != 0:
                acc += align - (acc % align)
            a["offset"] = acc; a["size"] = elem * comp
            if a["semantic"] == "PRIMITIVE_ID": primitive_offset = acc
            acc += elem * comp
        values = []
        if primitive_offset is not None:
            count = min(int(args.sample_count), int(mesh.numIndices))
            data = bytes(controller.GetBufferData(mesh.vertexResourceId, mesh.vertexByteOffset, min(mesh.vertexByteSize, mesh.vertexByteStride * count)))
            for i in range(count):
                off = i * mesh.vertexByteStride + primitive_offset
                if off + 4 <= len(data): values.append(struct.unpack_from("=I", data, off)[0])
        context = {
            "script": SCRIPT_NAME, "generated_at": datetime.now().isoformat(timespec="seconds"), "rdc": str(args.rdc), "eid": args.eid,
            "log_file": str(log_path) if log_path else None,
            "mesh_stride": int(mesh.vertexByteStride), "postvs_aligned": aligned, "calculated_stride": acc, "primitive_offset": primitive_offset,
            "sample_count": len(values), "first_primitive_ids": values, "unique_primitive_ids": sorted(set(values)),
            "representative_primitive_id": values[0] if values else None,
            "is_constant_in_sample": len(set(values)) == 1 if values else False,
            "fields": [{k:v for k,v in a.items() if k != "sig"} for a in attrs],
            "elapsed_seconds": round(time.perf_counter() - start, 3),
        }
        out = args.out / "draws" / f"eid_{args.eid}" / "primitive_context.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.test_log.parent.mkdir(parents=True, exist_ok=True)
        args.test_log.write_text(json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        logger.info("Wrote primitive context: %s", out)
        return context
    finally:
        if controller is not None or cap is not None:
            rd_session.close_capture(rd, cap, controller, logger)


def parse_args(argv: Optional[Sequence[str]] = None):
    if argv is None and not hasattr(sys, "argv"):
        argv = []
    settings = app_config.with_env_overrides(app_config.load_settings())
    eid = int(os.environ.get("RENDERDOC_EXTRACT_EID", settings.eid))
    rdc = Path(os.environ.get("RENDERDOC_EXTRACT_RDC", settings.rdc))
    out = Path(os.environ.get("RENDERDOC_EXTRACT_OUT", settings.out))
    sample_count = app_config.env_int("RENDERDOC_EXTRACT_PRIMITIVE_SAMPLE_COUNT", settings.primitive_sample_count)
    default_no_log = app_config.env_bool("RENDERDOC_EXTRACT_NO_LOG", settings.no_log)
    p = argparse.ArgumentParser(prog=SCRIPT_NAME)
    p.add_argument("--rdc", type=Path, default=rdc)
    p.add_argument("--eid", type=int, default=eid)
    p.add_argument("--out", type=Path, default=out)
    p.add_argument("--sample-count", type=int, default=sample_count)
    p.add_argument("--test-log", type=Path, default=TEST_DIR / f"primitive_context_eid_{eid}.json")
    p.add_argument("--renderdoc-module-dir", action="append", default=[])
    p.add_argument("--no-log", action="store_true", default=default_no_log)
    p.add_argument("-Nolog", dest="no_log", action="store_true")
    args, unknown = p.parse_known_args(argv); setattr(args, "unknown_args", unknown); return args


def main(argv=None):
    args = parse_args(argv)
    logger, log_path = setup_logger(args.no_log)
    try:
        ctx = extract_context(args, logger, log_path)
        logger.info("primitive_context passed: representative=%s constant=%s", ctx.get("representative_primitive_id"), ctx.get("is_constant_in_sample"))
        return 0
    except Exception as exc:
        logger.exception("extract_primitive_context failed: %s", exc)
        return 1

if __name__ == "__main__" or "pyrenderdoc" in globals():
    raise SystemExit(main())
