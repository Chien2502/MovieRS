"""Thực nghiệm tái lập: dữ liệu cố định → validation → test → báo cáo có nguồn.

Mặc định không ghi đè model đang phục vụ hay bất kỳ CSV dữ liệu nào.
Chạy từ gốc: python src/models/train_pipeline.py --seeds 42 43 44
"""

import argparse
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.protocol import file_fingerprint, frame_fingerprint, temporal_split
from src.models.baseline import MeanRecommender, PopularityRecommender
from src.models.evaluate import evaluate_ranking, rating_metrics
from src.models.hybrid import HybridRatingModel, parse_genres
from src.models.svd_surprise import SurpriseSVDRecommender


def run_experiment(data_dir, output_dir, seeds=(42, 43, 44), ranking_users=300, epochs=20, factors=50):
    """Chọn trọng số trên VAL; chỉ sau đó đọc kết quả TEST để báo cáo."""
    if not seeds or ranking_users < 1 or epochs < 1 or factors < 1:
        raise ValueError('Cấu hình thực nghiệm không hợp lệ')
    started = time.monotonic()
    base_path, movies_path = data_dir / 'ratings_processed.csv', data_dir / 'movies_processed.csv'
    train, val, test = temporal_split(pd.read_csv(base_path))
    movies = pd.read_csv(movies_path)
    movie_genres = {int(row.movieId): parse_genres(row.genres) for row in movies.itertuples()}
    results, selection = {}, {}
    popularity = PopularityRecommender().fit(train)
    for seed in seeds:
        print(f'[Thực nghiệm] SVD seed={seed}; train={len(train):,}', flush=True)
        model = SurpriseSVDRecommender(n_factors=factors, n_epochs=epochs, reg_all=0.05, random_state=seed).fit(train)
        hybrid = HybridRatingModel(model, popularity, train.userId.unique())
        configurations = [(0.0, 0.0), (0.2, 0.0), (0.2, 0.1)]
        validation = []
        for alpha, diversity in configurations:
            ranking = evaluate_ranking(model if alpha == 0 else hybrid, train, val, movie_genres, max_users=ranking_users,
                                       genre_weight=alpha, diversity_weight=diversity)
            validation.append({'genre_weight': alpha, 'diversity_weight': diversity, 'ranking': ranking})
        best = max(validation, key=lambda row: row['ranking']['ndcg'])
        selection[str(seed)] = {'criterion': 'validation_ndcg@10', 'configurations': validation,
                                'selected_genre_weight': best['genre_weight'],
                                'selected_diversity_weight': best['diversity_weight']}
        val_rating = rating_metrics(model, train, val)
        test_rating = rating_metrics(model, train, test)
        hybrid_val_rating = rating_metrics(hybrid, train, val)
        hybrid_test_rating = rating_metrics(hybrid, train, test)
        for name, alpha, diversity in [('SVD', 0.0, 0.0),
                                       ('SVD+Genres', 0.2, 0.0),
                                       ('SVD+Genres+MMR', 0.2, 0.1)]:
            print(f'[TEST] {name}; seed={seed}', flush=True)
            results[f'{name}/seed={seed}'] = {
                'family': name, 'seed': seed, 'validation_rating': val_rating if name == 'SVD' else hybrid_val_rating,
                'test_rating': test_rating if name == 'SVD' else hybrid_test_rating,
                'test_ranking': evaluate_ranking(model if name == 'SVD' else hybrid, train, test, movie_genres, max_users=ranking_users,
                                                genre_weight=alpha, diversity_weight=diversity, exclude_df=val)}
    for name, model in [('Mean', MeanRecommender().fit(train)), ('BayesianPopularity', PopularityRecommender().fit(train))]:
        print(f'[TEST] {name}', flush=True)
        results[name] = {'family': name, 'seed': None, 'validation_rating': rating_metrics(model, train, val),
                         'test_rating': rating_metrics(model, train, test),
                         'test_ranking': evaluate_ranking(model, train, test, movie_genres,
                                                         max_users=ranking_users, exclude_df=val)}
    summaries = {}
    for family in sorted({row['family'] for row in results.values()}):
        entries = [row for row in results.values() if row['family'] == family]
        measurements = {name: [row['test_ranking'][name] for row in entries]
                        for name in ['precision', 'recall', 'ndcg', 'coverage', 'diversity', 'novelty']}
        measurements['RMSE'] = [row['test_rating']['RMSE'] for row in entries]
        measurements['MAE'] = [row['test_rating']['MAE'] for row in entries]
        summaries[family] = {name: {'mean': float(np.mean(values)),
                                    'std_across_seeds': float(np.std(values, ddof=1)) if len(values) > 1 else None}
                              for name, values in measurements.items()}
    try:
        git_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=PROJECT_ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=PROJECT_ROOT, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        git_head, dirty = None, None
    source_paths = ['src/models/train_pipeline.py', 'src/models/evaluate.py', 'src/models/hybrid.py',
                    'src/models/svd_surprise.py', 'src/models/baseline.py', 'src/data/protocol.py']
    payload = {
        'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
        'protocol': {'split': 'global_temporal_80_10_10_timestamp_ties_stay_together',
                     'ranking_candidates': 'all_train_items_minus_train_and_validation_history_for_test',
                     'negative_item_sampling': False, 'user_sampling': 'uniform_without_replacement_seed_42',
                     'threshold': 3.5, 'k': 10, 'ranking_users_limit': ranking_users,
                     'unobserved_items': 'treated_as_nonrelevant_offline_not_as_true_dislikes',
                     'onboarding_preferences': 'not_available_in_MovieLens_not_inferred_from_test',
                     'implicit_feedback': 'excluded_from_academic_experiment',
                     'hybrid_cold_start': 'Bayesian_popularity_same_as_serving',
                     'ci95': 'percentile_user_bootstrap_1000_resamples_conditional_on_fixed_user_sample'},
        'dataset': {'ratings_sha256': file_fingerprint(base_path), 'movies_sha256': file_fingerprint(movies_path),
                    'ratings': int(len(train) + len(val) + len(test)), 'catalog_movies': len(movies),
                    'splits': {name: {'rows': len(df), 'users': int(df.userId.nunique()), 'items': int(df.movieId.nunique()),
                                     'start': str(df.timestamp.min()), 'end': str(df.timestamp.max()),
                                     'sha256': frame_fingerprint(df)} for name, df in [('train', train), ('val', val), ('test', test)]}},
        'environment': {'python': platform.python_version(), 'platform': platform.platform(), 'git_head': git_head,
                        'working_tree_dirty': dirty, 'source_sha256': {p: file_fingerprint(PROJECT_ROOT / p) for p in source_paths},
                        'packages': {p: importlib.metadata.version(p) for p in ['numpy', 'pandas', 'scikit-surprise']}},
        'parameters': {'seeds': list(seeds), 'n_factors': factors, 'n_epochs': epochs, 'reg_all': 0.05, 'lr_all': 0.005},
        'validation_selection': selection, 'results': results, 'summary': summaries,
        'duration_seconds': round(time.monotonic() - started, 2),
        'limitations': ['Đánh giá hồi cứu trên MovieLens; chưa đo hài lòng người dùng thật.',
                        'Lấy mẫu user cho ranking; RMSE/MAE dùng toàn bộ split.',
                        'Hai biến thể hybrid dùng cùng bộ dự đoán SVD/popularity nên RMSE/MAE giống nhau; chỉ khác thứ tự Top-K.',
                        'MMR dùng pool 200 ứng viên; toàn bộ danh mục TRAIN được chấm trước khi lấy pool.',
                        'Phim chưa có ở TRAIN không phục vụ được; báo cáo tỷ lệ positive ngoài danh mục.',
                        'Bộ dữ liệu processed đã qua lấy mẫu/lọc toàn cục; chưa tái tạo lọc chỉ bằng TRAIN từ raw.',
                        'Không suy ra kết luận SVD giải quyết cold-start hay hybrid luôn tốt hơn baseline.']}
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    (output_dir / f'experiment_{timestamp}.json').write_text(serialized, encoding='utf-8')
    tmp = output_dir / 'latest.json.tmp'
    tmp.write_text(serialized, encoding='utf-8')
    tmp.replace(output_dir / 'latest.json')
    rows = [{'model': name, **{metric: value['mean'] for metric, value in metrics.items()}}
            for name, metrics in summaries.items()]
    table = pd.DataFrame(rows)
    table.to_csv(output_dir / 'summary.csv', index=False)
    print(table.to_string(index=False), flush=True)
    return payload


def main():
    parser = argparse.ArgumentParser(description='Thực nghiệm MovieRS; không thay model hoặc dữ liệu phục vụ')
    parser.add_argument('--data-dir', type=Path, default=PROJECT_ROOT / 'data/processed')
    parser.add_argument('--output-dir', type=Path, default=PROJECT_ROOT / 'report/experiments')
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 43, 44])
    parser.add_argument('--ranking-users', type=int, default=300)
    parser.add_argument('--epochs', type=int, default=int(os.getenv('SVD_N_EPOCHS', '20')))
    parser.add_argument('--factors', type=int, default=int(os.getenv('SVD_N_FACTORS', '50')))
    args = parser.parse_args()
    run_experiment(args.data_dir, args.output_dir, args.seeds, args.ranking_users, args.epochs, args.factors)


if __name__ == '__main__':
    main()
