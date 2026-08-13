import json
import logging
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import extract_shaders
import rd_session

RDC = Path(r"I:\RE9\RE9GraceRain_capture.rdc")
EID = 11730
OUT = Path(r"I:\PTGameDoc\TLUS2 RDC\TLUS2-PIX\RE9Grace\hair_shader\calcShading")
DECOMPILER = Path(r"C:\LQTech\UGit\renderdoc\RenderDocExtract\Tools\hlsl_decompiler\HLSLDecompiler.exe")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("extract_calcshading_cs")
rd = rd_session.import_renderdoc([], logger)
rd_session.initialise_replay_if_needed(rd, logger)
cap = None
controller = None
try:
    cap, controller = rd_session.open_capture(rd, RDC, logger)
    action, pipe = rd_session.set_eid(controller, EID, logger)
    shader_dir = OUT / "libraries" / "shaders"
    shader_dir.mkdir(parents=True, exist_ok=True)
    result = extract_shaders.extract_shader_stage(rd, controller, pipe, rd.ShaderStage.Compute, "CS", shader_dir, shader_dir / "shader_library.json", DECOMPILER, logger)
    summary = {"rdc": str(RDC), "eid": EID, "action": rd_session.action_to_summary(rd, controller, action), "shader": result}
    (OUT / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if result is None:
        raise RuntimeError("No compute shader is bound at EID 11730")
    item = result["item"]
    if not item.get("hlsl_file") or not item.get("decompile", {}).get("succeeded"):
        raise RuntimeError(f"HLSL decompilation failed: {item.get('decompile')}")
    print(json.dumps({"raw_file": item["raw_file"], "disasm_file": item["disasm_file"], "hlsl_file": item["hlsl_file"], "encoding": item["encoding"], "entryPoint": item["entryPoint"], "sha256": item["sha256"]}, ensure_ascii=False, indent=2))
finally:
    if controller is not None or cap is not None:
        rd_session.close_capture(rd, cap, controller, logger)
