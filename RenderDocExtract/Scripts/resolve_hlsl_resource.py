#!/usr/bin/env python3
"""Resolve a decompiled HLSL resource name (_8, _12, etc.) to manifest/library files."""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

PROJECT_ROOT = Path("D:/UGit/renderdoc/RenderDocExtract")
OUTPUT_ROOT = PROJECT_ROOT / "Output"
RESOURCE_RE = re.compile(r"^\s*(?P<type>(?:RW)?Buffer<[^>]+>|(?:RW)?Texture\w*<[^>]+>|Sampler\w+)\s+(?P<name>_\d+)\s*:\s*register\((?P<class>[tubs])(?P<slot>\d+)(?:,\s*space(?P<space>\d+))?\)\s*;", re.MULTILINE)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_resources_from_slices(eid: int, out_root: Path) -> Dict[str, Dict[str, Any]]:
    js = out_root / "draws" / f"eid_{eid}" / "material_slices.json"
    if js.exists():
        return read_json(js).get("resource_declarations", {}).get("resources", {})
    hlsl = out_root / "draws" / f"eid_{eid}" / "material_slices.hlsl"
    text = hlsl.read_text(encoding="utf-8", errors="ignore")
    return {m.group("name"): {"type": m.group("type"), "register_class": m.group("class"), "slot": int(m.group("slot")), "space": int(m.group("space") or 0), "declaration": m.group(0).strip()} for m in RESOURCE_RE.finditer(text)}


def resolve(eid: int, name: str, out_root: Path) -> Dict[str, Any]:
    resources = parse_resources_from_slices(eid, out_root)
    decl = resources.get(name)
    if not decl:
        raise KeyError(f"Resource {name} not found in material_slices for EID {eid}")
    manifest = read_json(out_root / "draws" / f"eid_{eid}" / "draw_manifest.json")
    slot = int(decl.get("slot"))
    reg_class = decl.get("register_class")
    result = {"eid": eid, "hlsl_name": name, "declaration": decl, "matches": []}
    if reg_class == "t":
        for t in manifest.get("resources", {}).get("textures", {}).get("textures", []):
            if t.get("stage") == "PS" and int(t.get("access", {}).get("index", -1)) == slot:
                result["matches"].append({"kind": "texture", "stage": "PS", "shader_resource_name": t.get("shaderResourceName"), "resource_id": t.get("texture", {}).get("resourceId"), "library_id": t.get("library_id"), "library_file": t.get("library_file"), "absolute_path": str(out_root / "libraries" / "textures" / t.get("library_file")), "format": t.get("texture", {}).get("format")})
        for b in manifest.get("resources", {}).get("buffers", {}).get("buffers", []):
            if b.get("stage") == "PS" and b.get("category") == "read_only_buffer" and int(b.get("access", {}).get("index", -1)) == slot:
                result["matches"].append({"kind": "read_only_buffer", "stage": "PS", "shader_resource_name": (b.get("shader_resource") or {}).get("name"), "resource_id": b.get("descriptor", {}).get("resourceId"), "library_id": b.get("library_id"), "library_file": b.get("library_file"), "absolute_path": str(out_root / "libraries" / "buffers" / b.get("library_file")), "byte_size": b.get("descriptor", {}).get("byteSize"), "element_byte_size": b.get("descriptor", {}).get("elementByteSize")})
    elif reg_class == "u":
        for b in manifest.get("resources", {}).get("buffers", {}).get("buffers", []):
            if b.get("stage") == "PS" and b.get("category") == "read_write_buffer" and int(b.get("access", {}).get("index", -1)) == slot:
                result["matches"].append({"kind": "read_write_buffer", "stage": "PS", "shader_resource_name": (b.get("shader_resource") or {}).get("name"), "resource_id": b.get("descriptor", {}).get("resourceId"), "library_id": b.get("library_id"), "library_file": b.get("library_file"), "absolute_path": str(out_root / "libraries" / "buffers" / b.get("library_file"))})
    elif reg_class == "s":
        result["matches"].append({"kind": "sampler", "stage": "PS", "slot": slot, "note": "sampler state is embedded in texture binding records when available"})
    elif reg_class == "b":
        for b in manifest.get("resources", {}).get("buffers", {}).get("buffers", []):
            if b.get("stage") == "PS" and b.get("category") == "constant_buffer" and int(b.get("access", {}).get("index", -1)) == slot:
                result["matches"].append({"kind": "constant_buffer", "stage": "PS", "name": (b.get("constant_block") or {}).get("name"), "resource_id": b.get("descriptor", {}).get("resourceId"), "library_id": b.get("library_id"), "library_file": b.get("library_file"), "decoded_variables_file": b.get("decoded_variables_file"), "absolute_path": str(out_root / "libraries" / "buffers" / b.get("library_file"))})
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--eid", type=int, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--out", type=Path, default=OUTPUT_ROOT)
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    print(json.dumps(resolve(args.eid, args.name, args.out), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
