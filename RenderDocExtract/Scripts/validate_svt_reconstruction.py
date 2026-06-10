#!/usr/bin/env python3
"""Validate SVT reconstruction outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import app_config
from dds_utils import read_dds_header

PROJECT_ROOT = app_config.PROJECT_ROOT
OUTPUT_ROOT = app_config.OUTPUT_ROOT
TEST_DIR = app_config.TEST_DIR
SCRIPT_NAME = Path(__file__).stem


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate(args: argparse.Namespace) -> Dict[str, Any]:
    out_root = args.out
    recon_path = out_root / "draws" / f"eid_{args.eid}" / "svt_reconstruction" / "svt_reconstruction.json"
    errors: List[str] = []
    warnings: List[str] = []
    if not recon_path.exists():
        errors.append(f"Missing reconstruction JSON: {recon_path}")
        result = {"eid": args.eid, "status": "failed", "errors": errors, "warnings": warnings}
        return result
    data = read_json(recon_path)
    for name, info in data.get("physical_textures", {}).items():
        stats = info.get("stats", {})
        output_file = Path(stats.get("output_file", ""))
        if not output_file.exists():
            errors.append(f"Missing reconstructed DDS for {name}: {output_file}")
            continue
        try:
            header = read_dds_header(output_file)
            if [int(header["width"]), int(header["height"])] != stats.get("output_size"):
                errors.append(f"DDS size mismatch for {name}: header={header['width']}x{header['height']} stats={stats.get('output_size')}")
        except Exception as exc:
            errors.append(f"Cannot read reconstructed DDS header for {name}: {exc}")
        if stats.get("copied_pages", 0) <= 0:
            errors.append(f"No pages copied for {name}")
        if stats.get("out_of_range_pages", 0) > 0:
            warnings.append(f"{name} has out_of_range_pages={stats.get('out_of_range_pages')}")
        lib_item = info.get("library_item", {})
        if not lib_item.get("id") or not lib_item.get("file"):
            errors.append(f"Missing texture library registration for {name}")
    repl = Path(data.get("replacement_hlsl", ""))
    if not repl.exists():
        errors.append(f"Missing replacement HLSL: {repl}")
    else:
        text = repl.read_text(encoding="utf-8", errors="ignore")
        if "RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT" not in text:
            errors.append("Replacement HLSL missing macro RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT")
    result = {
        "eid": args.eid,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "reconstruction_json": str(recon_path),
        "replacement_hlsl": str(repl),
    }
    test_path = TEST_DIR / f"validate_svt_reconstruction_eid_{args.eid}.json"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    settings = app_config.with_env_overrides(app_config.load_settings())
    p = argparse.ArgumentParser(prog=SCRIPT_NAME)
    p.add_argument("--eid", type=int, default=settings.eid)
    p.add_argument("--out", type=Path, default=Path(settings.out))
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    result = validate(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
