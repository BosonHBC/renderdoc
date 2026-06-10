#!/usr/bin/env python3
"""Persistent application settings for RenderDocExtract.

This module is intentionally conservative Python so it can also be imported from
qrenderdoc's embedded Python runtime.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "Config"
OUTPUT_ROOT = PROJECT_ROOT / "Output"
LOG_DIR = PROJECT_ROOT / "Logs"
TEST_DIR = PROJECT_ROOT / "Tests"
DEFAULT_SETTINGS_PATH = CONFIG_DIR / "app_settings.json"

FALLBACK_RDC = Path("D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc")
FALLBACK_QRENDERDOC = Path("D:/UGit/renderdoc/x64/Release/qrenderdoc.exe")
FALLBACK_RENDERDOC = Path("D:/UGit/renderdoc/x64/Release/renderdoc.exe")
FALLBACK_DECOMPILER = Path("D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/tools/hlsl_decompiler/HLSLDecompiler.exe")
FALLBACK_GBUFFER_LAYOUTS = CONFIG_DIR / "gbuffer_layouts.json"
FALLBACK_EID = 7643


DEFAULTS = {
    "rdc": str(FALLBACK_RDC),
    "eid": FALLBACK_EID,
    "out": str(OUTPUT_ROOT),
    "qrenderdoc": str(FALLBACK_QRENDERDOC),
    "renderdoc": str(FALLBACK_RENDERDOC),
    "decompiler": str(FALLBACK_DECOMPILER),
    "gbuffer_layouts": str(FALLBACK_GBUFFER_LAYOUTS),
    "step_timeout": 300,
    "no_log": False,
    "mesh_unit": "cm",
    "mesh_max_indices": 200000,
    "mesh_json_vertex_limit": 256,
    "texture_lib": "",
    "textures_only_used": True,
    "primitive_sample_count": 64,
    "renderdoc_module_dirs": [],
    # SVT reconstruction
    "run_svt_reconstruction": True,
    "svt_tile_size": 128,
    "svt_border": 4,
    "svt_tile_pitch": 136,
}


class AppSettings(object):
    def __init__(self, **kwargs: Any) -> None:
        data = dict(DEFAULTS)
        data.update(kwargs)
        data = coerce_settings_dict(data)
        for key, value in data.items():
            setattr(self, key, value)

    def to_dict(self) -> Dict[str, Any]:
        return {key: getattr(self, key) for key in DEFAULTS.keys()}


SETTING_KEYS = set(DEFAULTS.keys())


def coerce_settings_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    base = dict(DEFAULTS)
    for key, value in data.items():
        if key in base:
            base[key] = value
    base["eid"] = safe_int(base.get("eid"), FALLBACK_EID)
    base["step_timeout"] = safe_int(base.get("step_timeout"), 300)
    base["mesh_max_indices"] = safe_int(base.get("mesh_max_indices"), 200000)
    base["mesh_json_vertex_limit"] = safe_int(base.get("mesh_json_vertex_limit"), 256)
    base["primitive_sample_count"] = safe_int(base.get("primitive_sample_count"), 64)
    base["no_log"] = safe_bool(base.get("no_log"), False)
    base["textures_only_used"] = safe_bool(base.get("textures_only_used"), True)
    base["run_svt_reconstruction"] = safe_bool(base.get("run_svt_reconstruction"), True)
    base["svt_tile_size"] = safe_int(base.get("svt_tile_size"), 128)
    base["svt_border"] = safe_int(base.get("svt_border"), 4)
    base["svt_tile_pitch"] = safe_int(base.get("svt_tile_pitch"), 136)
    if base.get("mesh_unit") not in ("cm", "m"):
        base["mesh_unit"] = "cm"
    dirs = base.get("renderdoc_module_dirs") or []
    if isinstance(dirs, str):
        dirs = split_path_list(dirs)
    base["renderdoc_module_dirs"] = [str(p) for p in dirs if str(p)]
    return base


def _coerce_settings(data: Dict[str, Any]) -> AppSettings:
    return AppSettings(**coerce_settings_dict(data))


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> AppSettings:
    if not path.exists():
        return AppSettings()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return AppSettings()
        return _coerce_settings(data)
    except Exception:
        return AppSettings()


def save_settings(settings: Any, path: Path = DEFAULT_SETTINGS_PATH) -> None:
    if isinstance(settings, AppSettings):
        data = settings.to_dict()
    elif isinstance(settings, dict):
        data = _coerce_settings(settings).to_dict()
    else:
        data = AppSettings().to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def ensure_settings(path: Path = DEFAULT_SETTINGS_PATH) -> AppSettings:
    settings = load_settings(path)
    if not path.exists():
        save_settings(settings, path)
    return settings


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on", "y"):
        return True
    if text in ("0", "false", "no", "off", "n"):
        return False
    return default


def env_int(name: str, default: int) -> int:
    return safe_int(os.environ.get(name), default)


def env_bool(name: str, default: bool = False) -> bool:
    return safe_bool(os.environ.get(name), default)


def env_path(name: str, default: Any) -> Path:
    return Path(os.environ.get(name, str(default)))


def split_path_list(value: str) -> List[str]:
    if not value:
        return []
    normalized = value.replace(";", os.pathsep)
    parts = []
    for chunk in normalized.split(os.pathsep):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


def join_path_list(values: Iterable[str]) -> str:
    return ";".join(str(v) for v in values if str(v))


def with_env_overrides(settings: Optional[AppSettings] = None) -> AppSettings:
    s = settings or load_settings()
    data = s.to_dict()
    mapping = {
        "RENDERDOC_EXTRACT_RDC": "rdc",
        "RENDERDOC_EXTRACT_EID": "eid",
        "RENDERDOC_EXTRACT_OUT": "out",
        "RENDERDOC_EXTRACT_QRENDERDOC": "qrenderdoc",
        "RENDERDOC_EXTRACT_RENDERDOC": "renderdoc",
        "RENDERDOC_EXTRACT_DECOMPILER": "decompiler",
        "RENDERDOC_EXTRACT_GBUFFER_LAYOUTS": "gbuffer_layouts",
        "RENDERDOC_EXTRACT_MESH_UNIT": "mesh_unit",
        "RENDERDOC_EXTRACT_MESH_MAX_INDICES": "mesh_max_indices",
        "RENDERDOC_EXTRACT_JSON_VERTEX_LIMIT": "mesh_json_vertex_limit",
        "RENDERDOC_EXTRACT_TEXTURE_LIB": "texture_lib",
        "RENDERDOC_EXTRACT_TEXTURES_ONLY_USED": "textures_only_used",
        "RENDERDOC_EXTRACT_PRIMITIVE_SAMPLE_COUNT": "primitive_sample_count",
    }
    for env_name, key in mapping.items():
        if env_name in os.environ:
            data[key] = os.environ[env_name]
    if "RENDERDOC_PYTHON_MODULE_DIR" in os.environ:
        data["renderdoc_module_dirs"] = split_path_list(os.environ["RENDERDOC_PYTHON_MODULE_DIR"])
    if "RENDERDOC_EXTRACT_NO_LOG" in os.environ:
        data["no_log"] = os.environ["RENDERDOC_EXTRACT_NO_LOG"]
    return _coerce_settings(data)


if __name__ == "__main__":
    settings = ensure_settings()
    print(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
