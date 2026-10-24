"""Nạp .env gốc và khởi tạo bảng PostgreSQL khi đã có DATABASE_URL.

Chạy: python src/data/init_database.py
Chỉ kiểm tra, không tạo bảng: python src/data/init_database.py --check
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from api.database import DatabaseError, database_connection, database_status

SCHEMA_SQL = PROJECT_ROOT / 'supabase/schema.sql'


def initialize_database():
    """Khởi tạo trong một giao dịch; không tải CSV hoặc thay kho lưu trữ hiện có."""
    sql = SCHEMA_SQL.read_text(encoding='utf-8')
    with database_connection() as connection:
        # Tránh hai tiến trình bootstrap cùng tạo schema một lúc.
        connection.execute('SELECT pg_advisory_xact_lock(%s)', (716200000,))
        connection.execute(sql, prepare=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Khởi tạo PostgreSQL Supabase cho MovieRS')
    parser.add_argument('--check', action='store_true', help='Chỉ kiểm tra kết nối và trạng thái schema')
    args = parser.parse_args(argv)
    load_dotenv(PROJECT_ROOT / '.env', override=False)
    if args.check:
        status = database_status()
        print(json.dumps(status, ensure_ascii=False))
        return 0 if status['status'] == 'connected' else 1
    try:
        initialize_database()
    except (DatabaseError, OSError):
        print('Chưa khởi tạo được PostgreSQL. Điền DATABASE_URL trong .env, cài requirements và kiểm tra quyền database owner.')
        return 1
    except Exception:
        print('Khởi tạo schema thất bại; giao dịch được rollback. Kiểm tra quyền PostgreSQL và file supabase/schema.sql.')
        return 1
    print('Đã tạo schema moviers và các bảng ứng dụng. Chưa chuyển dữ liệu CSV/JSON sang PostgreSQL.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
