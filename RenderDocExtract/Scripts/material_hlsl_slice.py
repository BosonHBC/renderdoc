#!/usr/bin/env python3
"""Generate property-focused HLSL slices from decompiled PS HLSL and draw manifest.

The slicer maps material properties through the selected GBuffer layout, traces
source-level dependencies from SV_Target components, copies resource declarations,
and replaces cbuffer/structured-buffer references with property-scoped symbolic
constants that include source binding and best-effort decoded values.
"""

import argparse
import json
import re
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import app_config

PROJECT_ROOT = app_config.PROJECT_ROOT
OUTPUT_ROOT = app_config.OUTPUT_ROOT
TEST_DIR = app_config.TEST_DIR
DEFAULT_LAYOUTS = app_config.FALLBACK_GBUFFER_LAYOUTS
MATERIAL_PROPERTIES = ["BaseColor", "Normal", "AO", "Roughness", "Specular", "Metallic", "SubsurfaceColor", "Opacity", "OpacityMask"]
ASSIGN_RE = re.compile(r"^\s*(?:(?P<decl>(?:float|uint|int|bool|float\d|uint\d|int\d)\s+))?(?P<lhs>[A-Za-z_]\w*(?:\.[xyzwrgba])?)\s*=\s*(?P<rhs>.*);\s*$")
IDENT_RE = re.compile(r"\b[A-Za-z_]\w*(?:\.[xyzwrgba])?\b")
CBUF_RE = re.compile(r"(?P<array>_\d+_m0)\[(?P<index>\d+)u?\](?:\.(?P<comp>[xyzwrgba]))?")
LOAD_RE = re.compile(r"(?P<name>_\d+)\.Load\((?P<expr>[^()]*)\)(?:\.(?P<comp>[xyzwrgba]))?")
CBUFFER_RE = re.compile(r"cbuffer\s+(?P<block>\w+)\s*:\s*register\(b(?P<slot>\d+)(?:,\s*space(?P<space>\d+))?\)\s*\{(?P<body>.*?)\};", re.DOTALL)
ARRAY_RE = re.compile(r"float4\s+(?P<array>_\d+_m0)\[(?P<count>\d+)\]")
RESOURCE_RE = re.compile(r"^\s*(?P<type>(?:RW)?Buffer<[^>]+>|(?:RW)?Texture\w*<[^>]+>|Sampler\w+)\s+(?P<name>_\d+)\s*:\s*register\((?P<class>[tubs])(?P<slot>\d+)(?:,\s*space(?P<space>\d+))?\)\s*;", re.MULTILINE)
STATIC_DECL_RE = re.compile(r"^\s*static\s+[^;]+;", re.MULTILINE)
METHOD_NAMES = ("SampleBias", "SampleLevel", "SampleCmpLevelZero", "SampleCmp", "Sample", "Load")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_manifest(eid: int, out_root: Path) -> Dict[str, Any]:
    return read_json(out_root / "draws" / f"eid_{eid}" / "draw_manifest.json")


def ps_hlsl_path(manifest: Dict[str, Any], out_root: Path) -> Path:
    rel = manifest["resources"]["shaders"]["ps"]["item"]["hlsl_file"]
    return out_root / "libraries" / rel


def primitive_id_from_context(eid: int, out_root: Path) -> Optional[int]:
    path = out_root / "draws" / f"eid_{eid}" / "primitive_context.json"
    if not path.exists():
        return None
    try:
        data = read_json(path)
        if data.get("is_constant_in_sample") and data.get("representative_primitive_id") is not None:
            return int(data["representative_primitive_id"])
    except Exception:
        return None
    return None


def selected_layout_id(manifest: Dict[str, Any]) -> str:
    return manifest["resources"]["shaders"]["gbuffer_layout_match"]["selected_layout_id"]


def get_layout(layouts: Dict[str, Any], layout_id: str) -> Dict[str, Any]:
    for layout in layouts.get("layouts", []):
        if layout.get("layout_id") == layout_id:
            return layout
    raise KeyError(layout_id)


