"""Đọc cấu hình nghiên cứu; không đọc hoặc đưa secrets từ .env vào artifacts."""

import hashlib
import json
import tomllib
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ResourceConfig(StrictConfig):
    max_rss_gib: float = Field(default=2, gt=0)
    min_available_gib: float = Field(default=3, ge=0)
    threads: int = Field(default=4, ge=1, le=16)


class Profile(StrictConfig):
    users: int = Field(ge=1)
    expected_rows: int | None = Field(default=None, ge=1)
    minutes: float = Field(gt=0)


class Search(StrictConfig):
    svd: list[tuple[int, int, float]] = Field(min_length=1, max_length=4)
    knn: list[tuple[int, float]] = Field(min_length=1, max_length=3)
    tau: list[float] = Field(min_length=1, max_length=2)
    beta: list[float] = Field(min_length=1, max_length=4)
    mmr: list[float] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def valid_trials(self):
        if any(f < 1 or e < 1 or r <= 0 for f, e, r in self.svd):
            raise ValueError('Tham số SVD không hợp lệ')
        if any(n < 1 or s < 0 for n, s in self.knn) or any(t <= 0 for t in self.tau):
            raise ValueError('Tham số KNN hoặc tau không hợp lệ')
        if any(not 0 <= v <= 1 for v in self.beta + self.mmr):
            raise ValueError('Trọng số phải thuộc [0,1]')
        return self


class ResearchConfig(StrictConfig):
    version: int = Field(default=2, ge=2, le=2)
    source_dir: str = 'data/raw'
    snapshot_dir: str = 'data/snapshots'
    run_dir: str = 'artifacts/runs'
    sample_seed: int = 20261015
    chunk_rows: int = Field(default=250000, ge=1, le=1000000)
    t1: datetime
    t2: datetime
    seeds: list[int] = Field(default_factory=lambda: [42, 43, 44], min_length=1)
    ranking_users: int = Field(default=1000, ge=1)
    validation_users: int = Field(default=200, ge=1)
    threshold: float = Field(default=3.5, ge=0.5, le=5)
    k: int = Field(default=10, ge=1, le=100)
    bootstrap_samples: int = Field(default=2000, ge=100, le=10000)
    expected_source_sha256: str | None = None
    expected_archive_md5: str | None = None
    resources: ResourceConfig = Field(default_factory=ResourceConfig)
    profiles: dict[str, Profile]
    search: Search

    @model_validator(mode='after')
    def validate_protocol(self):
        if self.t1.tzinfo is None or self.t2.tzinfo is None or self.t1 >= self.t2:
            raise ValueError('Cutoff phải có múi giờ và T1 < T2')
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError('Seed không được trùng')
        if not self.profiles:
            raise ValueError('Cần ít nhất một profile')
        return self

    def path(self, value):
        p = Path(value)
        return p if p.is_absolute() else ROOT / p

    def fingerprint(self):
        encoded = json.dumps(self.model_dump(mode='json'), sort_keys=True, separators=(',', ':')).encode()
        return hashlib.sha256(encoded).hexdigest()


def load_config(path=ROOT / 'configs/research.toml'):
    with open(path, 'rb') as stream:
        return ResearchConfig.model_validate(tomllib.load(stream))
