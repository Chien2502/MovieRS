"""Smoke HTTP thật bằng server tạm; không tạo tài khoản hoặc ghi feedback.

Chạy từ gốc: python src/pipeline/verify_runtime.py
"""

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from src.data.protocol import file_fingerprint


def snapshot_inputs():
    """Đối chiếu dữ liệu/model trước và sau, không chỉ dựa vào số dòng."""
    names = ['ratings_processed.csv', 'ratings_train.csv', 'ratings_val.csv', 'ratings_test.csv',
             'movies_processed.csv', 'users.json', 'user_favorites.csv', 'watch_progress.csv', 'interactions_log.csv']
    paths = [PROJECT_ROOT / 'data/processed' / name for name in names]
    paths += [PROJECT_ROOT / 'models/model_latest.pkl', PROJECT_ROOT / 'models/model_latest.json']
    return {str(path.relative_to(PROJECT_ROOT)): file_fingerprint(path) if path.exists() else None for path in paths}


def main():
    before = snapshot_inputs()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {**os.environ, 'AUTO_RETRAIN': '0', 'API_RELOAD': '0', 'PYTHONIOENCODING': 'utf-8'}
    process = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', str(port)],
        cwd=PROJECT_ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        for attempt in range(100):
            if process.poll() is not None:
                raise RuntimeError('Tiến trình API đã dừng trước khi sẵn sàng')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                    break
            except OSError:
                if attempt == 99:
                    raise RuntimeError('API không mở cổng trong thời gian chờ')
                time.sleep(0.1)
        rows = []
        routes = ['/health', '/health/database', '/movies/popular?limit=10', '/recommendations/1?limit=10',
                  '/recommendations/1?limit=35', '/recommendations/1?explore=true',
                  '/recommendations/199999?limit=10', '/movies/search?q=%5B']
        for route in routes:
            started = time.perf_counter()
            response = requests.get(f'http://127.0.0.1:{port}/api{route}', timeout=45)
            response.raise_for_status()
            data = response.json()
            if route.startswith('/recommendations/'):
                assert len({m['movieId'] for m in data['recommendations']}) == data['count']
                assert all(m.get('reason') for m in data['recommendations'])
            rows.append({'route': route, 'status': response.status_code,
                         'milliseconds': round((time.perf_counter()-started)*1000, 2),
                         'strategy': data.get('strategy') if isinstance(data, dict) else None})
        for route,method,expected in [('/users/200000/profile','GET',401),('/recommendations/reload','POST',403)]:
            response=requests.request(method,f'http://127.0.0.1:{port}/api{route}',timeout=10)
            assert response.status_code==expected
            rows.append({'route':route,'status':response.status_code,'expected':expected})
        after = snapshot_inputs()
        assert before == after, 'Dữ liệu hoặc model đã thay đổi trong lúc smoke test'
        artifact = {'created_at': datetime.now(timezone.utc).isoformat(), 'mode': 'real_HTTP_uvicorn_localhost_single_process',
                    'auto_retrain': False, 'inputs_unchanged_by_sha256': before == after,
                    'input_sha256': before, 'checks': rows}
        output = PROJECT_ROOT / 'report/http_smoke.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(artifact, ensure_ascii=False, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=15)


if __name__ == '__main__':
    main()
