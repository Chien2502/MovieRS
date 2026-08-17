"""
registry.py — Model registry đơn giản (metadata JSON cho từng version + bản deploy hiện tại)

Cấu trúc file:
  - models/model_v_{ts}.json      : metadata của một phiên bản model đã huấn luyện
  - models/model_latest.json      : metadata của model đang được serve bởi API

Sử dụng:
  from src.pipeline.registry import write_metadata, read_metadata, latest_metadata_path
"""

import json
from datetime import datetime
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"


def metadata_path(version_file: Path) -> Path:
    """models/model_v_ts.pkl -> models/model_v_ts.json"""
    return version_file.with_suffix(".json")


def latest_metadata_path() -> Path:
    return MODEL_DIR / "model_latest.json"


def _to_jsonable(obj):
    """Chuẩn hóa dữ liệu về kiểu Python thuần (tránh numpy scalar không serialize được)."""
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if hasattr(obj, "item"):  # numpy scalars (float64, bool_, ...)
        return obj.item()
    return obj


def write_metadata(
    version_file: Path,
    metrics: dict,
    params: dict,
    promoted: bool,
    prev_version: str | None = None,
    train_rows: int | None = None,
    save_path: Path | None = None,
) -> Path:
    """Ghi metadata cho một phiên bản model (mặc định cạnh file .pkl)."""
    meta = {
        "version": version_file.stem,
        "model_file": version_file.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "metrics": _to_jsonable(metrics or {}),
        "params": _to_jsonable(params or {}),
        "train_rows": train_rows,
        "promoted": bool(promoted),
        "prev_version": prev_version,
    }
    path = save_path or metadata_path(version_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_metadata(path: Path) -> dict | None:
    """Đọc metadata JSON; trả về None nếu không tồn tại hoặc lỗi parse."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def list_versions() -> list[dict]:
    """Liệt kê metadata của tất cả các phiên bản model (sắp theo tên giảm dần)."""
    versions = []
    for meta_file in sorted(MODEL_DIR.glob("model_v_*.json"), reverse=True):
        meta = read_metadata(meta_file)
        if meta:
            versions.append(meta)
    return versions
