"""
baseline.py — Định nghĩa các mô hình cơ sở (Baseline Models) làm thước đo so sánh

Bao gồm:
  1. MeanRecommender: Dự đoán bằng điểm trung bình toàn cục (Dummy Baseline).
  2. PopularityRecommender: Gợi ý các phim phổ biến nhất (phim được đánh giá nhiều nhất và điểm cao).
  3. KNNRecommender: Collaborative Filtering (User-based / Item-based) sử dụng scikit-surprise.
"""

import numpy as np
import pandas as pd
from surprise import Dataset, Reader, KNNBasic
from surprise.prediction_algorithms.predictions import Prediction


class MeanRecommender:
    """Mô hình dự đoán đơn giản: luôn trả về điểm trung bình của toàn bộ tập Train."""
    def __init__(self):
        self.global_mean = 3.5

    def fit(self, train_df: pd.DataFrame):
        self.global_mean = train_df['rating'].mean()
        print(f"[MeanRecommender] Fitted. Global Mean = {self.global_mean:.4f}")
        return self

    def predict(self, user_id: int, movie_id: int) -> float:
        return self.global_mean

    def evaluate_test(self, test_df: pd.DataFrame) -> dict:
        """Đo lường RMSE/MAE trên tập test."""
        predictions = test_df['rating'].apply(lambda x: self.global_mean)
        errors = test_df['rating'] - predictions
        rmse = np.sqrt(np.mean(errors ** 2))
        mae = np.mean(np.abs(errors))
        return {"RMSE": rmse, "MAE": mae}


class PopularityRecommender:
    """Mô hình gợi ý không cá nhân hóa: gợi ý các bộ phim phổ biến nhất."""
    def __init__(self, top_n=20):
        self.top_n = top_n
        self.popular_movies = []
        self.global_mean = 3.5

    def fit(self, train_df: pd.DataFrame):
        self.global_mean = train_df['rating'].mean()
        
        # Tính toán mức độ phổ biến dựa trên số lượng rating và điểm trung bình
        movie_stats = train_df.groupby('movieId').agg(
            rating_count=('rating', 'count'),
            rating_mean=('rating', 'mean')
        ).reset_index()
        
        # Công thức tính score kết hợp: Bayesian Average hoặc score đơn giản
        # Ở đây dùng công thức kết hợp: Càng nhiều rating càng tin cậy
        # score = (v * R + m * C) / (v + m)
        # Trong đó: v = rating_count, R = rating_mean, m = số rating tối thiểu cần thiết (VD: 5), C = global_mean
        m = 5
        C = self.global_mean
        movie_stats['popularity_score'] = (
            (movie_stats['rating_count'] * movie_stats['rating_mean'] + m * C) / 
            (movie_stats['rating_count'] + m)
        )
        
        # Sắp xếp để lấy Top N
        self.popular_movies_df = movie_stats.sort_values(by='popularity_score', ascending=False)
        self.popular_movies = self.popular_movies_df['movieId'].head(self.top_n).tolist()
        
        # Lưu dictionary điểm của từng phim để dự đoán
        self.movie_scores = dict(zip(movie_stats['movieId'], movie_stats['rating_mean']))
        
        print(f"[PopularityRecommender] Fitted. Top 3 phim hot nhất: {self.popular_movies[:3]}")
        return self

    def predict(self, user_id: int, movie_id: int) -> float:
        # Nếu phim tồn tại trong tập train, trả về điểm trung bình của phim đó,
        # nếu không trả về trung bình toàn cục.
        return self.movie_scores.get(movie_id, self.global_mean)

    def recommend(self, user_id: int, n=10) -> list:
        """Gợi ý Top N phim phổ biến nhất."""
        return self.popular_movies[:n]

    def evaluate_test(self, test_df: pd.DataFrame) -> dict:
        predictions = test_df['movieId'].apply(lambda mid: self.movie_scores.get(mid, self.global_mean))
        errors = test_df['rating'] - predictions
        rmse = np.sqrt(np.mean(errors ** 2))
        mae = np.mean(np.abs(errors))
        return {"RMSE": rmse, "MAE": mae}


class SurpriseKNNRecommender:
    """Sử dụng thuật toán KNN từ thư viện scikit-surprise."""
    def __init__(self, user_based=True, k=40, sim_options=None):
        self.user_based = user_based
        self.k = k
        if sim_options is None:
            self.sim_options = {
                'name': 'cosine',
                'user_based': user_based
            }
        else:
            self.sim_options = sim_options
        
        self.model = KNNBasic(k=self.k, sim_options=self.sim_options, verbose=False)
        self.trainset = None

    def fit(self, train_df: pd.DataFrame):
        # Đọc dữ liệu vào Surprise
        reader = Reader(rating_scale=(0.5, 5.0))
        data = Dataset.load_from_df(train_df[['userId', 'movieId', 'rating']], reader)
        self.trainset = data.build_full_trainset()
        
        print(f"[KNNRecommender] Đang huấn luyện KNN (user_based={self.user_based}, k={self.k})...")
        self.model.fit(self.trainset)
        print("[KNNRecommender] Huấn luyện hoàn tất.")
        return self

    def predict(self, user_id: int, movie_id: int) -> float:
        # Chuyển đổi userId và movieId sang string để khớp với kiểu đọc của Surprise nếu cần,
        # Surprise tự động map id nội bộ (raw vs inner).
        # Ta gọi hàm predict của Surprise:
        pred = self.model.predict(user_id, movie_id)
        return pred.est

    def evaluate_test(self, test_df: pd.DataFrame) -> dict:
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
