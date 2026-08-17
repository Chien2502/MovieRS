"""
download_movielens.py — Tải và giải nén bộ dữ liệu MovieLens

Hỗ trợ:
  - ml-latest-small (~100K ratings, ~600 users, ~9K movies)
  - ml-25m (~25M ratings, ~162K users, ~62K movies)

Sử dụng:
  python src/data/download_movielens.py          # Tải ml-latest-small (mặc định)
  python src/data/download_movielens.py --size 25m  # Tải ml-25m
"""

import os
import sys
import zipfile
import shutil
from pathlib import Path

# Thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import requests
except ImportError:
    print("Cần cài đặt thư viện requests: pip install requests")
    sys.exit(1)


# ============================================================
# Cấu hình URL và thư mục đích
# ============================================================
MOVIELENS_URLS = {
    "small": "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip",
    "25m": "https://files.grouplens.org/datasets/movielens/ml-25m.zip",
}

RAW_DIR = PROJECT_ROOT / "data" / "raw"


def download_file(url: str, dest: Path) -> Path:
    """Tải file từ URL về thư mục đích, hiển thị tiến trình."""
    dest.mkdir(parents=True, exist_ok=True)
    filename = url.split("/")[-1]
    filepath = dest / filename

    if filepath.exists():
        print(f"[✓] File đã tồn tại: {filepath}")
        return filepath

    print(f"[↓] Đang tải: {url}")
    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    downloaded = 0

    with open(filepath, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                pct = (downloaded / total_size) * 100
                mb_done = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r    {mb_done:.1f}/{mb_total:.1f} MB ({pct:.1f}%)", end="", flush=True)

    print(f"\n[✓] Tải xong: {filepath}")
    return filepath


def extract_zip(zip_path: Path, dest: Path) -> Path:
    """Giải nén file ZIP và trả về thư mục chứa dữ liệu."""
    print(f"[📦] Đang giải nén: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)

    # MovieLens ZIP thường chứa 1 thư mục con (vd: ml-latest-small/)
    # Di chuyển các file CSV ra thư mục raw/
    extracted_dirs = [d for d in dest.iterdir() if d.is_dir()]
    if extracted_dirs:
        inner_dir = extracted_dirs[0]
        for f in inner_dir.glob("*.csv"):
            target = dest / f.name
            if not target.exists():
                shutil.move(str(f), str(target))
                print(f"    → {f.name}")
        # Giữ lại thư mục gốc để tham khảo README
        print(f"[✓] Giải nén xong. Các file CSV nằm tại: {dest}")

    return dest


def verify_dataset(raw_dir: Path) -> bool:
    """Kiểm tra các file CSV cần thiết đã tồn tại."""
    required_files = ["ratings.csv", "movies.csv", "links.csv", "tags.csv"]
    missing = [f for f in required_files if not (raw_dir / f).exists()]

    if missing:
        print(f"[✗] Thiếu file: {', '.join(missing)}")
        return False

    # In thống kê nhanh
    for f in required_files:
        filepath = raw_dir / f
        line_count = sum(1 for _ in open(filepath, encoding="utf-8")) - 1  # Trừ header
        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"    {f}: {line_count:,} dòng ({size_mb:.1f} MB)")

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Tải bộ dữ liệu MovieLens")
    parser.add_argument(
        "--size",
        choices=["small", "25m"],
        default="small",
        help="Kích thước dataset: 'small' (ml-latest-small) hoặc '25m' (ml-25m). Mặc định: small",
    )
    args = parser.parse_args()

    url = MOVIELENS_URLS[args.size]
    print(f"{'='*60}")
    print(f"  MovieRS — Tải dữ liệu MovieLens ({args.size})")
    print(f"{'='*60}")

    # Bước 1: Tải ZIP
    zip_path = download_file(url, RAW_DIR)

    # Bước 2: Giải nén
    extract_zip(zip_path, RAW_DIR)

    # Bước 3: Xác minh
    print(f"\n{'─'*40}")
    print("Xác minh dữ liệu:")
    if verify_dataset(RAW_DIR):
        print(f"\n[✓] Dataset sẵn sàng tại: {RAW_DIR}")
        print(f"    Bước tiếp theo: python src/data/fetch_tmdb.py")
    else:
        print(f"\n[✗] Có lỗi! Hãy thử tải lại.")
        sys.exit(1)


if __name__ == "__main__":
    main()
