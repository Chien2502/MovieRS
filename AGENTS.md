# MovieRS agent notes — V2

## Phạm vi và entrypoint
- Không áp dụng Dely. `.agent/` là toolkit chung, không phải cấu hình MovieRS.
- API: chạy từ root bằng `python api/main.py`; `.env` gốc giữ secrets, không commit. Router dưới `/api`.
- Flutter: `mobile_app/lib/main.dart`; URL ở `mobile_app/lib/config/app_config.dart`, ưu tiên `--dart-define=API_URL=...`; không đọc `.env`.
- Dashboard: `streamlit run dashboard/app.py`, đọc artifacts V2 hoàn tất; `dashboard/legacy.py` chỉ là phiên bản tham khảo V1.
- Giữ Python comments/docstrings và Flutter UI copy bằng tiếng Việt. Player tiếp tục mô phỏng.

## Môi trường và kiểm thử
- Môi trường sạch đã tạo: `.venv-refactor/Scripts/python.exe`; Windows/Python 3.14.2.
- Cài: `pip install -r requirements.lock.txt`, `pip install --no-deps -e .`. Lock là dependency closure Windows; đổi OS/Python phải kiểm thử và tạo lock phù hợp.
- `python -m pytest -q`: test mặc định dùng file tạm; conftest ép files, pool=0 và serving pointer trống để không tác động database thật.
- Tích hợp opt-in: `$env:MOVIERS_RUN_DB_TESTS='1'; python -m pytest tests/test_postgres_integration.py -q`; chỉ tạo/xóa tài khoản fixture riêng.
- Nghiệm thu: `python scripts/verify_refactor.py --database`; thêm `--flutter` để chạy analyzer/test/build web.
- Flutter: chạy `flutter analyze`, `flutter test`, `flutter build web` trong `mobile_app`.
- HTTP smoke chỉ đọc: `python -m src.pipeline.verify_runtime`, server localhost tạm, kiểm tra SHA-256 đầu vào trước/sau.

## Dữ liệu và nghiên cứu
- Cấu hình nguồn duy nhất: `configs/research.toml` (TOML + Pydantic, không chứa secrets).
- `python -m src.experiments prepare --profile research` tạo snapshot từ toàn bộ `data/raw/ratings.csv` theo chunk.
- Mẫu mặc định: 8.000 user theo thứ tự SHA256 `20261015:userId`, giữ toàn bộ lịch sử, 1.237.592 rating. Smoke/dev/extended là 1.000/4.000/12.000 user lồng nhau.
- Cutoff mọi profile: T1=2016-07-25T17:31:14Z, T2=2018-01-23T19:51:49Z; không tự tính cutoff khác để dev nhìn vào TEST tương lai.
- `python -m src.experiments run --profile research` chọn tham số trên VAL, khóa selection rồi refit TRAIN+VAL và chấm TEST. Watchdog chạy ở tiến trình riêng, một job tại một thời điểm; không bỏ mô hình thất bại khỏi leaderboard.
- Candidate ranking là toàn catalog fit trừ lịch sử đã biết, không sample negative item. Headline giữ positive ngoài catalog; user chỉ có positive không phục vụ được vẫn tính điểm 0.
- Threshold=3.5, K=10, ba seed 42/43/44; secondary K=5/20. Seed không được coi như user độc lập; CI chênh lệch là paired user bootstrap sau khi trung bình qua seed.
- Snapshot ở `data/snapshots/<id>` và run ở `artifacts/runs/<id>` là bất biến. `source_code.zip` trong run giữ code nghiên cứu tại thời điểm chạy. Resume cần đúng code/config/dataset và checksum.
- Kết quả V2 compact được lưu `report/experiments/v2`; xem `report/REFACTOR_ACCEPTANCE.md`. Không tính phần trăm cải tiến bằng cách so kết quả khác sample/protocol.
- MostPopular tốt hơn hybrid trong run hiện tại. Không sửa giao thức/TEST để ép hybrid thắng. Đọc ablation cùng fallback trước khi quy lợi ích cho thành phần genre hoặc trọng số.
- Nghiên cứu không đọc phản hồi app, TMDB votes hiện tại hoặc model serving. `src/models/train_pipeline.py` và pipeline preprocessing cũ giữ để tái lập V1, không phải entrypoint V2.
- Không ghi đè raw, generated CSV/JSON hoặc model cũ nếu công việc không yêu cầu dữ liệu/runtime. Catalog thiếu metadata TMDB vẫn giữ title/genre gốc từ bundle; thời lượng mặc định là mô phỏng.

