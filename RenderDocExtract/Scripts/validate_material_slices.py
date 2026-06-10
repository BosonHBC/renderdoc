#!/usr/bin/env python3
"""Validate generated material HLSL slices structurally and source placeholder mappings."""

import argparse
import json
from pathlib import Path
from typing import Any, Optional, Sequence

import app_config

PROJECT_ROOT = app_config.PROJECT_ROOT
OUTPUT_ROOT = app_config.OUTPUT_ROOT
TEST_DIR = app_config.TEST_DIR


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate(eid: int, out_root: Path) -> dict:
    path = out_root / "draws" / f"eid_{eid}" / "material_slices.json"
    hlsl_path = out_root / "draws" / f"eid_{eid}" / "material_slices.hlsl"
    errors = []
    warnings = []
    summary = read_json(path) if path.exists() else {"functions": []}
    text = hlsl_path.read_text(encoding="utf-8", errors="ignore") if hlsl_path.exists() else ""
    if not path.exists():
        errors.append(f"Missing material_slices.json: {path}")
    if not hlsl_path.exists():
        errors.append(f"Missing material_slices.hlsl: {hlsl_path}")
    # Resource declaration sanity: material slices should copy source declarations for lookup.
    for required in ("cbuffers", "resources", "declaration_lines"):
        if required not in summary.get("resource_declarations", {}):
            errors.append(f"Missing resource_declarations.{required}")
    if "Buffer<" not in text and "StructuredBuffer" not in text:
        warnings.append("No Buffer/StructuredBuffer declaration text found in slice HLSL")
    if "Texture2D" not in text:
        warnings.append("No Texture2D declaration text found in slice HLSL")
    if "cbuffer" not in text:
        errors.append("No cbuffer declaration text found in slice HLSL")

    for fn in summary.get("functions", []):
        prop = fn.get("property")
        if f"void frag_main_{prop}()" not in text:
            errors.append(f"Missing function frag_main_{prop}")
            continue
        if fn.get("targets") and f"MF_{prop}(" not in text:
            errors.append(f"Missing UE-style function MF_{prop}")
        if fn.get("targets") and fn.get("status") == "generated":
            for target in fn.get("targets", []):
                if target not in text:
                    errors.append(f"Generated slices do not mention target {target}")
        for c in fn.get("cbuffer_placeholders", []):
            if not c.get("file"):
                errors.append(f"{prop} cbuffer placeholder {c.get('name')} missing source file")
            if c.get("value") is None:
                warnings.append(f"{prop} cbuffer placeholder {c.get('name')} has no decoded static value")
            if c.get("name") not in text:
                errors.append(f"{prop} cbuffer placeholder {c.get('name')} missing from HLSL")
        for sb in fn.get("structured_buffer_placeholders", []):
            if not sb.get("file"):
                errors.append(f"{prop} structured buffer placeholder {sb.get('name')} missing source file")
            if sb.get("name") not in text:
                errors.append(f"{prop} structured buffer placeholder {sb.get('name')} missing from HLSL")
            if not sb.get("index_origin"):
                errors.append(f"{prop} structured buffer placeholder {sb.get('name')} missing index origin")
            if not sb.get("symbolic_index_expr"):
                errors.append(f"{prop} structured buffer placeholder {sb.get('name')} missing symbolic index expression")
            if sb.get("static_index") is not None and sb.get("value") is None:
                warnings.append(f"{prop} structured buffer placeholder {sb.get('name')} has static index but no value")
    result = {"eid": eid, "status": "passed" if not errors else "failed", "errors": errors, "warnings": warnings, "summary": str(path), "hlsl": str(hlsl_path)}
    out = TEST_DIR / f"validate_material_slices_eid_{eid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    settings = app_config.with_env_overrides(app_config.load_settings())
    parser = argparse.ArgumentParser()
    parser.add_argument("--eid", type=int, default=settings.eid)
    parser.add_argument("--out", type=Path, default=Path(settings.out))
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = validate(args.eid, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
