# MovieRS — Phòng thực nghiệm hệ khuyến nghị phim

MovieRS nghiên cứu hệ khuyến nghị lai SVD, hồ sơ thể loại và độ phổ biến trên **mẫu user-cluster từ toàn bộ MovieLens 25M**. FastAPI + Flutter minh họa luồng ứng dụng; Streamlit trình bày bằng chứng dữ liệu và so sánh mô hình. Trình phát là mô phỏng.

## Kết quả và phạm vi

Mẫu chính giữ toàn bộ **1.237.592 rating của 8.000 user**, seed 20261015. Nguồn ZIP đã đối chiếu checksum GroupLens. Chia thời gian toàn cục với cutoff cố định; chọn tham số trên VAL, refit TRAIN+VAL rồi chấm TEST trên toàn catalog trước cutoff. Ranking dùng 900 user có positive, ba seed huấn luyện 42/43/44; giữ positive ngoài catalog trong metric chính.

Run xác nhận ban đầu: MostPopular NDCG@10 **0,28036**, ItemKNN **0,15770**, hybrid thích ứng **0,11859**, SVD **0,02705**. Hybrid tăng so với SVD thuần nhưng **chưa vượt baseline mạnh MostPopular**; cần đọc cả ablation cùng fallback để xác định phần cải tiến thực sự. Rating SVD RMSE **0,95575** không chứng minh xếp hạng tốt hơn. Phiên bản serving được chọn bằng VAL, không dùng TEST để quyết định deployment.

Dashboard hiển thị paired Δ/CI95, cohort, diversity, coverage, chi phí, tính đại diện và provenance. Kết quả V1 nằm trong `report/experiments` và [README lưu trữ](report/README_V1.md); không tính Δ giữa hai giao thức.

Kế hoạch: [REFACTOR_PLAN.md](report/REFACTOR_PLAN.md). Tiến độ và nghiệm thu V2: [REFACTOR_ACCEPTANCE.md](report/REFACTOR_ACCEPTANCE.md).

## Môi trường đã kiểm chứng

Chạy từ gốc repo trên Windows/Python 3.14.2:

```powershell
python -m venv .venv-refactor
.venv-refactor/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv-refactor/Scripts/python.exe -m pip install --no-deps -e .
```

`requirements.lock.txt` khóa dependency closure của môi trường Windows đã đo. Khi đổi Python/OS phải tạo và kiểm thử lại lock phù hợp. Notebook và load test là tùy chọn trong `requirements-notebooks.txt`, `requirements-loadtest.txt`.

## Dữ liệu và thực nghiệm

Nếu chưa có raw local, tải ML-25M bằng `python src/data/download_movielens.py --size 25m`. Không cần TMDB để chạy benchmark; chỉ dùng `ratings.csv` và genre gốc từ `movies.csv`. Các tham số, trial và ngân sách nằm trong `configs/research.toml`.

```powershell
.venv-refactor/Scripts/python.exe -m src.experiments prepare --profile research
.venv-refactor/Scripts/python.exe -m src.experiments run --profile research
```

Profile smoke/dev/research/extended tương ứng 1.000/4.000/8.000/12.000 user, giữ lịch sử. Tất cả dùng cùng cutoff research. Nguồn đọc theo chunk; snapshot bất biến trong `data/snapshots/<dataset_id>`. Job có watchdog RAM/thời gian ở tiến trình riêng và lock chống chạy đồng thời. Khi vượt ngân sách, run bị đánh dấu failed, không coi trial còn lại là kết quả thành công.

Lệnh in đường dẫn snapshot/run. Để resume run chưa hoàn tất, thêm `--resume artifacts/runs/<run_id>`; code/config/dataset phải khớp. Checkpoint không làm thay đổi giao thức TEST. Archive mã nguồn của run ở `source_code.zip`; metric từng user ở `per_user_metrics.parquet`.

```powershell
.venv-refactor/Scripts/python.exe -m streamlit run dashboard/app.py
```

Dashboard tự chọn run hoàn tất mới nhất. Không tự train, không dùng số liệu minh họa. Run đang chạy không che mất run hoàn tất trước đó. Các biểu đồ NDCG, rating, diversity tách đơn vị; so sánh khác dataset/protocol/user bị chặn tính Δ.

## PostgreSQL và ứng dụng

Cấu hình nằm trong `.env` gốc, được Git ignore. `DATABASE_URL` là URI PostgreSQL; OAuth MCP và API keys không thay mật khẩu database. Driver không nhận tham số Prisma `pgbouncer=true`. SSL mặc định require, prepared statements tắt khi dùng transaction pooler.

```powershell
python src/data/init_database.py --check
python src/data/init_database.py
python -m src.data.migrate_runtime
python -m src.data.migrate_runtime --apply
```

Dry-run kiểm kê và báo bản ghi không có FK. Apply backup nguyên trạng nguồn, cách ly bản ghi lỗi và import trong một transaction; chạy lại không ghi đè dữ liệu mới ở PostgreSQL. Schema/migrations nằm trong `supabase/`. ML-25M và model lớn ở local, không upload cả 25M rating vào database ứng dụng.

Sau khi đối soát, dùng `MOVIERS_STORAGE=postgres`; `files` chỉ dành cho demo/test. Pool tối đa 4 kết nối theo `DATABASE_POOL_SIZE`. Mất database trả lỗi, không tự ghi sang CSV. Rollback phải export dữ liệu đã phát sinh trước khi chuyển nguồn ghi:

