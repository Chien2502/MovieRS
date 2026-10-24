"""Ghi artifacts nguyên tử và kiểm tra lineage trước khi tái sử dụng."""

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def identity(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def source_provenance(root):
    root = Path(root)
    files = [p for folder in ['src', 'configs'] for p in (root / folder).rglob('*')
             if p.is_file() and p.suffix in {'.py', '.toml'} and '__pycache__' not in p.parts]
    try:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        head, dirty = None, None
    return {'git_head': head, 'dirty': dirty,
            'source_sha256': {str(p.relative_to(root)): sha256(p) for p in sorted(files)}}


def verify_files(folder, manifest):
    folder = Path(folder)
    for filename, expected in manifest['files'].items():
        target = (folder / filename).resolve()
        if not target.is_relative_to(folder.resolve()) or not target.is_file() or sha256(target) != expected:
            raise ValueError(f'Artifact thiếu hoặc sai checksum: {filename}')
