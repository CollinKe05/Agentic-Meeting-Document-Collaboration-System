from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .paths import WORKSPACE_DIR, safe_child_path


CRYPTO_SUFFIXES = {".md", ".markdown", ".txt"}


def crypto_status() -> dict[str, Any]:
    try:
        from syss_f16yolo_sere.utils.crypto_utils import DEFAULT_KEY  # noqa: F401
    except ModuleNotFoundError as exc:
        if exc.name == "Crypto":
            return {
                "ok": False,
                "available": False,
                "error": "Missing pycryptodome. Install with: python -m pip install pycryptodome",
            }
        return {"ok": False, "available": False, "error": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:  # noqa: BLE001 - status boundary
        return {"ok": False, "available": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": True,
        "available": True,
        "has_env_key": bool(os.environ.get("MARKDOWN_ENCRYPT_KEY")),
        "workspace": str(WORKSPACE_DIR),
    }


def encrypt_workspace_file(payload: dict[str, Any]) -> dict[str, Any]:
    path = _resolve_text_path(payload)
    content = path.read_text(encoding="utf-8")
    crypto = _crypto()
    if crypto.is_encrypted(content):
        raise ValueError("File already looks encrypted; refusing to encrypt it again")
    encrypted = crypto.encrypt_text(content, _optional_key(payload))
    output_path = _resolve_output_path(path, payload, suffix=".encrypted.md")
    output_path.write_text(encrypted, encoding="utf-8", newline="\n")
    return _result("encrypt", path, output_path, encrypted=True)


def decrypt_workspace_file(payload: dict[str, Any]) -> dict[str, Any]:
    path = _resolve_text_path(payload)
    content = path.read_text(encoding="utf-8")
    crypto = _crypto()
    if not crypto.is_encrypted(content):
        raise ValueError("File does not look encrypted; refusing to decrypt it")
    plain = crypto.decrypt_text(content.strip(), _optional_key(payload))
    output_path = _resolve_output_path(path, payload, suffix=".decrypted.md")
    output_path.write_text(plain, encoding="utf-8", newline="\n")
    return _result("decrypt", path, output_path, encrypted=False)


def inspect_workspace_file(payload: dict[str, Any]) -> dict[str, Any]:
    path = _resolve_text_path(payload)
    content = path.read_text(encoding="utf-8")
    crypto = _crypto()
    return {
        "ok": True,
        "path": _rel(path),
        "name": path.name,
        "bytes": path.stat().st_size,
        "encrypted": crypto.is_encrypted(content),
    }


def _crypto():
    try:
        from syss_f16yolo_sere.utils import crypto_utils
    except ModuleNotFoundError as exc:
        if exc.name == "Crypto":
            raise RuntimeError("Missing pycryptodome. Install with: python -m pip install pycryptodome") from exc
        raise
    return crypto_utils


def _resolve_text_path(payload: dict[str, Any]) -> Path:
    rel_path = str(payload.get("path", "")).strip()
    path = safe_child_path(WORKSPACE_DIR, rel_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(rel_path)
    if path.suffix.lower() not in CRYPTO_SUFFIXES:
        raise ValueError("Crypto tool only supports Markdown/TXT files")
    return path


def _resolve_output_path(path: Path, payload: dict[str, Any], *, suffix: str) -> Path:
    output = str(payload.get("output_path", "")).strip()
    overwrite = bool(payload.get("overwrite", False))
    if output:
        output_path = safe_child_path(WORKSPACE_DIR, output)
        if output_path.suffix.lower() not in CRYPTO_SUFFIXES:
            raise ValueError("Output must be a Markdown/TXT file")
    else:
        output_path = path.with_name(f"{path.stem}{suffix}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not overwrite:
        output_path = _next_available_path(output_path)
    return output_path


def _next_available_path(path: Path) -> Path:
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not allocate a non-conflicting output filename: {path.name}")


def _optional_key(payload: dict[str, Any]) -> str | None:
    key = payload.get("key")
    if key is None:
        return None
    key = str(key)
    return key or None


def _rel(path: Path) -> str:
    return path.resolve().relative_to(WORKSPACE_DIR.resolve()).as_posix()


def _result(operation: str, source_path: Path, output_path: Path, *, encrypted: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": operation,
        "source_path": _rel(source_path),
        "output_path": _rel(output_path),
        "absolute_output_path": str(output_path),
        "encrypted": encrypted,
        "bytes": output_path.stat().st_size,
    }
