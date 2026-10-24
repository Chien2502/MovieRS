"""Từ chối artifacts thiếu nguồn gốc, lỗi checksum hoặc so sánh khác protocol."""

from pathlib import Path

from src.data.snapshots import load_snapshot
from src.experiments.artifacts import identity, read_json, verify_files


def list_runs(base):
    result=[]
    for path in Path(base).glob('*/manifest.json'):
        try:
            if read_json(path).get('status')=='complete':result.append(path.parent)
        except (OSError,ValueError):pass
    return sorted(result,reverse=True)


def load_run(folder):
    folder=Path(folder)
    manifest=read_json(folder/'manifest.json')
    if manifest.get('schema_version')!=2 or manifest.get('status')!='complete':
        raise ValueError('Run chưa hoàn tất hoặc dùng schema không được hỗ trợ')
    for name in ['selection.json','metrics.json','comparisons.json','per_user_metrics.parquet','resource_usage.json']:
        if name not in manifest['files']:
            raise ValueError('Thiếu artifact bắt buộc: '+name)
    verify_files(folder,manifest)
    return {'folder':str(folder), 'manifest':manifest,
            **{name:read_json(folder/(name+'.json')) for name in ['selection','metrics','comparisons','resource_usage']}}


def comparison_key(run):
    manifest=run['manifest']
    return identity({'dataset':manifest['dataset_id'],'splits':manifest['split_hashes'],
                     'users':manifest['evaluation_users_sha256'],'protocol':manifest['protocol']})


def require_comparable(left,right):
    if comparison_key(left)!=comparison_key(right):
        raise ValueError('Khác dữ liệu, split, user hoặc protocol; không được tính chênh lệch trực tiếp')


def load_quality(run):
    snapshot=Path(run['manifest']['snapshot'])
    manifest=load_snapshot(snapshot)
    if manifest['dataset_id']!=run['manifest']['dataset_id']:
        raise ValueError('Snapshot không khớp run')
    return manifest,read_json(snapshot/'quality.json')
