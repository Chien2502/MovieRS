"""
svd_surprise.py — Wrapper sử dụng scikit-surprise để huấn luyện mô hình SVD

Mục đích:
  - Cung cấp mô hình SVD tối ưu hóa cao thông qua thư viện scikit-surprise.
  - Cho phép lưu và tải mô hình thuận tiện (Model Serialization).
  - Tích hợp công cụ tinh chỉnh siêu tham số (Hyperparameter Tuning).
"""

import joblib
from pathlib import Path
import numpy as np
import pandas as pd
from surprise import Dataset, Reader, SVD


class SurpriseSVDRecommender:
    """Mô hình SVD sử dụng thư viện scikit-surprise."""
    supports_rating_prediction = True
    def __init__(self, n_factors=100, lr_all=0.005, reg_all=0.02, n_epochs=20, random_state=42):
        self.n_factors = n_factors
        self.lr_all = lr_all
        self.reg_all = reg_all
        self.n_epochs = n_epochs
        self.random_state = random_state
        
        self.model = SVD(
            n_factors=self.n_factors,
            lr_all=self.lr_all,
            reg_all=self.reg_all,
            n_epochs=self.n_epochs,
            random_state=random_state,
        )
        self.trainset = None
        # Users chưa có trong trainset nhưng đã được cập nhật online:
        # {user_id: (p_u: np.ndarray, b_u: float)} — giúp cá nhân hóa tức thời
        # mà không cần retrain toàn bộ mô hình.
        self.extra_users = {}

    def fit(self, train_df: pd.DataFrame):
        """Huấn luyện mô hình SVD trên tập Train."""
        print(f"[SurpriseSVD] Training SVD (n_factors={self.n_factors}, epochs={self.n_epochs})...")
        
        reader = Reader(rating_scale=(0.5, 5.0))
        data = Dataset.load_from_df(train_df[['userId', 'movieId', 'rating']], reader)
        self.trainset = data.build_full_trainset()
        
        self.model.fit(self.trainset)
        # Model mới → xoá các user đã cập nhật online ở model cũ (bản thân chúng
        # đã được gộp vào train qua merge_interactions nếu tương tác thật)
        self.extra_users = {}
        print("[SurpriseSVD] Training completed.")
        return self

    def predict(self, user_id: int, movie_id: int) -> float:
        """Dự đoán rating cho một cặp user-movie."""
        # User được cập nhật online (chưa có trong trainset) → tính trực tiếp
        # từ latent factors đã lưu trong extra_users
        if user_id in self.extra_users:
            pu, bu = self.extra_users[user_id]
            trainset = self.model.trainset
            try:
                inner_iid = trainset.to_inner_iid(movie_id)
            except ValueError:
                return float(np.clip(trainset.global_mean + bu, 0.5, 5.0))
            return float(np.clip(
                trainset.global_mean + bu + self.model.bi[inner_iid]
                + float(pu @ self.model.qi[inner_iid]), 0.5, 5.0))
        pred = self.model.predict(user_id, movie_id)
        return float(pred.est)

    def online_update(self, user_id: int, movie_id: int, rating: float,
                      lr: float = None, reg: float = None) -> bool:
        """Cập nhật tức thời vector ẩn của MỘT user theo một rating mới (Online Learning).

        Áp dụng đúng 1 bước SGD của FunkSVD (không retrain toàn bộ):
          err = r - (mu + b_u + b_i + p_u^T q_i)
          b_u <- b_u + lr * (err - reg * b_u)
          p_u <- p_u + lr * (err * q_i - reg * p_u)

        - User đã có trong trainset: cập nhật trực tiếp trên ma trận latent của model.
        - User mới (cold-start): lưu vào extra_users — vector p_u khởi tạo 0 (đẳng cấp
          với bản khởi tạo SVD), tích lũy dần qua từng tương tác.
        - Trả về False nếu phim không tồn tại trong mô hình (không cập nhật được).
        """
        lr = lr if lr is not None else self.lr_all
        reg = reg if reg is not None else self.reg_all

        try:
            trainset = self.model.trainset
            inner_iid = trainset.to_inner_iid(movie_id)
            qi = self.model.qi[inner_iid]
            bi = self.model.bi[inner_iid]
            global_mean = trainset.global_mean
        except (ValueError, KeyError, AttributeError):
            return False

        try:
            inner_uid = trainset.to_inner_uid(user_id)
        except (ValueError, KeyError):
            inner_uid = None

        if inner_uid is not None:
            bu = self.model.bu[inner_uid]
            pu = self.model.pu[inner_uid]
            err = rating - (global_mean + bu + bi + float(pu @ qi))
            self.model.bu[inner_uid] = bu + lr * (err - reg * bu)
            self.model.pu[inner_uid] = pu + lr * (err * qi - reg * pu)
        else:
            pu, bu = self.extra_users.get(user_id, (np.zeros(self.n_factors), 0.0))
            err = rating - (global_mean + bu + bi + float(pu @ qi))
            bu = bu + lr * (err - reg * bu)
            pu = pu + lr * (err * qi - reg * pu)
            self.extra_users[user_id] = (pu, bu)
        return True

    def recommend(self, user_id: int, all_movie_ids: list, rated_movie_ids: list = None, n=10) -> list:
        """Gợi ý Top-N phim cho một user cụ thể (loại bỏ những phim đã đánh giá nếu có).

        Ưu tiên fast path vector hóa (tính điểm toàn bộ ứng viên bằng 1 phép toán
        NumPy trên latent factors); fallback về vòng lặp dự đoán từng phim.
        """
        seen = set(rated_movie_ids or [])
        candidates = np.array([mid for mid in all_movie_ids if mid not in seen], dtype=int)
        scores = self.score_items(user_id, candidates)
        order = np.lexsort((candidates, -scores))[:n]
        return [(int(candidates[i]), float(scores[i])) for i in order]

    def score_items(self, user_id: int, movie_ids) -> np.ndarray:
        """Điểm vector hóa khớp predict, kể cả user/phim chưa có trong train."""
        trainset = self.model.trainset
        if user_id in self.extra_users:
            pu, bu = self.extra_users[user_id]
        else:
            try:
                uid = trainset.to_inner_uid(user_id)
                pu, bu = self.model.pu[uid], self.model.bu[uid]
            except ValueError:
                pu, bu = np.zeros(self.model.qi.shape[1]), 0.0
        values = np.full(len(movie_ids), trainset.global_mean + bu, dtype=float)
        positions, inner_ids = [], []
        for position, mid in enumerate(movie_ids):
            try:
                inner_ids.append(trainset.to_inner_iid(int(mid)))
                positions.append(position)
            except ValueError:
                continue
        if inner_ids:
            ids = np.asarray(inner_ids)
            values[positions] += self.model.bi[ids] + self.model.qi[ids] @ pu
        return np.clip(values, 0.5, 5.0)

    def _recommend_vectorized(self, user_id: int, all_movie_ids: list,
                              rated_movie_ids: list, n: int = 10):
        """Tính điểm mọi ứng viên bằng latent factors (nhanh hơn vòng lặp predict).

        Trả về danh sách (movieId, score) hoặc None nếu không vector hóa được.
        """
        try:
            trainset = self.model.trainset
            global_mean = trainset.global_mean
            if user_id in self.extra_users:
                # User cập nhật online (chưa có trong trainset) → dùng vector riêng
                pu, user_bias = self.extra_users[user_id]
            else:
                inner_uid = trainset.to_inner_uid(user_id)
                pu = self.model.pu[inner_uid]
                user_bias = self.model.bu[inner_uid]
            bi = self.model.bi
            qi = self.model.qi
        except (AttributeError, IndexError, KeyError, ValueError):
            return None

        inner_iids = []
        valid_mids = []
        for mid in all_movie_ids:
            if mid in rated_movie_ids:
                continue
            try:
                inner_iids.append(trainset.to_inner_iid(mid))
                valid_mids.append(mid)
            except (ValueError, KeyError):
                continue

        if not valid_mids:
            return []

        iids = np.array(inner_iids)
        scores = global_mean + user_bias + bi[iids] + pu @ qi[iids].T
        order = np.argsort(-scores)
        return [(int(valid_mids[i]), float(scores[i])) for i in order[:n]]

    def evaluate_test(self, test_df: pd.DataFrame) -> dict:
        """Đo lường RMSE/MAE trên tập test."""
        import numpy as np
        predictions = []
        for _, row in test_df.iterrows():
            uid, mid, real = int(row['userId']), int(row['movieId']), row['rating']
            est = self.predict(uid, mid)
            predictions.append((real, est))
            
        real_arr = np.array([p[0] for p in predictions])
        est_arr = np.array([p[1] for p in predictions])
        
        errors = real_arr - est_arr
        rmse = np.sqrt(np.mean(errors ** 2))
        mae = np.mean(np.abs(errors))
        return {"RMSE": rmse, "MAE": mae}

    def save(self, filepath: Path):
        """Lưu trữ mô hình."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        # Lưu cả đối tượng SurpriseSVDRecommender
        joblib.dump(self, filepath)
        print(f"[SurpriseSVD] Saved model to: {filepath}")

    @staticmethod
    def load(filepath: Path):
        """Tải mô hình đã lưu."""
        model = joblib.load(filepath)
        # Backward compatibility: model cũ (pickle trước khi có online update)
        # không có extra_users → khởi tạo lại để không crash
        if not hasattr(model, "extra_users"):
            model.extra_users = {}
        print(f"[SurpriseSVD] Loaded model from: {filepath}")
        return model