## PostgreSQL, xác thực và vận hành
- PostgreSQL scaffolding/schema ở `api/database.py`, `supabase/schema.sql`; migrations tạo bằng Supabase CLI. MCP OAuth/API keys không thay mật khẩu SQL.
- `MOVIERS_STORAGE` chọn đúng một nguồn files/postgres. Sau migration dự án chọn postgres; mất DB trả lỗi, không ghi fallback CSV.
- `DATABASE_POOL_SIZE` tối đa 8, hiện cấu hình 4; SSL mặc định require, `prepare_threshold=None` cho transaction pooler. Bỏ tham số Prisma `pgbouncer=true` khỏi URI Psycopg.
- Bootstrap: `python src/data/init_database.py`; kiểm tra chỉ đọc thêm `--check`. `/api/health/database` không tạo bảng.
- Import: `python -m src.data.migrate_runtime` là dry-run, `--apply` backup và import trong một transaction. Catalog canonical raw bổ sung phim thiếu TMDB. Orphan được cách ly trong backup, không tạo tài khoản giả hoặc xóa source.
- Timestamp legacy không có timezone dùng Asia/Ho_Chi_Minh, được ghi rõ trong biên bản; timestamp có offset giữ nguyên. Export rollback: `python -m src.data.migrate_runtime --export-to artifacts/<new-folder>`; không bật lại CSV cũ sau khi PostgreSQL đã có ghi mới.
- Schema moviers riêng, RLS bật và thu hồi quyền anon/authenticated. Backend SQL owner bypass RLS: middleware/API ownership là ranh giới bảo vệ, không tuyên bố RLS tự xác thực token FastAPI.
- Auth: Argon2id; hash SHA-256 cũ nâng sau login hợp lệ. Bearer opaque 12h, server lưu digest và hỗ trợ logout. User ID không phải token xác thực.
- User app ID >=200000, route user/watch/interactions và recommendations app kiểm tra quyền sở hữu; MovieLens ID lịch sử là dữ liệu demo công khai.
- Reload model cần `X-Admin-Token` khớp `ADMIN_API_TOKEN` backend. Không đưa token quản trị, secret Supabase hoặc DATABASE_URL vào Flutter.
- Feedback explicit/legacy_unknown > favorite > watch_complete. Favorite+feedback và watch+feedback cùng transaction; retry không lặp SGD. Bỏ favorite rút proxy; xem dở không phải dislike. >=95% là proxy 4.0, không phải sao chủ động.
- `Idempotency-Key` ràng buộc payload trong 24 giờ; replay cũ không đảo trạng thái mới, payload khác cùng key trả 409. PostgreSQL commit ledger cùng nghiệp vụ; adapter file chỉ dành cho demo một tiến trình.
- Mỗi transaction đặt SET LOCAL statement_timeout/lock_timeout; không chỉ dựa vào startup options khi đi qua pooler.
- API không chạy retrain nền. Worker: `python -m src.pipeline.worker --snapshot <folder> --selection <run>/selection.json`; chọn model bằng VAL và gate ranking + guardrail, không dùng TEST. Trỏ bằng `MOVIERS_SERVING_POINTER=artifacts/serving/current.json`.
- Worker tạo bundle mới, kiểm tra checksum và đổi con trỏ nguyên tử; `--rollback <version>` về bundle hợp lệ. Serving nhận feedback vào lịch sử fit riêng; holdout nghiên cứu không đổi.
- Model serving dùng title/genre canonical và metadata enrichment khi có. Onboarding rerank là hành vi ứng dụng, không phải metric MovieLens có nhãn onboarding thật.
