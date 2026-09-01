"""
item_similarity.py — Chỉ mục tương tự giữa các phim (Item-Item Similarity Index)

Mục đích: phục vụ Candidate Retrieval cho khuyến nghị tức thì.

Hai nguồn tương tự:
  1. Latent similarity (warm items): cosine giữa các vector latent q_i của SVD —
     chỉ áp dụng cho phim có trong trainset (~44K phim sau stratified sampling).
  2. Genre similarity (cold items): cosine giữa binary vector thể loại —
     dùng cho phim ngoài trainset (không có latent vector), giúp "bắc cầu"
     từ phim lạ về các phim warm cùng thể loại.

Đầu ra được lưu dạng numpy (.npz) để load nhanh, không phải pickle dict:
  - train_item_ids:      (n_warm,)        int32 — movieId theo thứ tự hàng
  - latent_top_mids:     (n_warm, top_k)  int32 — movieId tương tự nhất (latent)
  - latent_top_scores:   (n_warm, top_k)  float32
  - cold_item_ids:       (n_cold,)        int32
  - genre_top_mids:      (n_cold, top_k)  int32 — movieId warm tương tự nhất (genre)
  - genre_top_scores:    (n_cold, top_k)  float32

Sử dụng:
  python src/models/item_similarity.py --top-k 200
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models.svd_surprise import SurpriseSVDRecommender

MODEL_PATH = PROJECT_ROOT / "models" / "model_latest.pkl"
MOVIES_CSV = PROJECT_ROOT / "data" / "processed" / "movies_processed.csv"
OUTPUT_NPZ = PROJECT_ROOT / "data" / "processed" / "item_sim.npz"


def _normalize_rows(mat: np.ndarray) -> np.ndarray:
    """Chuẩn hóa từng hàng về unit vector (hàng zero giữ nguyên 0)."""
    mat = np.asarray(mat, dtype=np.float64)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def _build_genre_vectors(movies_df: pd.DataFrame) -> tuple[list[int], np.ndarray]:
    """Xây binary vector thể loại cho toàn catalog.

    Trả về (movie_ids, genre_matrix) với genre_matrix shape (n_movies, n_genres).
    """
    all_genres: set[str] = set()
    genre_lists: list[list[str]] = []
    for genres_raw in movies_df["genres"].fillna(""):
        tokens = [g.strip().lower() for g in str(genres_raw).split(",") if g.strip()]
        genre_lists.append(tokens)
        all_genres.update(tokens)

    genre_names = sorted(all_genres)
    genre_idx = {g: i for i, g in enumerate(genre_names)}
    matrix = np.zeros((len(movies_df), len(genre_names)), dtype=np.float32)
    for row, tokens in enumerate(genre_lists):
        for t in tokens:
            matrix[row, genre_idx[t]] = 1.0

    return movies_df["movieId"].astype(int).tolist(), matrix


def build_index(model, movies_df: pd.DataFrame, top_k: int = 200) -> dict:
    """Tính item-item similarity từ model SVD + catalog, trả về dict các mảng numpy."""
    trainset = model.model.trainset
    n_warm = len(trainset.all_items())
    qi = np.asarray(model.model.qi, dtype=np.float64)  # (n_warm, n_factors)
    qi_norm = _normalize_rows(qi)

    # Map inner_iid -> raw movieId
    train_item_ids = np.array(
        [trainset.to_raw_iid(iid) for iid in range(n_warm)], dtype=np.int32
    )
    train_id_to_row = {int(mid): i for i, mid in enumerate(train_item_ids)}

    # Catalog (thứ tự giữ nguyên như movies_processed.csv)
    catalog_ids, genre_mat = _build_genre_vectors(movies_df)
    genre_norm = _normalize_rows(genre_mat.astype(np.float64))
    catalog_row = {int(mid): i for i, mid in enumerate(catalog_ids)}

    cold_ids = [mid for mid in catalog_ids if mid not in train_id_to_row]
    print(f"[ItemSim] Warm items (latent): {len(train_item_ids):,}")
    print(f"[ItemSim] Cold items (genre) : {len(cold_ids):,}")

    top_k = min(top_k, n_warm)

    # ---------- 1. Latent similarity (warm x warm), tính theo chunk để tiết kiệm RAM ----------
    print("[ItemSim] Tính latent cosine similarity (chunked)...")
    start = time.time()
    latent_top_mids = np.zeros((n_warm, top_k), dtype=np.int32)
    latent_top_scores = np.zeros((n_warm, top_k), dtype=np.float32)

    CHUNK = 1024
    for i in range(0, n_warm, CHUNK):
        end = min(i + CHUNK, n_warm)
        # (chunk, n_factors) @ (n_factors, n_warm) -> (chunk, n_warm)
        sim = qi_norm[i:end] @ qi_norm.T
        # Loại bỏ chính nó: đặt -inf trên đường chéo tương ứng
        for local, global_row in enumerate(range(i, end)):
            sim[local, global_row] = -np.inf
        # Lấy top_k
        idx = np.argpartition(-sim, kth=top_k - 1, axis=1)[:, :top_k]
        scores = np.take_along_axis(sim, idx, axis=1)
        order = np.argsort(-scores, axis=1)
        idx_sorted = np.take_along_axis(idx, order, axis=1)
        scores_sorted = np.take_along_axis(scores, order, axis=1)
        latent_top_mids[i:end] = train_item_ids[idx_sorted]
        latent_top_scores[i:end] = scores_sorted.astype(np.float32)
        if (end // CHUNK) % 5 == 0:
            print(f"    ... {end:,}/{n_warm:,} items ({time.time() - start:.1f}s)")

    print(f"[ItemSim] ✓ Latent similarity xong: {time.time() - start:.1f}s")

    # ---------- 2. Genre similarity (cold x warm) ----------
    print("[ItemSim] Tính genre cosine similarity cho cold items...")
    start = time.time()
    n_cold = len(cold_ids)
    cold_item_ids = np.array(cold_ids, dtype=np.int32)
    genre_top_mids = np.zeros((n_cold, top_k), dtype=np.int32)
    genre_top_scores = np.zeros((n_cold, top_k), dtype=np.float32)

    cold_rows = np.array([catalog_row[mid] for mid in cold_ids])
    warm_rows = np.array(
        [catalog_row[int(mid)] for mid in train_item_ids if int(mid) in catalog_row], dtype=np.int64
    )
    warm_item_ids = np.array(
        [mid for mid in train_item_ids if int(mid) in catalog_row], dtype=np.int32
    )
    cold_genre_norm = genre_norm[cold_rows]  # (n_cold, n_genres)
    warm_genre_norm = genre_norm[warm_rows]  # (n_warm, n_genres)

    for i in range(0, n_cold, CHUNK):
        end = min(i + CHUNK, n_cold)
        sim = cold_genre_norm[i:end] @ warm_genre_norm.T  # (chunk, n_warm)
        idx = np.argpartition(-sim, kth=top_k - 1, axis=1)[:, :top_k]
        scores = np.take_along_axis(sim, idx, axis=1)
        order = np.argsort(-scores, axis=1)
        idx_sorted = np.take_along_axis(idx, order, axis=1)
        scores_sorted = np.take_along_axis(scores, order, axis=1)
        genre_top_mids[i:end] = warm_item_ids[idx_sorted]
        genre_top_scores[i:end] = scores_sorted.astype(np.float32)

    print(f"[ItemSim] ✓ Genre similarity xong: {time.time() - start:.1f}s")

    return {
        "train_item_ids": train_item_ids,
        "latent_top_mids": latent_top_mids,
        "latent_top_scores": latent_top_scores,
        "cold_item_ids": cold_item_ids,
        "genre_top_mids": genre_top_mids,
        "genre_top_scores": genre_top_scores,
    }


def save_index(index: dict, path: Path = OUTPUT_NPZ) -> Path:
    """Lưu index dạng .npz (nén)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        train_item_ids=index["train_item_ids"],
        latent_top_mids=index["latent_top_mids"],
        latent_top_scores=index["latent_top_scores"],
        cold_item_ids=index["cold_item_ids"],
        genre_top_mids=index["genre_top_mids"],
        genre_top_scores=index["genre_top_scores"],
    )
    print(f"[ItemSim] Đã lưu index tại: {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")
    return path


