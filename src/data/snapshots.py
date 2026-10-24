"""Tạo snapshot user-cluster từ toàn nguồn; không sửa kho dữ liệu vận hành."""

import hashlib
import shutil
import tempfile
import sqlite3
from contextlib import closing
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from src.experiments.artifacts import identity, read_json, sha256, utc_now, verify_files, write_json

COLUMNS = ['userId', 'movieId', 'rating', 'timestamp']
DTYPES = {'userId': 'int32', 'movieId': 'int32', 'rating': 'float32', 'timestamp': 'int64'}


def ordered_users(users, seed):
    return sorted(set(int(u) for u in users),
                  key=lambda u: (hashlib.sha256(f'{seed}:{u}'.encode()).digest(), u))


def selected_hash(users):
    return hashlib.sha256('\n'.join(map(str, users)).encode()).hexdigest()


def validate_chunk(frame):
    if frame[COLUMNS].isna().any().any():
        raise ValueError('Nguồn có ô trống')
    if any(((frame[c] <= 0) | (frame[c] % 1 != 0)).any() for c in ['userId', 'movieId']):
        raise ValueError('ID phải là số nguyên dương')
    if not frame.rating.between(.5, 5).all() or ((frame.rating * 2) % 1 != 0).any():
        raise ValueError('Rating phải thuộc [0.5,5], theo bước 0.5')
    if (frame.timestamp < 0).any() or (frame.timestamp % 1 != 0).any():
        raise ValueError('Timestamp epoch không hợp lệ')


def _distribution(frame):
    years = pd.to_datetime(frame.timestamp, unit='s', utc=True).dt.year
    return {'ratings': {str(float(k)): int(v) for k, v in frame.rating.value_counts().items()},
            'years': {str(int(k)): int(v) for k, v in years.value_counts().items()}}


