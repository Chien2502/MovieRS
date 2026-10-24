"""Loader từ chối artifacts lỗi và giao thức không tương thích."""

import copy

import pytest

from dashboard.services.artifacts import load_run,require_comparable


def test_comparison_rejects_different_evaluation_users():
    base={'manifest':{'dataset_id':'a','split_hashes':{'test':'b'},'evaluation_users_sha256':'same',
                      'protocol':{'k':10,'threshold':3.5}}}
    other=copy.deepcopy(base)
    require_comparable(base,other)
    other['manifest']['evaluation_users_sha256']='different'
    with pytest.raises(ValueError,match='protocol'):require_comparable(base,other)


def test_loader_rejects_failed_run(tmp_path):
    (tmp_path/'manifest.json').write_text('{"schema_version":2,"status":"failed"}')
    with pytest.raises(ValueError,match='hoàn tất'):load_run(tmp_path)