def property_targets(layouts: Dict[str, Any], layout_id: str, prop: str) -> List[str]:
    props = layouts.get("material_properties", {})
    info = props.get(prop, {})
    layout = get_layout(layouts, layout_id)
    targets: List[str] = []
    for comp in info.get("components", []):
        semantic = comp.get("semantic")
        channels = comp.get("channels", [])
        for rt in layout.get("render_targets", []):
            if rt.get("semantic") == semantic:
                idx = int(rt.get("index"))
                for ch in channels:
                    comp_letter = {"R": "x", "G": "y", "B": "z", "A": "w"}.get(ch.upper(), ch.lower())
                    targets.append(f"SV_Target_{idx}.{comp_letter}")
    return targets


def parse_assignments(hlsl: str) -> Tuple[List[str], Dict[str, List[Tuple[int, str, str, str]]]]:
    lines = hlsl.splitlines()
    assigns: Dict[str, List[Tuple[int, str, str, str]]] = {}
    for i, line in enumerate(lines, 1):
        m = ASSIGN_RE.match(line)
        if not m:
            continue
        lhs = m.group("lhs")
        rhs = m.group("rhs")
        decl = (m.group("decl") or "").strip()
        rec = (i, line, rhs, decl)
        assigns.setdefault(lhs, []).append(rec)
        if "." in lhs:
            base = lhs.split(".", 1)[0]
            assigns.setdefault(base, []).append(rec)
    return lines, assigns


def latest_assignment(assigns: Dict[str, List[Tuple[int, str, str, str]]], symbol: str) -> Optional[Tuple[int, str, str, str]]:
    records = assigns.get(symbol)
    if not records and "." in symbol:
        records = assigns.get(symbol.split(".", 1)[0])
    return records[-1] if records else None


def identifiers(expr: str) -> Set[str]:
    skip = {"float", "float2", "float3", "float4", "uint", "uint2", "uint3", "uint4", "int", "int2", "int3", "int4", "bool", "true", "false", "min", "max", "saturate", "sqrt", "abs", "asuint", "asfloat", "clamp", "lerp", "dot", "normalize"}
    ids: Set[str] = set()
    for m in IDENT_RE.finditer(expr):
        token = m.group(0)
        base = token.split(".", 1)[0]
        if base in skip or base == "Load":
            continue
        ids.add(token if base.startswith("SV_Target") else base)
    return ids


def dependency_closure(targets: List[str], assigns: Dict[str, List[Tuple[int, str, str, str]]]) -> List[Tuple[int, str]]:
    visited: Set[str] = set()
    kept: Dict[int, str] = {}
    queue = list(targets)
    while queue:
        sym = queue.pop()
        if sym in visited:
            continue
        visited.add(sym)
        records = assigns.get(sym)
        if records is None and "." in sym:
            records = assigns.get(sym.split(".", 1)[0])
        if not records:
            continue
        # Keep every assignment to the same symbol. Decompiled HLSL often emits
        # phi/branch variables such as _476 assigned in both if/else paths; using
        # only the last assignment drops texture indirection chains like _15.Load.
        for line_no, line, rhs, _decl in records:
            kept[line_no] = line
            for dep in identifiers(rhs):
                if dep not in visited:
                    queue.append(dep)
    return sorted(kept.items())


def find_resource_calls(line: str, resources: Dict[str, Dict[str, Any]], texture_only: bool = False) -> List[Dict[str, str]]:
    calls: List[Dict[str, str]] = []
    for name, res in resources.items():
        if texture_only and not str(res.get("type", "")).startswith(("Texture", "RWTexture")):
            continue
        start = 0
        while True:
            pos = line.find(name + ".", start)
            if pos < 0:
                break
            method = None
            method_start = pos + len(name) + 1
            for m in METHOD_NAMES:
                if line.startswith(m + "(", method_start):
                    method = m
                    break
            if method is None:
                start = method_start
                continue
            open_pos = method_start + len(method)
            depth = 0
            end = open_pos
            while end < len(line):
                ch = line[end]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end += 1
                        break
                end += 1
            expr_end = end
            comp = ""
            if expr_end + 1 < len(line) and line[expr_end] == "." and line[expr_end + 1] in "xyzwrgba":
                comp = line[expr_end + 1]
                expr_end += 2
            expr = line[pos:expr_end]
            calls.append({"resource": name, "method": method, "expr": expr, "component": comp, "type": res.get("type", "")})
            start = expr_end
    return calls


