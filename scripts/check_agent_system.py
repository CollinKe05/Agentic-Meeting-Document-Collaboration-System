from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    ok = True
    print("== Python ==")
    print(sys.executable)
    print(sys.version.split()[0])

    ok = _check_imports() and ok
    ok = _check_ocr_paths() and ok
    ok = _check_asr_paths() and ok
    ok = _check_agent_imports() and ok
    return 0 if ok else 1


def _check_imports() -> bool:
    print("\n== Python deps ==")
    modules = [
        ("numpy", "numpy"),
        ("cv2", "opencv-python"),
        ("onnxruntime", "onnxruntime"),
        ("fitz", "PyMuPDF"),
        ("PIL", "Pillow"),
        ("pyclipper", "pyclipper"),
        ("shapely", "shapely"),
        ("sounddevice", "sounddevice"),
        ("soundfile", "soundfile"),
        ("sherpa_onnx", "sherpa-onnx"),
        ("Crypto", "pycryptodome"),
    ]
    ok = True
    for module, package in modules:
        try:
            imported = importlib.import_module(module)
            version = getattr(imported, "__version__", "")
            print(f"OK {module}" + (f" {version}" if version else ""))
        except Exception as exc:  # noqa: BLE001 - diagnostic script
            ok = False
            print(f"FAIL {module} ({package}): {type(exc).__name__}: {exc}")
    return ok


def _check_ocr_paths() -> bool:
    print("\n== OCR / SYSS ==")
    ok = True
    try:
        from sys_core.syss.config import SystemConfig

        cfg = SystemConfig()
        checks = [
            ("yolo", cfg.yolo_model, True),
            ("ppocr dir", cfg.ocr_model_dir, False),
            ("dict", cfg.char_dict, True),
            ("bpu det", cfg.bpu_det_model, True),
            ("bpu rec", cfg.bpu_rec_model, True),
        ]
        for label, value, is_file in checks:
            path = Path(value) if value else Path("")
            exists = path.is_file() if is_file else path.is_dir()
            if exists:
                print(f"OK {label}: {path}")
            else:
                ok = False
                print(f"FAIL {label}: {value or '<empty>'}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"FAIL sys_core.syss.config: {type(exc).__name__}: {exc}")

    try:
        from agent_edge.ocr_pc_tool import _resolve_ocr_backend

        print(f"OK default OCR backend: {_resolve_ocr_backend({})}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"FAIL OCR backend resolution: {type(exc).__name__}: {exc}")
    return ok


def _check_asr_paths() -> bool:
    print("\n== ASR ==")
    ok = True
    asr_dir = Path(os.environ.get("SHERPA_ASR_DIR", PROJECT_ROOT / "sherpa_asr")).expanduser()
    checks = [
        ("asr dir", asr_dir, False),
        ("mic_asr.py", asr_dir / "mic_asr.py", True),
        ("sensevoice model", asr_dir / "models" / "sensevoice" / "model.int8.onnx", True),
        ("sensevoice tokens", asr_dir / "models" / "sensevoice" / "tokens.txt", True),
    ]
    for label, path, is_file in checks:
        exists = path.is_file() if is_file else path.is_dir()
        if exists:
            print(f"OK {label}: {path}")
        else:
            ok = False
            print(f"FAIL {label}: {path}")
    return ok


def _check_agent_imports() -> bool:
    print("\n== Agent imports ==")
    ok = True
    for module in ("agent_edge.web_app", "agent_edge.local_actions", "agent_edge.syss_ocr_runner", "sys_core.syss.pipeline"):
        try:
            importlib.import_module(module)
            print(f"OK {module}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"FAIL {module}: {type(exc).__name__}: {exc}")
    return ok


if __name__ == "__main__":
    raise SystemExit(main())
