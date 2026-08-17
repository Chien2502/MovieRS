"""
svd_numpy.py — Tự xây dựng thuật toán FunkSVD bằng NumPy & Stochastic Gradient Descent (SGD)

Mục đích:
  - Chứng minh sự hiểu biết sâu sắc về mặt toán học của thuật toán Phân rã ma trận (Matrix Factorization).
  - Không sử dụng thư viện Surprise, tự quản lý việc cập nhật tham số (Biases, Latent Vectors) và tối ưu hóa hàm lỗi.
  - Phù hợp để làm trọng tâm phần lý thuyết và thực nghiệm trong báo cáo.
"""

import numpy as np
import pandas as pd


class NumPyFunkSVD:
    """Thuật toán FunkSVD tự viết bằng NumPy sử dụng SGD."""
    def __init__(self, n_factors=50, lr=0.005, reg=0.02, n_epochs=20):
        self.n_factors = n_factors
        self.lr = lr
        self.reg = reg
        self.n_epochs = n_epochs
        
        # Các tham số của mô hình
        self.global_mean = 0.0
        self.bu = None  # User biases
        self.bi = None  # Movie biases
        self.P = None   # User latent factors matrix (N_users x n_factors)
        self.Q = None   # Movie latent factors matrix (N_movies x n_factors)
        
        # Mapping từ raw ID sang index nội bộ (0 -> N-1)
        self.user_to_idx = {}
        self.idx_to_user = {}
        self.movie_to_idx = {}
        self.idx_to_movie = {}

    def fit(self, train_df: pd.DataFrame, val_df: pd.DataFrame = None):
        """Huấn luyện mô hình sử dụng SGD."""
        print(f"[NumPySVD] Bắt đầu chuẩn bị cấu trúc dữ liệu...")
        
        # 1. Tạo mapping ID
        unique_users = train_df['userId'].unique()
        unique_movies = train_df['movieId'].unique()
        
        self.user_to_idx = {uid: idx for idx, uid in enumerate(unique_users)}
        self.idx_to_user = {idx: uid for uid, idx in self.user_to_idx.items()}
        self.movie_to_idx = {mid: idx for idx, mid in enumerate(unique_movies)}
        self.idx_to_movie = {idx: mid for mid, idx in self.movie_to_idx.items()}
        
        num_users = len(unique_users)
        num_movies = len(unique_movies)
        
        # 2. Khởi tạo các tham số
        self.global_mean = train_df['rating'].mean()
        
        # Khởi tạo ngẫu nhiên P và Q với phân phối chuẩn nhỏ
        self.bu = np.zeros(num_users)
        self.bi = np.zeros(num_movies)
        self.P = np.random.normal(0, 0.1, (num_users, self.n_factors))
        self.Q = np.random.normal(0, 0.1, (num_movies, self.n_factors))
        
        # 3. Chuẩn bị tập dữ liệu huấn luyện dạng numpy array để tối ưu hóa tốc độ vòng lặp
        train_data = []
        for _, row in train_df.iterrows():
            u_idx = self.user_to_idx[row['userId']]
            i_idx = self.movie_to_idx[row['movieId']]
            rating = row['rating']
            train_data.append((u_idx, i_idx, rating))
            
        train_data = np.array(train_data)
        
        print(f"[NumPySVD] Khởi tạo hoàn tất. Users: {num_users:,}, Movies: {num_movies:,}, Ratings: {len(train_data):,}")
        print(f"[NumPySVD] Bắt đầu huấn luyện trong {self.n_epochs} epochs...")
        
        for epoch in range(self.n_epochs):
            # Trộn ngẫu nhiên dữ liệu huấn luyện ở mỗi epoch để SGD hội tụ tốt hơn
            np.random.shuffle(train_data)
            
            loss_sum = 0
            for u_idx, i_idx, r in train_data:
                u_idx = int(u_idx)
                i_idx = int(i_idx)
                
                # Dự đoán rating: r_pred = mean + b_u + b_i + P_u . Q_i
                pred = self.global_mean + self.bu[u_idx] + self.bi[i_idx] + np.dot(self.P[u_idx], self.Q[i_idx])
                
                # Sai số
                err = r - pred
                loss_sum += err ** 2
                
                # Cập nhật tham số theo hướng ngược gradient
                # 1. Cập nhật Biases
                self.bu[u_idx] += self.lr * (err - self.reg * self.bu[u_idx])
                self.bi[i_idx] += self.lr * (err - self.reg * self.bi[i_idx])
                
                # 2. Cập nhật Latent Factors (lưu lại giá trị cũ của P để cập nhật Q đúng đắn)
                p_old = self.P[u_idx].copy()
                self.P[u_idx] += self.lr * (err * self.Q[i_idx] - self.reg * self.P[u_idx])
                self.Q[i_idx] += self.lr * (err * p_old - self.reg * self.Q[i_idx])
                
            # Tính toán RMSE trên tập train
            train_rmse = np.sqrt(loss_sum / len(train_data))
            
            # Tính toán RMSE trên tập validation (nếu có)
            val_info = ""
            if val_df is not None:
                val_rmse = self.evaluate_rmse(val_df)
                val_info = f" | Val RMSE: {val_rmse:.4f}"
                
            print(f"    Epoch {epoch+1:02d}/{self.n_epochs:02d} | Train RMSE: {train_rmse:.4f}{val_info}")
            
        print("[NumPySVD] Huấn luyện hoàn tất.")
        return self

    def predict(self, user_id: int, movie_id: int) -> float:
        """Dự đoán rating cho một cặp user-movie."""
        u_idx = self.user_to_idx.get(user_id, -1)
        i_idx = self.movie_to_idx.get(movie_id, -1)
        
        # Xử lý Cold-Start (nếu user hoặc item mới chưa từng xuất hiện ở tập Train)
        # Sử dụng Baseline đơn giản
        user_exists = u_idx != -1
        movie_exists = i_idx != -1
        
        if user_exists and movie_exists:
            pred = self.global_mean + self.bu[u_idx] + self.bi[i_idx] + np.dot(self.P[u_idx], self.Q[i_idx])
        elif user_exists:
            pred = self.global_mean + self.bu[u_idx]
        elif movie_exists:
            pred = self.global_mean + self.bi[i_idx]
        else:
            pred = self.global_mean
            
        # Giới hạn điểm rating từ 0.5 đến 5.0
        return float(np.clip(pred, 0.5, 5.0))

    def evaluate_rmse(self, df: pd.DataFrame) -> float:
        """Tính RMSE của mô hình trên một tập dữ liệu bất kỳ."""
        loss_sum = 0
        count = 0
        for _, row in df.iterrows():
            uid, mid, real = int(row['userId']), int(row['movieId']), row['rating']
            pred = self.predict(uid, mid)
            loss_sum += (real - pred) ** 2
            count += 1
        return np.sqrt(loss_sum / count) if count > 0 else 0.0

    def evaluate_test(self, test_df: pd.DataFrame) -> dict:
        """Đo lường RMSE/MAE trên tập test."""
        errors = []
        abs_errors = []
        for _, row in test_df.iterrows():
            uid, mid, real = int(row['userId']), int(row['movieId']), row['rating']
            pred = self.predict(uid, mid)
            err = real - pred
            errors.append(err ** 2)
            abs_errors.append(abs(err))
            
        rmse = np.sqrt(np.mean(errors))
        mae = np.mean(abs_errors)
        return {"RMSE": rmse, "MAE": mae}
