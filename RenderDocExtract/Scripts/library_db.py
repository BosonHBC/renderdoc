#!/usr/bin/env python3
"""JSON asset-library helper for RenderDocExtract.

Provides stable hash helpers, atomic JSON writes, asset registration, and
format-based index allocation shared by texture/shader/mesh/buffer extractors.
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

PROJECT_ROOT = Path("D:/UGit/renderdoc/RenderDocExtract")
LOG_DIR = PROJECT_ROOT / "Logs"
TEST_DIR = PROJECT_ROOT / "Tests"
SCRIPT_NAME = Path(globals().get("__file__", "library_db.py")).stem
DB_VERSION = 1


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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def empty_db(kind: str = "generic") -> Dict[str, Any]:
    return {
        "version": DB_VERSION,
        "kind": kind,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": {},
    }


def ensure_db_shape(db: Dict[str, Any], kind: str = "generic") -> Dict[str, Any]:
    if not isinstance(db, dict):
        raise ValueError("Database root must be a JSON object")
    db.setdefault("version", DB_VERSION)
    db.setdefault("kind", kind)
    db.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    db.setdefault("updated_at", datetime.now().isoformat(timespec="seconds"))
    db.setdefault("items", {})
    if not isinstance(db["items"], dict):
        raise ValueError("Database field 'items' must be an object")
    return db


def load_json_db(path: Path, kind: str = "generic") -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return empty_db(kind)
    with path.open("r", encoding="utf-8") as f:
        db = json.load(f)
    return ensure_db_shape(db, kind)


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp_path.replace(path)


def normalise_format_name(format_name: str) -> str:
    safe = []
    for ch in str(format_name).strip():
        if ch.isalnum() or ch in ("_", "-", "."):
            safe.append(ch)
        elif ch in (" ", "/", "\\", ":"):
            safe.append("_")
    result = "".join(safe).strip("_")
    return result or "UNKNOWN"


def next_index_by_format(db: Dict[str, Any], format_name: str) -> int:
    prefix = normalise_format_name(format_name)
    max_index = 0
    for item in db.get("items", {}).values():
        if not isinstance(item, dict):
            continue
        if normalise_format_name(item.get("format", "")) != prefix:
            continue
        index = item.get("index")
        if isinstance(index, int):
            max_index = max(max_index, index)
    return max_index + 1


def make_asset_key(category: str, digest: str) -> str:
    short = str(digest)[:16]
    return f"{category}_{short}"


def register_asset(
    db_path: Path,
    key: str,
    item: Dict[str, Any],
    kind: str = "generic",
    update_existing: bool = False,
) -> Tuple[Dict[str, Any], bool]:
    """Register an asset item.

    Returns `(registered_item, created)`. By default existing items preserve
    paths and indices for stable asset references; only `seen_count` and
    `last_seen_at` are updated. Pass `update_existing=True` for metadata-rich
    records such as shader reflection where schema can improve over time.
    """

    db = load_json_db(db_path, kind)
    items = db["items"]
    now = datetime.now().isoformat(timespec="seconds")

    if key in items:
        existing = items[key]
        if isinstance(existing, dict):
            previous_seen_count = int(existing.get("seen_count", 1))
            if update_existing:
                preserved = {
                    "id": existing.get("id", key),
                    "created_at": existing.get("created_at", now),
                    "seen_count": previous_seen_count,
                }
                existing.clear()
                existing.update(dict(item))
                existing.update(preserved)
            existing["seen_count"] = previous_seen_count + 1
            existing["last_seen_at"] = now
        atomic_write_json(db_path, db)
        return existing, False

    new_item = dict(item)
    new_item.setdefault("id", key)
    new_item.setdefault("created_at", now)
    new_item.setdefault("last_seen_at", now)
    new_item.setdefault("seen_count", 1)
    items[key] = new_item
    atomic_write_json(db_path, db)
    return new_item, True


def copy_if_new(src: Path, dst: Path) -> bool:
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and sha256_file(src) == sha256_file(dst):
        return False
    shutil.copy2(src, dst)
    return True


def run_self_test(out_dir: Path, logger: logging.Logger) -> Dict[str, Any]:
    start = time.perf_counter()
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Running library_db self-test in %s", out_dir)

    data_a = b"RenderDocExtract asset payload A"
    data_b = b"RenderDocExtract asset payload B"
    file_a = out_dir / "payload_a.bin"
    file_b = out_dir / "payload_b.bin"
    file_a.write_bytes(data_a)
    file_b.write_bytes(data_b)

    hash_a = sha256_bytes(data_a)
    hash_a_file = sha256_file(file_a)
    hash_b = sha256_file(file_b)
    assert hash_a == hash_a_file, "sha256_file must match sha256_bytes"
    assert hash_a != hash_b, "different payloads must produce different hashes"

    db_path = out_dir / "asset_library.json"
    db0 = load_json_db(db_path, "self_test")
    assert db0["items"] == {}, "new DB should start empty"
    assert next_index_by_format(db0, "BC7 UNORM SRGB") == 1

    key_a = make_asset_key("tex", hash_a)
    item_a = {
        "category": "texture",
        "format": "BC7_UNORM_SRGB",
        "index": next_index_by_format(db0, "BC7_UNORM_SRGB"),
        "sha256": hash_a,
        "file": "BC7_UNORM_SRGB_000001.dds",
    }
    registered_a, created_a = register_asset(db_path, key_a, item_a, "self_test")
    assert created_a is True
    assert registered_a["index"] == 1

    registered_dup, created_dup = register_asset(db_path, key_a, dict(item_a), "self_test")
    assert created_dup is False
    assert registered_dup["index"] == 1
    assert registered_dup["seen_count"] == 2

    db1 = load_json_db(db_path, "self_test")
    assert len(db1["items"]) == 1
    assert next_index_by_format(db1, "BC7_UNORM_SRGB") == 2

    key_b = make_asset_key("tex", hash_b)
    item_b = {
        "category": "texture",
        "format": "BC7_UNORM_SRGB",
        "index": next_index_by_format(db1, "BC7_UNORM_SRGB"),
        "sha256": hash_b,
        "file": "BC7_UNORM_SRGB_000002.dds",
    }
    registered_b, created_b = register_asset(db_path, key_b, item_b, "self_test")
    assert created_b is True
    assert registered_b["index"] == 2

    copied_first = copy_if_new(file_a, out_dir / "copy" / "payload_a.bin")
    copied_second = copy_if_new(file_a, out_dir / "copy" / "payload_a.bin")
    assert copied_first is True
    assert copied_second is False

    db2 = load_json_db(db_path, "self_test")
    summary = {
        "script": SCRIPT_NAME,
        "status": "passed",
        "db_path": str(db_path),
        "item_count": len(db2["items"]),
        "hash_a": hash_a,
        "hash_b": hash_b,
        "next_bc7_index": next_index_by_format(db2, "BC7_UNORM_SRGB"),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
    }
    atomic_write_json(out_dir / "self_test_summary.json", summary)
    logger.info("library_db self-test passed: %s", out_dir / "self_test_summary.json")
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    if argv is None and not hasattr(sys, "argv"):
        argv = []
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="JSON asset-library helper for RenderDocExtract.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--self-test", action="store_true", help="Run built-in self-test.")
    parser.add_argument("--out", type=Path, default=TEST_DIR / "library_db_test", help="Self-test output directory.")
    parser.add_argument("--no-log", dest="no_log", action="store_true", help="Disable log file output.")
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
    if log_path:
        logger.info("Log path: %s", log_path)

    start = time.perf_counter()
    try:
        if args.self_test:
            run_self_test(args.out, logger)
        else:
            logger.info("No action requested. Use --self-test or --help.")
        logger.info("Elapsed seconds: %.3f", time.perf_counter() - start)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("library_db failed: %s", exc)
        return 1


if __name__ == "__main__" or "pyrenderdoc" in globals():
    raise SystemExit(main())