def texture_field_type(call: Dict[str, str]) -> str:
    if call.get("component"):
        return "uint" if "uint" in call.get("type", "") else "float"
    m = re.search(r"<([^>]+)>", call.get("type", ""))
    return m.group(1) if m else "float4"


def parse_resource_declarations(hlsl: str) -> Dict[str, Any]:
    cbufs: Dict[str, Dict[str, Any]] = {}
    resources: Dict[str, Dict[str, Any]] = {}
    declaration_lines: List[str] = []
    for m in CBUFFER_RE.finditer(hlsl):
        block = m.group("block")
        slot = int(m.group("slot"))
        body = m.group("body")
        arr = ARRAY_RE.search(body)
        array = arr.group("array") if arr else block
        cbufs[array] = {"block": block, "slot": slot, "space": int(m.group("space") or 0), "array": array, "count": int(arr.group("count")) if arr else None}
        declaration_lines.append(m.group(0))
    for m in RESOURCE_RE.finditer(hlsl):
        resources[m.group("name")] = {"type": m.group("type"), "register_class": m.group("class"), "slot": int(m.group("slot")), "space": int(m.group("space") or 0), "declaration": m.group(0).strip()}
        declaration_lines.append(m.group(0).strip())
    static_decls = [m.group(0).strip() for m in STATIC_DECL_RE.finditer(hlsl)]
    return {"cbuffers": cbufs, "resources": resources, "declaration_lines": declaration_lines, "static_declarations": static_decls}


