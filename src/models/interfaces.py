"""Hợp đồng mô hình, tách điểm xếp hạng khỏi dự đoán số sao."""

from pathlib import Path
from typing import Protocol

import joblib
import numpy as np
import pandas as pd


class RankingModel(Protocol):
    supports_rating_prediction: bool

    def fit(self, ratings: pd.DataFrame): ...
    def score_items(self, user_id: int, movie_ids) -> np.ndarray: ...
    def save(self,path:Path): ...


def save_model(model: RankingModel, path: Path):
    """Chỉ nạp lại artifacts do dự án tạo; pickle không phải định dạng tải từ người lạ."""
    callback=getattr(model,'check',None)
    if hasattr(model,'check'):model.check=None
    try:joblib.dump(model,path,compress=3)
    finally:
        if hasattr(model,'check'):model.check=callback


def load_model(path):
    """Chỉ nạp pickle tin cậy đã được kiểm tra checksum ở lớp artifact."""
    model=joblib.load(path)
    if not callable(getattr(model,'score_items',None)) or not hasattr(model,'supports_rating_prediction'):
        raise ValueError('Artifact không đáp ứng hợp đồng mô hình')
    return model


class SerializableModel:
    def save(self,path):
        save_model(self,Path(path))

    @classmethod
    def load(cls,path):
        model=load_model(path)
        if not isinstance(model,cls):raise ValueError('Artifact thuộc họ mô hình khác')
        return model