def load_index(path: Path = OUTPUT_NPZ) -> dict | None:
    """Load index từ .npz; trả về None nếu không tồn tại."""
    if not path.exists():
        return None
    with np.load(path, allow_pickle=False) as data:
        return {
            "train_item_ids": data["train_item_ids"].astype(np.int32),
            "latent_top_mids": data["latent_top_mids"].astype(np.int32),
            "latent_top_scores": data["latent_top_scores"].astype(np.float32),
            "cold_item_ids": data["cold_item_ids"].astype(np.int32),
            "genre_top_mids": data["genre_top_mids"].astype(np.int32),
            "genre_top_scores": data["genre_top_scores"].astype(np.float32),
        }


def main():
    parser = argparse.ArgumentParser(description="Precompute Item-Item Similarity Index")
    parser.add_argument("--top-k", type=int, default=200, help="Số phim tương tự lưu cho mỗi phim")
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print("  MovieRS — Precompute Item-Item Similarity Index")
    print(f"{'=' * 60}")

    if not MODEL_PATH.exists():
        print(f"[✗] Không tìm thấy model: {MODEL_PATH}")
        sys.exit(1)
    if not MOVIES_CSV.exists():
        print(f"[✗] Không tìm thấy catalog: {MOVIES_CSV}")
        sys.exit(1)

    print(f"[📥] Đang load model SVD từ {MODEL_PATH}...")
    model = SurpriseSVDRecommender.load(MODEL_PATH)
    movies_df = pd.read_csv(MOVIES_CSV).fillna("")

    index = build_index(model, movies_df, top_k=args.top_k)
    save_index(index)


if __name__ == "__main__":
    main()
