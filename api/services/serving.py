"""Nạp gói phục vụ bằng con trỏ nguyên tử và checksum, không đọc kết quả TEST."""

import joblib

from src.experiments.artifacts import read_json,sha256,verify_files


def load_bundle(pointer):
    from pathlib import Path
    pointer=Path(pointer)
    selected=read_json(pointer)
    folder=(pointer.parent/selected['version']).resolve()
    if not folder.is_relative_to(pointer.parent.resolve()):raise ValueError('Version không hợp lệ')
    if sha256(folder/'manifest.json')!=selected['manifest_sha256']:raise ValueError('Checksum manifest serving không khớp')
    manifest=read_json(folder/'manifest.json')
    if manifest.get('status')!='ready':raise ValueError('Gói serving chưa sẵn sàng')
    verify_files(folder,manifest)
    return joblib.load(folder/'model.joblib'),manifest
