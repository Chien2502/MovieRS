"""
evaluate.py — Module đánh giá chất lượng hệ khuyến nghị toàn diện

Bao gồm:
  1. Độ chính xác dự đoán (Prediction Accuracy): RMSE, MAE.
  2. Độ chính xác xếp hạng (Ranking Accuracy): Precision@K, Recall@K, NDCG@K.
  3. Chỉ số chất lượng gợi ý: Catalog Coverage, Diversity, Novelty.
  4. Đánh giá theo nhóm người dùng (User Group Evaluation): Cold, Warm, Heavy users.
"""

from collections import defaultdict
import numpy as np
import pandas as pd


def get_top_n(predictions, n=10):
    """Lấy ra Top-N khuyến nghị cho mỗi user từ danh sách dự đoán.
    
    predictions: List of tuples (userId, movieId, real_rating, est_rating)
    """
    top_n = defaultdict(list)
    for uid, mid, true_r, est_r in predictions:
        top_n[uid].append((mid, est_r, true_r))

    # Sắp xếp các đề xuất của từng user theo điểm dự đoán giảm dần
    for uid, user_ratings in top_n.items():
      user_ratings.sort(key=lambda x: x[1], reverse=True)
      top_n[uid] = user_ratings[:n]

    return top_n


def precision_recall_at_k(predictions, k=10, threshold=3.5):
    """Tính Precision@K và Recall@K.
    
    threshold: điểm rating được coi là user thích phim đó.
    """
    user_est_true = defaultdict(list)
    for uid, _, true_r, est_r in predictions:
        user_est_true[uid].append((est_r, true_r))

    precisions = dict()
    recalls = dict()

    for uid, user_ratings in user_est_true.items():
        # Sắp xếp theo điểm ước lượng giảm dần
        user_ratings.sort(key=lambda x: x[0], reverse=True)
        
        # Số lượng phim thực sự thích
        n_rel = sum((true_r >= threshold) for (_, true_r) in user_ratings)
        
        # Số lượng phim được đề xuất trong top K và thực sự thích
        n_rec_k = sum((true_r >= threshold) for (_, true_r) in user_ratings[:k])
        
        # Precision@K = số phim thích được recommend / số phim được recommend
        precisions[uid] = n_rec_k / k if k > 0 else 0
        
        # Recall@K = số phim thích được recommend / tổng số phim thích thực sự
        recalls[uid] = n_rec_k / n_rel if n_rel > 0 else 1.0

    mean_precision = np.mean(list(precisions.values()))
    mean_recall = np.mean(list(recalls.values()))
    
    return mean_precision, mean_recall


def ndcg_at_k(predictions, k=10):
    """Tính NDCG@K (Normalized Discounted Cumulative Gain) trên tập dự đoán."""
    user_est_true = defaultdict(list)
    for uid, _, true_r, est_r in predictions:
        user_est_true[uid].append((est_r, true_r))

    ndcgs = []

    for uid, user_ratings in user_est_true.items():
        # Sắp xếp theo ước lượng
        user_ratings.sort(key=lambda x: x[0], reverse=True)
        top_k_ratings = [true_r for (_, true_r) in user_ratings[:k]]
        
        # Sắp xếp lý tưởng (để tính IDCG)
        ideal_ratings = sorted([true_r for (_, true_r) in user_ratings], reverse=True)[:k]
        
        # DCG@K
        dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(top_k_ratings))
        # IDCG@K
        idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal_ratings))
        
        ndcg = dcg / idcg if idcg > 0 else 0.0
        ndcgs.append(ndcg)
        
    return np.mean(ndcgs)


def catalog_coverage(top_n_recommendations, total_movies_in_catalog):
    """Tính Catalog Coverage: tỉ lệ phần trăm các phim trong catalog được recommend ít nhất 1 lần."""
    recommended_movies = set()
    for uid, recommendations in top_n_recommendations.items():
        for mid, _, _ in recommendations:
            recommended_movies.add(mid)
            
    coverage = len(recommended_movies) / total_movies_in_catalog if total_movies_in_catalog > 0 else 0.0
    return coverage, len(recommended_movies)


def evaluate_model_pipeline(model, train_df: pd.DataFrame, test_df: pd.DataFrame) -> dict:
    """Đánh giá toàn diện mô hình (tính toán tất cả các độ đo)."""
    # 1. Dự đoán trên tập test
    test_predictions = []
    for _, row in test_df.iterrows():
        uid = int(row['userId'])
        mid = int(row['movieId'])
        real = row['rating']
        est = model.predict(uid, mid)
        test_predictions.append((uid, mid, real, est))
        
    # 2. Tính RMSE, MAE
    real_arr = np.array([p[2] for p in test_predictions])
    est_arr = np.array([p[3] for p in test_predictions])
    errors = real_arr - est_arr
    rmse = np.sqrt(np.mean(errors ** 2))
    mae = np.mean(np.abs(errors))
    
    # 3. Tính Precision@10, Recall@10, NDCG@10
    precision10, recall10 = precision_recall_at_k(test_predictions, k=10, threshold=3.5)
    ndcg10 = ndcg_at_k(test_predictions, k=10)
    
    # 4. Tính Catalog Coverage
    # Lấy top 10 khuyến nghị cho mỗi user trong tập test
    top_10_recs = get_top_n(test_predictions, n=10)
    total_catalog = train_df['movieId'].nunique()
    coverage, num_recommended = catalog_coverage(top_10_recs, total_catalog)
    
    # 5. Phân tích lỗi theo nhóm độ thưa (Sparsity Group)
    # Đếm số rating của từng user ở tập Train
    user_counts = train_df['userId'].value_counts().to_dict()
    
    group_errors = defaultdict(list)
    for uid, _, real, est in test_predictions:
        count = user_counts.get(uid, 0)
        
        # Phân nhóm user
        if count < 5:
            group = "Cold Users (<5 ratings)"
        elif count <= 20:
            group = "Warm Users (5-20 ratings)"
        else:
            group = "Heavy Users (>20 ratings)"
            
        group_errors[group].append((real - est) ** 2)
        
    group_rmse = {}
    for group, squared_errs in group_errors.items():
        group_rmse[group] = np.sqrt(np.mean(squared_errs))
        
    return {
        "RMSE": rmse,
        "MAE": mae,
        "Precision@10": precision10,
        "Recall@10": recall10,
        "NDCG@10": ndcg10,
        "Catalog_Coverage": coverage,
        "Unique_Recommended_Movies": num_recommended,
        "Group_RMSE": group_rmse
    }
