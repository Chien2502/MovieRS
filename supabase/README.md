# PostgreSQL runtime MovieRS V2

Project Supabase: `mrtjfvtbzupbwdtljihg`. Backend kết nối SQL bằng Psycopg; MCP OAuth và API key không phải mật khẩu PostgreSQL. Giữ `DATABASE_URL` trong `.env` gốc, không đưa vào Flutter hoặc Git.

```dotenv
MOVIERS_STORAGE=postgres
DATABASE_URL=postgresql://USER:URL_ENCODED_PASSWORD@POOLER_HOST:5432/postgres
DATABASE_SSLMODE=require
DATABASE_CONNECT_TIMEOUT=5
DATABASE_POOL_SIZE=4
DATABASE_STATEMENT_TIMEOUT_MS=15000
DATABASE_LOCK_TIMEOUT_MS=5000
ADMIN_API_TOKEN=GENERATE_A_RANDOM_BACKEND_SECRET
AUTO_RETRAIN=0
```

Lấy URI thật tại Dashboard → Connect. Session pooler hỗ trợ IPv4; URL-encode mật khẩu. Connector tắt prepared statements, giới hạn pool/queue, đặt timeout trong từng transaction để có hiệu lực qua pooler. SSL `verify-full` trong URI được giữ nguyên. Không có fallback ghi CSV khi database lỗi.

## Schema và migration

Migration có version ở `migrations/`; `schema.sql` là bootstrap database mới, không thay thế quy trình nâng cấp schema cũ.

| Bảng trong schema riêng moviers | Vai trò |
|---|---|
| app_users | Tài khoản ID từ 200000, Argon2id, sở thích |
| movies | Catalog MovieLens; không chứa toàn bộ rating ML-25M |
| feedback | Một phản hồi hiệu lực/user–movie, có nguồn |
| favorites | Danh sách lưu |
| watch_progress | Vị trí/thời lượng, trạng thái tính từ tỷ lệ |
| sessions | Digest token, thời hạn và thu hồi |
| idempotency_keys | Digest request key/payload, TTL 24 giờ |
| schema_version | Phiên bản schema |

RLS bật, không cấp schema/table cho public/anon/authenticated. API kiểm tra bearer và quyền sở hữu vì kết nối SQL owner có thể bypass RLS. Đây là FastAPI quản lý danh tính, chưa dùng Supabase Auth. Không đặt schema này vào exposed schemas của Data API.

```powershell
python src/data/init_database.py --check
# Chỉ bootstrap database mới:
python src/data/init_database.py
python -m src.data.migrate_runtime
python -m src.data.migrate_runtime --apply
```

Migration runtime mặc định dry-run, backup nguyên trạng, kiểm tra FK và nhập trong transaction. Chạy lại không ghi đè cập nhật đã phát sinh. Timestamp naive của prototype được diễn giải theo Asia/Ho_Chi_Minh. Bản ghi không có tài khoản/phim được cách ly; không tạo tài khoản giả.

Favorite + feedback và progress + watch_complete commit cùng transaction. `Idempotency-Key` 8–128 ký tự gắn với nội dung; replay cùng key không ghi đè trạng thái mới hơn, dùng key cho nội dung khác trả 409. Explicit có ưu tiên cao hơn favorite/watch_complete. Flutter gửi key cho mỗi ý định ghi.

## Kiểm tra và rollback

`GET /api/health/database` chỉ kiểm tra, không tạo bảng; lỗi trả 503 và giấu URI. Integration opt-in chỉ tạo/xóa fixture có tên riêng:

```powershell
$env:MOVIERS_RUN_DB_TESTS='1'
python -m pytest tests/test_postgres_integration.py -q
python -m src.data.migrate_runtime --export-to artifacts/rollback_export_new
```

Dừng ghi khi cutover/rollback. Export vào thư mục mới gồm accounts/feedback/favorites/progress và checksum; không export phiên đăng nhập. Đối soát export rồi mới đổi adapter về files với các đường dẫn trỏ vào bản export, khởi động lại API. Không bật lại CSV cũ vì sẽ mất ghi sau cutover. Adapter file dành cho demo một tiến trình; tính nguyên tử xuyên nhiều bảng và ledger được bảo đảm ở PostgreSQL.

Bằng chứng nằm trong [biên bản nghiệm thu](../report/REFACTOR_ACCEPTANCE.md). Research snapshot/model vẫn ở local, tách hoàn toàn khỏi kho runtime.

Tham khảo: [kết nối PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [Psycopg pool](https://www.psycopg.org/psycopg3/docs/advanced/pool.html).
