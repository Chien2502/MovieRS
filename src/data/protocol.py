"""Giao thức dữ liệu tái lập, tách thực nghiệm lịch sử khỏi phản hồi ứng dụng."""

import hashlib

import numpy as np
import pandas as pd


def normalize_ratings(df):
    """Kiểm tra dữ liệu trước khi chia; không âm thầm bỏ dòng sai."""
    result = df[['userId', 'movieId', 'rating', 'timestamp']].copy()
    for name in ['userId', 'movieId', 'rating']:
        result[name] = pd.to_numeric(result[name], errors='raise')
    for name in ['userId', 'movieId']:
        if (result[name] <= 0).any() or (result[name] % 1 != 0).any():
            raise ValueError('ID phải là số nguyên dương')
        result[name] = result[name].astype('int64')
    if not result.rating.between(0.5, 5).all():
        raise ValueError('Rating phải nằm trong [0.5,5]')
    numeric = pd.to_numeric(result.timestamp, errors='coerce')
    epoch = numeric.notna()
    timestamps = pd.Series(pd.NaT, index=result.index, dtype='datetime64[ns, UTC]')
    timestamps.loc[epoch] = pd.to_datetime(numeric.loc[epoch], unit='s', utc=True, errors='raise')
    timestamps.loc[~epoch] = pd.to_datetime(result.loc[~epoch, 'timestamp'], utc=True, format='mixed', errors='raise')
    result['timestamp'] = timestamps
    if result.isna().any().any() or result.duplicated(['userId', 'movieId']).any():
        raise ValueError('Dữ liệu có ô trống hoặc trùng cặp user–movie')
    return result.sort_values(['timestamp', 'userId', 'movieId'], kind='stable').reset_index(drop=True)


def temporal_split(df):
    """Chia toàn cục 80/10/10; cùng timestamp không vượt qua ranh giới."""
    ordered = normalize_ratings(df)
    if len(ordered) < 10:
        raise ValueError('Cần ít nhất 10 đánh giá để chia dữ liệu')
    ts = ordered.timestamp
    a = int(ts.searchsorted(ts.iloc[int(len(ordered) * 0.8)], side='left'))
    b = int(ts.searchsorted(ts.iloc[int(len(ordered) * 0.9)], side='left'))
    if not 0 < a < b < len(ordered):
        raise ValueError('Không đủ mốc thời gian khác nhau để chia ba tập')
    return tuple(part.reset_index(drop=True) for part in (ordered.iloc[:a], ordered.iloc[a:b], ordered.iloc[b:]))


def frame_fingerprint(df):
    """Mã băm nội dung có thứ tự, dùng nhận diện chính xác tập đánh giá."""
    columns = ['userId', 'movieId', 'rating', 'timestamp']
    return hashlib.sha256(df[columns].to_csv(index=False).encode('utf-8')).hexdigest()


def file_fingerprint(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()