def ps_cbuffer_bindings(manifest: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for b in manifest.get("resources", {}).get("buffers", {}).get("buffers", []):
        if b.get("stage") == "PS" and b.get("category") == "constant_buffer":
            out[int(b.get("access", {}).get("index", 0))] = b
    return out


def ps_structured_buffer_bindings(manifest: Dict[str, Any]) -> Dict[str, Dict[int, Dict[str, Any]]]:
    out: Dict[str, Dict[int, Dict[str, Any]]] = {"t": {}, "u": {}}
    for b in manifest.get("resources", {}).get("buffers", {}).get("buffers", []):
        if b.get("stage") != "PS":
            continue
        if b.get("category") == "read_only_buffer":
            out["t"][int(b.get("access", {}).get("index", 0))] = b
        elif b.get("category") == "read_write_buffer":
            out["u"][int(b.get("access", {}).get("index", 0))] = b
    return out


def component_offset(comp: Optional[str]) -> Optional[int]:
    if comp is None:
        return None
    return {"x": 0, "r": 0, "y": 4, "g": 4, "z": 8, "b": 8, "w": 12, "a": 12}.get(comp.lower())


def read_float4_from_file(path: Path, offset: int) -> Optional[List[float]]:
    if not path.exists():
        return None
    data = path.read_bytes()
    if offset + 16 > len(data):
        return None
    return list(struct.unpack_from("=4f", data, offset))


def read_scalar_from_file(path: Path, offset: int, comp: Optional[str]) -> Optional[float]:
    vec = read_float4_from_file(path, offset)
    if vec is None:
        return None
    idx = 0 if comp is None else {"x": 0, "r": 0, "y": 1, "g": 1, "z": 2, "b": 2, "w": 3, "a": 3}.get(comp.lower(), 0)
    return vec[idx]


def format_value(v: Any) -> str:
    if v is None:
        return "None"
    if isinstance(v, list):
        return "float4(" + ", ".join(f"{x:.9g}" for x in v) + ")"
    if isinstance(v, float):
        return f"{v:.9g}"
    return str(v)


def make_cbuffer_resolver(prop: str, manifest: Dict[str, Any], resources: Dict[str, Any], out_root: Path):
    mapping: Dict[str, str] = {}
    decls: List[str] = []
    details: List[Dict[str, Any]] = []
    counter = 0
    cbuf_bindings = ps_cbuffer_bindings(manifest)
    cbuf_decls = resources["cbuffers"]

    def repl(m: re.Match) -> str:
        nonlocal counter
        key = m.group(0)
        if key in mapping:
            return mapping[key]
        counter += 1
        array = m.group("array")
        idx = int(m.group("index"))
        comp = m.group("comp")
        name = f"{prop}_Scalar_{counter}"
        mapping[key] = name
        cdecl = cbuf_decls.get(array, {})
        slot = cdecl.get("slot")
        binding = cbuf_bindings.get(slot) if slot is not None else None
        file_rel = binding.get("library_file") if binding else None
        file_path = out_root / "libraries" / "buffers" / file_rel if file_rel else Path("")
        byte_offset = idx * 16
        value = read_scalar_from_file(file_path, byte_offset, comp) if comp else read_float4_from_file(file_path, byte_offset)
        hlsl_type = "float" if comp else "float4"
        decls.append(f"// {name}: source {key}; cbuffer register(b{slot}); file {file_rel}; byte_offset {byte_offset}; value {format_value(value)}\nstatic const {hlsl_type} {name} = {format_value(value) if value is not None else ('0.0f' if comp else 'float4(0,0,0,0)')};")
        details.append({"name": name, "source": key, "kind": "cbuffer", "slot": slot, "file": file_rel, "byte_offset": byte_offset, "component": comp, "value": value})
        return name
    return repl, decls, details


def substitute_index_expr(expr: str, assigns: Dict[str, List[Tuple[int, str, str, str]]], max_depth: int = 6) -> Tuple[str, List[Dict[str, Any]], str]:
    """Best-effort symbolic expansion of a structured buffer Load index expression."""
    expanded = expr.strip()
    deps: List[Dict[str, Any]] = []
    origin_flags = set()
    for _ in range(max_depth):
        changed = False
        for token in sorted({m.group(0) for m in re.finditer(r"\b_\d+\b", expanded)}):
            rec = latest_assignment(assigns, token)
            if not rec:
                continue
            line_no, line, rhs, decl = rec
            deps.append({"symbol": token, "line": line_no, "assignment": line.strip(), "rhs": rhs})
            expanded = re.sub(rf"\b{re.escape(token)}\b", f"({rhs})", expanded)
            changed = True
        if not changed:
            break
    if "PRIMITIVE_ID" in expanded:
        origin_flags.add("PrimitiveID")
    if "gl_PrimitiveID" in expanded:
        origin_flags.add("PrimitiveID")
    if "gl_VertexIndex" in expanded or "SV_VertexID" in expanded:
        origin_flags.add("VertexID")
    if "gl_InstanceIndex" in expanded or "SV_InstanceID" in expanded:
        origin_flags.add("InstanceID")
    return expanded, deps, "+".join(sorted(origin_flags)) if origin_flags else "constant_or_unknown"


def parse_load_index(expr: str, primitive_id: Optional[int] = None) -> Optional[int]:
    text = expr.strip().replace(" ", "")
    text = text.replace("u", "")
    if primitive_id is not None:
        text = text.replace("PRIMITIVE_ID", str(int(primitive_id)))
    if re.fullmatch(r"\d+", text):
        return int(text)
    # Safe subset: constant integer arithmetic after substitution.
    if re.fullmatch(r"[0-9+\-*/()]+", text):
        try:
            return int(eval(text, {"__builtins__": {}}, {}))
        except Exception:
            return None
    return None


def read_buffer_load_value(path: Path, element_size: int, index: int, comp: Optional[str], resource_type: str) -> Any:
    if not path.exists() or index is None:
        return None
    data = path.read_bytes()
    off = index * element_size
    if off + element_size > len(data):
        return None
    # Most extracted structured buffers in this project are uint4/float4 or scalar uint buffers.
    if "uint4" in resource_type and element_size >= 16:
        vals = list(struct.unpack_from("=4I", data, off))
    elif "float4" in resource_type and element_size >= 16:
        vals = list(struct.unpack_from("=4f", data, off))
    elif "uint" in resource_type and element_size >= 4:
        vals = [struct.unpack_from("=I", data, off)[0]]
    elif "float" in resource_type and element_size >= 4:
        vals = [struct.unpack_from("=f", data, off)[0]]
    else:
        vals = list(data[off: off + element_size])
    if comp:
        ci = {"x": 0, "r": 0, "y": 1, "g": 1, "z": 2, "b": 2, "w": 3, "a": 3}.get(comp.lower(), 0)
        return vals[ci] if ci < len(vals) else None
    return vals


def make_load_resolver(prop: str, manifest: Dict[str, Any], resources: Dict[str, Any], out_root: Path, assigns: Dict[str, List[Tuple[int, str, str, str]]], primitive_id: Optional[int]):
    mapping: Dict[str, str] = {}
    decls: List[str] = []
    details: List[Dict[str, Any]] = []
    counter = 0
    buffer_bindings = ps_structured_buffer_bindings(manifest)
    resource_decls = resources["resources"]

    def repl(m: re.Match) -> str:
        nonlocal counter
        key = m.group(0)
        if key in mapping:
            return mapping[key]
        counter += 1
        resource = m.group("name")
        expr = m.group("expr")
        comp = m.group("comp")
        rdecl = resource_decls.get(resource, {})
        if not str(rdecl.get("type", "")).startswith(("Buffer<", "RWBuffer<")):
            return key
        name = f"{prop}_Scalar_sb_{counter}"
        mapping[key] = name
        slot = rdecl.get("slot")
        reg_class = rdecl.get("register_class", "t")
        binding = buffer_bindings.get(reg_class, {}).get(slot) if slot is not None else None
        file_rel = binding.get("library_file") if binding else None
        file_path = out_root / "libraries" / "buffers" / file_rel if file_rel else Path("")
        elem = int((binding or {}).get("descriptor", {}).get("elementByteSize", 16) or 16)
        if str(rdecl.get("type", "")).startswith("Buffer<"):
            elem = 4
        symbolic_expr, index_deps, index_origin = substitute_index_expr(expr, assigns)
        index = parse_load_index(symbolic_expr, primitive_id)
        value = read_buffer_load_value(file_path, elem, index, comp, rdecl.get("type", "")) if index is not None else None
        hlsl_type = "uint" if "uint" in rdecl.get("type", "") and comp else "float" if comp else "float4"
        default = format_value(value) if value is not None else ("0" if hlsl_type == "uint" else "0.0f" if comp else "float4(0,0,0,0)")
        decls.append(f"// {name}: source {key}; {resource} register(t{slot}); file {file_rel}; element_size {elem}; index_expr ({expr}); symbolic_index ({symbolic_expr}); primitive_id {primitive_id}; index_origin {index_origin}; static_index {index}; static_value {format_value(value)}\nstatic const {hlsl_type} {name} = {default};")
        details.append({"name": name, "source": key, "kind": "structured_buffer", "resource": resource, "slot": slot, "file": file_rel, "element_size": elem, "index_expr": expr, "symbolic_index_expr": symbolic_expr, "index_dependencies": index_deps, "index_origin": index_origin, "primitive_id": primitive_id, "static_index": index, "component": comp, "value": value})
        return name
    return repl, decls, details


def return_type_for_targets(targets: List[str]) -> str:
    if len(targets) == 1:
        return "float"
    if len(targets) == 2:
        return "float2"
    if len(targets) == 3:
        return "float3"
    if len(targets) == 4:
        return "float4"
    return "void"


def return_expr_for_targets(targets: List[str]) -> str:
    if len(targets) == 1:
        return targets[0]
    return f"{return_type_for_targets(targets)}(" + ", ".join(targets) + ")"


def replace_texture_calls(line: str, sample_map: Dict[str, Dict[str, Any]]) -> str:
    # Replace longest expressions first to avoid partial replacements.
    for expr, meta in sorted(sample_map.items(), key=lambda kv: len(kv[0]), reverse=True):
        line = line.replace(expr, "samples." + meta["field"])
    return line


def make_function(prop: str, targets: List[str], kept_lines: List[Tuple[int, str]], manifest: Dict[str, Any], resources: Dict[str, Any], out_root: Path, assigns: Dict[str, List[Tuple[int, str, str, str]]], primitive_id: Optional[int], sample_map: Dict[str, Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    if not targets:
        text = f"// Material property: {prop}\n// No GBuffer channel mapped in selected layout.\nvoid frag_main_{prop}()\n{{\n    // empty\n}}\n\n"
        return text, {"property": prop, "status": "no_layout_channel", "targets": []}
    c_repl, c_decls, c_details = make_cbuffer_resolver(prop, manifest, resources, out_root)
    sb_repl, sb_decls, sb_details = make_load_resolver(prop, manifest, resources, out_root, assigns, primitive_id)
    renamed: List[Tuple[int, str]] = []
    for line_no, line in kept_lines:
        new_line = replace_texture_calls(line, sample_map)
        new_line = CBUF_RE.sub(c_repl, new_line)
        new_line = LOAD_RE.sub(sb_repl, new_line)
        renamed.append((line_no, new_line))
    lines = []
    lines.append(f"// Material property: {prop}")
    lines.append(f"// Targets: {', '.join(targets)}")
    lines.extend(c_decls)
    lines.extend(sb_decls)
    ret_type = return_type_for_targets(targets)
    lines.append(f"{ret_type} MF_{prop}(MaterialTextureSamples samples)")
    lines.append("{")
    if renamed:
        for line_no, line in renamed:
            lines.append(f"    // source line {line_no}")
            lines.append("    " + line.strip())
        lines.append(f"    return {return_expr_for_targets(targets)};")
    else:
        lines.append("    // No dependency assignment found in decompiled HLSL for this property.")
        if ret_type != "void":
            lines.append(f"    return ({ret_type})0;")
    lines.append("}")
    lines.append(f"void frag_main_{prop}()")
    lines.append("{")
    if ret_type != "void":
        lines.append("    MaterialTextureSamples samples = SampleMaterialTextures();")
        lines.append(f"    {ret_type} {prop} = MF_{prop}(samples);")
    lines.append("}")
    lines.append("")
    return "\n".join(lines), {"property": prop, "status": "generated" if renamed else "empty", "targets": targets, "source_line_count": len(renamed), "cbuffer_placeholder_count": len(c_details), "structured_buffer_placeholder_count": len(sb_details), "cbuffer_placeholders": c_details, "structured_buffer_placeholders": sb_details}


def collect_texture_samples(prop_kept: Dict[str, List[Tuple[int, str]]], resources: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    sample_map: Dict[str, Dict[str, Any]] = {}
    counter = 0
    for prop, kept in prop_kept.items():
        for line_no, line in kept:
            for call in find_resource_calls(line, resources["resources"], texture_only=True):
                expr = call["expr"]
                if expr not in sample_map:
                    counter += 1
                    sample_map[expr] = {"field": f"Sample_{counter}", "type": texture_field_type(call), "expr": expr, "resource": call["resource"], "method": call["method"], "properties": [], "source_lines": []}
                if prop not in sample_map[expr]["properties"]:
                    sample_map[expr]["properties"].append(prop)
                sample_map[expr]["source_lines"].append(line_no)
    return sample_map


def make_texture_sample_function(sample_map: Dict[str, Dict[str, Any]], assigns: Dict[str, List[Tuple[int, str, str, str]]], manifest: Dict[str, Any], resources: Dict[str, Any], out_root: Path, primitive_id: Optional[int]) -> Tuple[str, Dict[str, Any]]:
    if not sample_map:
        return "struct MaterialTextureSamples {};\nMaterialTextureSamples SampleMaterialTextures() { MaterialTextureSamples s; return s; }\n", {"sample_count": 0, "samples": []}
    dep_symbols: Set[str] = set()
    for meta in sample_map.values():
        dep_symbols.update(identifiers(meta["expr"]))
    kept = dependency_closure(list(dep_symbols), assigns)
    c_repl, c_decls, c_details = make_cbuffer_resolver("TextureSample", manifest, resources, out_root)
    sb_repl, sb_decls, sb_details = make_load_resolver("TextureSample", manifest, resources, out_root, assigns, primitive_id)
    lines = ["struct MaterialTextureSamples", "{"]
    for meta in sample_map.values():
        lines.append(f"    {meta['type']} {meta['field']}; // {meta['expr']} used by {', '.join(meta['properties'])}")
    lines.append("};\n")
    lines.extend(c_decls)
    lines.extend(sb_decls)
    lines.append("MaterialTextureSamples SampleMaterialTextures()")
    lines.append("{")
    lines.append("    MaterialTextureSamples samples;")
    for line_no, line in kept:
        new_line = CBUF_RE.sub(c_repl, line)
        new_line = LOAD_RE.sub(sb_repl, new_line)
        lines.append(f"    // source line {line_no}")
        lines.append("    " + new_line.strip())
    for expr, meta in sample_map.items():
        expr2 = CBUF_RE.sub(c_repl, expr)
        expr2 = LOAD_RE.sub(sb_repl, expr2)
        lines.append(f"    samples.{meta['field']} = {expr2};")
    lines.append("    return samples;")
    lines.append("}\n")
    return "\n".join(lines), {"sample_count": len(sample_map), "samples": list(sample_map.values()), "cbuffer_placeholders": c_details, "structured_buffer_placeholders": sb_details}


def generate_for_eid(eid: int, out_root: Path, layout_path: Path, output_dir: Optional[Path] = None) -> Dict[str, Any]:
    manifest = load_manifest(eid, out_root)
    layouts = read_json(layout_path)
    layout_id = selected_layout_id(manifest)
    hlsl_path = ps_hlsl_path(manifest, out_root)
    hlsl = hlsl_path.read_text(encoding="utf-8", errors="ignore")
    resources = parse_resource_declarations(hlsl)
    _lines, assigns = parse_assignments(hlsl)
    output_dir = output_dir or (out_root / "draws" / f"eid_{eid}")
    primitive_id = primitive_id_from_context(eid, out_root)
    prop_kept: Dict[str, List[Tuple[int, str]]] = {}
    prop_targets: Dict[str, List[str]] = {}
    for prop in MATERIAL_PROPERTIES:
        targets = property_targets(layouts, layout_id, prop)
        prop_targets[prop] = targets
        prop_kept[prop] = dependency_closure(targets, assigns)
    sample_map = collect_texture_samples(prop_kept, resources)
    sample_text, sample_summary = make_texture_sample_function(sample_map, assigns, manifest, resources, out_root, primitive_id)
    functions = []
    summary = {"eid": eid, "layout_id": layout_id, "primitive_id": primitive_id, "source_hlsl": str(hlsl_path), "functions": [], "texture_samples": sample_summary, "output_hlsl": str(output_dir / "material_slices.hlsl"), "resource_declarations": resources}
    header = ["// Auto-generated material property HLSL slices", f"// EID: {eid}", f"// Layout: {layout_id}", f"// PrimitiveID: {primitive_id}", f"// Source: {hlsl_path}", "", "// ---- Copied resource/static declarations from source HLSL ----"]
    header.extend(resources["declaration_lines"])
    header.extend(resources["static_declarations"])
    header.append("// ---- End copied declarations ----\n")
    for prop in MATERIAL_PROPERTIES:
        targets = prop_targets[prop]
        kept = prop_kept[prop]
        fn_text, fn_summary = make_function(prop, targets, kept, manifest, resources, out_root, assigns, primitive_id, sample_map)
        functions.append(fn_text)
        summary["functions"].append(fn_summary)
    write_text(output_dir / "material_slices.hlsl", "\n".join(header + [sample_text] + functions))
    write_text(output_dir / "material_slices.json", json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    settings = app_config.with_env_overrides(app_config.load_settings())
    parser = argparse.ArgumentParser(prog="material_hlsl_slice", description="Generate material-property HLSL slices from PS HLSL and GBuffer layout.")
    parser.add_argument("--eid", type=int, default=settings.eid)
    parser.add_argument("--out", type=Path, default=Path(settings.out))
    parser.add_argument("--layouts", type=Path, default=Path(settings.gbuffer_layouts))
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    summary = generate_for_eid(args.eid, args.out, args.layouts, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