def prepare_snapshot(config, profile='research', check=lambda: None):
    """Kiểm tra nguồn trước sampling; chỉ công bố snapshot sau khi đủ artifacts."""
    specification = config.profiles[profile]
    raw = config.path(config.source_dir)
    ratings_path, movies_path = raw / 'ratings.csv', raw / 'movies.csv'
    source_hash, movie_hash = sha256(ratings_path), sha256(movies_path)
    if config.expected_source_sha256 and source_hash != config.expected_source_sha256:
        raise ValueError('Checksum nguồn khác ML-25M đã đăng ký')
    archive_check = {'verified': False, 'reason': 'Chưa yêu cầu checksum ZIP'}
    if config.expected_archive_md5:
        digest = hashlib.md5()
        with (raw / 'ml-25m.zip').open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != config.expected_archive_md5:
            raise ValueError('Checksum ZIP không khớp nguồn chính thức đã đăng ký')
        archive_check = {'verified': True, 'md5': digest.hexdigest(),
                         'url': 'https://files.grouplens.org/datasets/movielens/ml-25m.zip.md5'}
    definition = {'source_sha256': source_hash, 'movies_sha256': movie_hash,
                  'seed': config.sample_seed, 'users': specification.users,
                  't1': config.t1.isoformat(), 't2': config.t2.isoformat(), 'version': 2, 'builder_revision': 3}
    dataset_id = identity(definition)[:20]
    destination = config.path(config.snapshot_dir) / dataset_id
    if (destination / 'manifest.json').exists():
        manifest = read_json(destination / 'manifest.json')
        verify_files(destination, manifest)
        return destination
    check()
    movies = pd.read_csv(movies_path)
    numeric_ids=pd.to_numeric(movies.movieId,errors='raise')
    if ((numeric_ids<=0)|(numeric_ids%1!=0)).any():raise ValueError('Movie ID không hợp lệ')
    if movies.movieId.duplicated().any() or movies[['movieId', 'title']].isna().any().any():
        raise ValueError('Danh mục phim có ID trùng hoặc thiếu thông tin bắt buộc')
    movie_ids = set(movies.movieId.astype(int))
    counts, item_counts, rating_hist, years = Counter(), Counter(), Counter(), Counter()
    last_pair = None
    source_sorted = True
    total = 0
    # Kiểm tra trước khi ép dtype để tránh cắt phần thập phân ID không hợp lệ.
    for chunk in pd.read_csv(ratings_path, usecols=COLUMNS, chunksize=config.chunk_rows):
        check()
        validate_chunk(chunk)
        if not set(chunk.movieId.unique()).issubset(movie_ids):
            raise ValueError('Rating tham chiếu phim không có trong danh mục')
        pairs = pd.MultiIndex.from_frame(chunk[['userId', 'movieId']])
        if pairs.has_duplicates:
            raise ValueError('Nguồn có cặp user–movie trùng')
        source_sorted = source_sorted and pairs.is_monotonic_increasing
        first, last = pairs[0], pairs[-1]
        if last_pair is not None:
            if first == last_pair:raise ValueError('Nguồn có cặp trùng ở ranh giới chunk')
            source_sorted = source_sorted and first > last_pair
        last_pair = last
        counts.update({int(k): int(v) for k, v in chunk.userId.value_counts().items()})
        item_counts.update({int(k): int(v) for k, v in chunk.movieId.value_counts().items()})
        hist = _distribution(chunk)
        rating_hist.update(hist['ratings'])
        years.update(hist['years'])
        total += len(chunk)
    if not source_sorted:
        # Nguồn đổi thứ tự vẫn lấy cùng sample. Unique index trên đĩa bắt trùng xuyên chunk.
        with tempfile.TemporaryDirectory(prefix='moviers-source-audit-') as temporary:
            with closing(sqlite3.connect(str(Path(temporary)/'pairs.db'))) as database, database:
                database.execute('PRAGMA cache_size=-16384')
                database.execute('CREATE TABLE pairs(user_id INTEGER,movie_id INTEGER,PRIMARY KEY(user_id,movie_id)) WITHOUT ROWID')
                try:
                    for chunk in pd.read_csv(ratings_path,usecols=['userId','movieId'],chunksize=config.chunk_rows):
                        check()
                        database.executemany('INSERT INTO pairs VALUES(?,?)',chunk.itertuples(index=False,name=None))
                except sqlite3.IntegrityError:
                    raise ValueError('Nguồn có cặp trùng xuyên chunk') from None
    if specification.users > len(counts):
        raise ValueError('Số user yêu cầu vượt số user nguồn')
    ids = ordered_users(counts, config.sample_seed)[:specification.users]
    selected = set(ids)
    parts = []
    for chunk in pd.read_csv(ratings_path, usecols=COLUMNS, dtype=DTYPES, chunksize=config.chunk_rows):
        check()
        parts.append(chunk[chunk.userId.isin(selected)])
    sample = pd.concat(parts, ignore_index=True).sort_values(COLUMNS[3:] + COLUMNS[:2], kind='stable').reset_index(drop=True)
    if sample.duplicated(['userId', 'movieId']).any():
        raise ValueError('Sample có cặp trùng')
    if specification.expected_rows and len(sample) != specification.expected_rows:
        raise ValueError('Số dòng sample không khớp đặc tả')
    t1, t2 = int(config.t1.timestamp()), int(config.t2.timestamp())
    train = sample[sample.timestamp < t1]
    val = sample[(sample.timestamp >= t1) & (sample.timestamp < t2)]
    test = sample[sample.timestamp >= t2]
    if any(f.empty for f in [train, val, test]):
        raise ValueError('Có split rỗng ở cutoff đã đăng ký')
    if not train.timestamp.max() < val.timestamp.min() <= val.timestamp.max() < test.timestamp.min():
        raise ValueError('Vi phạm ranh giới thời gian')
    hist = _distribution(sample)
    from src.models.hybrid import parse_genres
    sample_item_counts=sample.movieId.value_counts().to_dict()
    source_genres,sample_genres=Counter(),Counter()
    for row in movies.itertuples():
        for genre in parse_genres(row.genres):
            source_genres[genre]+=item_counts.get(int(row.movieId),0)
            sample_genres[genre]+=sample_item_counts.get(int(row.movieId),0)
    def popularity_bin(count):
        return '<20' if count<20 else ('20-99' if count<100 else ('100-999' if count<1000 else '1000+'))
    source_tail,sample_tail=Counter(),Counter()
    for mid,count in item_counts.items():
        source_tail[popularity_bin(count)]+=count
        sample_tail[popularity_bin(count)]+=sample_item_counts.get(mid,0)
    tv = .5 * sum(abs(hist['ratings'].get(k, 0) / len(sample) - v / total) for k, v in rating_hist.items())
    year_delta = max(abs(hist['years'].get(k, 0) / len(sample) - v / total) for k, v in years.items())
    warnings = []
    if tv > .02:
        warnings.append('TV phân phối rating vượt 0.02')
    if year_delta > .02:
        warnings.append('Độ lệch tỷ trọng năm vượt 2 điểm phần trăm')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f'.{dataset_id}-', dir=destination.parent))
    try:
        sample.to_parquet(temporary / 'ratings.parquet', index=False)
        for name, frame in [('train', train), ('validation', val), ('test', test)]:
            frame.to_parquet(temporary / f'{name}.parquet', index=False)
        movies.to_parquet(temporary / 'movies.parquet', index=False)
        write_json(temporary / 'selected_users.json', ids)
        def profile_stats(frame):
            return {'rows': len(frame), 'users': int(frame.userId.nunique()), 'items': int(frame.movieId.nunique()),
                    'min_epoch': int(frame.timestamp.min()), 'max_epoch': int(frame.timestamp.max())}
        quality = {'status': 'warning' if warnings else 'passed', 'warnings': warnings,
                   'source_rows': total, 'source_users': len(counts), 'source_rated_items': len(item_counts),
                   'catalog_movies': len(movies), 'source_sorted_by_user_movie':bool(source_sorted), 'source_rating_histogram': dict(rating_hist),
                   'source_year_histogram': dict(years), 'sample_distributions': hist,
                   'source_genre_assignments':dict(source_genres),'sample_genre_assignments':dict(sample_genres),
                   'source_popularity_bins_rating_counts':dict(source_tail),'sample_popularity_bins_rating_counts':dict(sample_tail),
                   'sample_rated_items':int(sample.movieId.nunique()),
                   'rating_total_variation': tv, 'max_year_share_delta': year_delta,
                   'selection_probability_per_user': len(ids) / len(counts),
                   'source_user_activity_quantiles': np.quantile(list(counts.values()), [0,.25,.5,.75,.9,.99,1]).tolist(),
                   'sample_user_activity_quantiles': np.quantile(sample.userId.value_counts(), [0,.25,.5,.75,.9,.99,1]).tolist(),
                   'missing_genre_movies': int(movies.genres.isna().sum() + (movies.genres == '(no genres listed)').sum()),
                   'archive_checksum': archive_check,
                   'hard_checks': {'missing': 0, 'invalid': 0, 'duplicate_pairs': 0, 'orphan_items': 0},
                   'limitations': ['Mẫu user không đảm bảo bao phủ mọi phim hoặc năm hiếm.',
                                   'Rating tự chọn, thiếu exposure và demographic; không phải nhãn dislike cho phim chưa xem.',
                                   'Genre là snapshot hồi cứu; TMDB hiện tại không là feature đánh giá.',
                                   'Checksum chứng minh toàn vẹn file, không chứng minh tính đúng khách quan của sở thích.']}
        write_json(temporary / 'quality.json', quality)
        (temporary / 'data_card.md').write_text(
            f'# Data card {dataset_id}\n\nMovieLens 25M; seed={config.sample_seed}; user-cluster, giữ toàn bộ lịch sử.\n\n'
            f'{len(sample):,} rating / {len(ids):,} user / {sample.movieId.nunique():,} phim có rating.\n\n'
            f'TV số sao={tv:.6f}; max lệch tỷ trọng năm={year_delta:.6f}.\n\n'
            'Tham khảo quality.json để xem phân phối, checksum, giới hạn và cảnh báo.\n', encoding='utf-8')
        manifest = {'schema_version': 2, 'dataset_id': dataset_id, 'created_at': utc_now(), 'status': 'complete',
                    'definition': definition, 'profile': profile, 'selected_users_sha256': selected_hash(ids),
                    'splits': {n: profile_stats(f) for n, f in [('train', train), ('validation', val), ('test', test)]},
                    'files': {p.name: sha256(p) for p in temporary.iterdir()}}
        write_json(temporary / 'manifest.json', manifest)
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    return destination


def load_snapshot(folder):
    folder = Path(folder)
    manifest = read_json(folder / 'manifest.json')
    if manifest['status'] != 'complete':
        raise ValueError('Snapshot chưa hoàn tất')
    verify_files(folder, manifest)
    return manifest