```powershell
python -m src.data.migrate_runtime --export-to artifacts/rollback_export_new
```

Thư mục export phải mới. Dữ liệu chứa hash tài khoản nên chỉ lưu trong artifact local, không commit. Không copy CSV cũ đè PostgreSQL hoặc bật dual-write.

Worker tạo model phục vụ riêng, chép hai đường dẫn mà pipeline đã in:

```powershell
python -m src.pipeline.worker --snapshot data/snapshots/<dataset_id> --selection artifacts/runs/<run_id>/selection.json
```

Worker chỉ đọc selection đã khóa và TRAIN/VAL. Gate so NDCG validation, cohort, latency và RMSE khi cả hai model hỗ trợ rating; serving fit lại với lịch sử đã biết và feedback ứng dụng. Không sửa holdout hoặc nhận feedback demo vào benchmark. Chọn `MOVIERS_SERVING_POINTER=artifacts/serving/current.json` sau khi có bundle. Có thể thêm `--rollback <version>` để đổi về bundle đã kiểm chứng.

```powershell
$env:PYTHONIOENCODING='utf-8'
python api/main.py
```

API không chạy retrain nền. Docs: http://localhost:8000/docs; health: `/api/health`, `/api/health/database`. Đăng ký/login cấp bearer token 12 giờ, server chỉ lưu digest; đăng xuất thu hồi phiên. Mật khẩu mới Argon2id, tài khoản prototype nâng hash khi login hợp lệ. Route dữ liệu app kiểm tra quyền sở hữu. Reload cần `X-Admin-Token` khớp `ADMIN_API_TOKEN` backend.

Flutter tự gửi token, kiểm tra phiên ở Splash và quay về Login khi phiên hết hạn. Secret Supabase/database không đưa vào app:

```powershell
cd mobile_app
flutter pub get
flutter run
# Máy thật/tunnel: flutter run --dart-define=API_URL=https://your-host.example
```

Flutter dùng `lib/config/app_config.dart`, không đọc `.env`. Player mô phỏng giữ heartbeat, resume và kiểm tra lưu thất bại. Onboarding rerank ở ứng dụng là luồng bổ sung theo thể loại người dùng chọn, không được trình bày như kết quả offline MovieLens không có nhãn onboarding.

### Chạy trên điện thoại Android thật qua Ngrok

Giữ hai terminal chạy API và `ngrok http 8000`. Từ gốc repo, chạy:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_mobile.ps1
# Chỉ kiểm tra đường hầm và PostgreSQL:
powershell -ExecutionPolicy Bypass -File scripts/run_mobile.ps1 -CheckOnly
# Chọn thiết bị cụ thể (xem ID bằng flutter devices):
powershell -ExecutionPolicy Bypass -File scripts/run_mobile.ps1 -DeviceId <device-id>
```

Script đọc URL HTTPS từ Ngrok local ở cổng 4040, kiểm tra API/database rồi chạy Flutter với `--dart-define=API_URL=...`. Sau khi cài, script đọc URL thực tế của ứng dụng debug trên điện thoại và tự xóa cache build, cài lại một lần nếu Flutter dùng cấu hình cũ. Không chạy lệnh Flutter khác cùng lúc với script vì chúng dùng chung cache build. Nếu Ngrok dùng cổng quản trị khác, truyền `-ApiUrl https://your-domain.ngrok-free.dev`. Khi URL Ngrok đổi, chạy lại script; hot reload không cập nhật biến biên dịch. `10.0.2.2` chỉ dùng cho máy ảo Android, `127.0.0.1` trên điện thoại là chính điện thoại. Không đưa URI PostgreSQL vào `API_URL`.

## Kiểm thử

```powershell
.venv-refactor/Scripts/python.exe -m pytest -q
# Tích hợp opt-in: chỉ tạo và xóa tài khoản fixture riêng trong PostgreSQL đã cấu hình.
$env:MOVIERS_RUN_DB_TESTS='1'
.venv-refactor/Scripts/python.exe -m pytest tests/test_postgres_integration.py -q
.venv-refactor/Scripts/python.exe -m src.pipeline.verify_runtime
cd mobile_app
flutter analyze
flutter test
flutter build web
```

Test thường dùng file tạm, không chọn database thật từ .env. Integration kiểm tra ownership, source priority, retry, transaction rollback, concurrency và pool. HTTP smoke chạy Uvicorn thật, kiểm tra SHA-256 đầu vào trước/sau. Chi tiết, số liệu và giới hạn thiết bị thật nằm trong biên bản nghiệm thu.

## Giới hạn học thuật

Checksum chứng minh toàn vẹn file, không chứng minh sở thích là chân lý. Mẫu user-cluster vẫn có thiên lệch tự chọn của MovieLens và thiếu exposure/demographic. Genre là snapshot hồi cứu; TMDB hiện tại không là feature lịch sử. Positive chưa quan sát không phải dislike. CI theo user có điều kiện trên sample/cutoff; ba seed không thay ba dataset độc lập. Kết quả offline không thay A/B test hoặc khảo sát người dùng.

Nguồn: [MovieLens 25M](https://files.grouplens.org/datasets/movielens/ml-25m-README.html), [Surprise SVD](https://surprise.readthedocs.io/en/stable/matrix_factorization.html), [sampled ranking metrics](https://research.google/pubs/on-sampled-metrics-for-item-recommendation/), [temporal leakage](https://arxiv.org/abs/2010.11060).
