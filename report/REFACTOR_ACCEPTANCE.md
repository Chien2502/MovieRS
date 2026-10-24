# Nghiệm thu MovieRS V2

Ngày: 16/10/2026. Phạm vi: P1–P7 của [kế hoạch](REFACTOR_PLAN.md). Không áp dụng Dely, player giữ mô phỏng. Các giới hạn nghiên cứu/thiết bị bên dưới là giới hạn phạm vi, không được diễn giải thành kiểm thử đã thực hiện.

## 1. Đối chiếu yêu cầu và bằng chứng

| Pha | Kết quả triển khai | Bằng chứng kiểm chứng |
|---|---|---|
| P1: nền tảng | TOML/Pydantic từ chối config sai; pyproject/lock; model capability và save/load; source archive/manifest/environment | `configs/research.toml`, `src/experiments/`, `src/models/interfaces.py`; fixture config/serialization; clean venv install và pip check |
| P2: dữ liệu | Quét toàn nguồn theo chunk; SHA256 user sample giữ lịch sử; Parquet canonical; split UTC; quality/data card/checksum | `src/data/snapshots.py`; `tests/test_refactor_pipeline.py`; snapshot 0bf8337c28f8baeb49a9; [quality](experiments/v2/quality.json), [data card](experiments/v2/data_card.md) |
| P3: evaluation | Full-catalog, positive ngoài catalog ở mẫu số chính; cohort, seed averaging, paired bootstrap; TRAIN→VAL→freeze→refit→TEST | `src/evaluation/`; fixture metric/tie/out-of-catalog; thay toàn nhãn TEST không đổi selection; per-user Parquet và [comparisons](experiments/v2/comparisons.json) |
| P4: model/runner | 12 family/ablation; VAL chọn thật; 3 seed SVD; sparse KNN; resource budget, process-tree watchdog, checkpoint checksum/resume | `src/models/research.py`, `src/experiments/runner.py`, `resources.py`; full research hai lượt; tests timeout không hợp tác/launcher Windows/checkpoint hỏng |
| P5: dashboard | 7 trang; checksum/compatibility trước delta; cohort, K phụ, CI, CSV; Pareto liên quan–đa dạng; model size, latency và danh sách giải thích | `dashboard/pages/research.py`, `dashboard/services/`; AppTest 7 trang; giải thích chỉ hiện khi payload tái tạo đúng danh sách lưu; fixture checksum/ranking |
| P6: database/auth | Một storage được chỉ định; schema/version/FK/RLS/private grants; Argon2id/session/ownership; feedback transaction, idempotency và concurrency | `api/repositories/postgres.py`, `api/security.py`, `api/idempotency.py`, `supabase/migrations/`; PostgreSQL integration trên database thật |
| P6: migration/rollback | Backup/import idempotent, cách ly orphan; đối soát ID/giá trị/timezone; export có checksum, đọc bằng adapter file; rollback model thật trên con trỏ tạm | [runtime reconciliation](refactor/runtime_reconciliation.json); `src/data/migrate_runtime.py`, `src/pipeline/worker.py`; không đổi file nguồn/live serving pointer |
| P6: ứng dụng | Token Flutter, expired session về Login; lỗi không thành danh sách rỗng/thành công giả; favorites một request, player resume/save failure; worker ngoài API | `mobile_app/test/recommendation_flow_test.dart`; HTTP smoke; serving gate/rollback tests |
| P7: bàn giao | Báo cáo viết lại bằng kết quả V2; README/AGENTS/schema docs; evidence bundle và lệnh nghiệm thu | [báo cáo](Bao_Cao_Thuc_Tap_MovieRS.md), [verification](refactor/verification_v2.json), [evidence manifest](experiments/v2/evidence_manifest.json) |

Module mới giữ wrapper nghiên cứu V1 để đối chiếu; không xóa dữ liệu/model cũ. Các adapter file nằm trong service/facade hiện có, được chọn bằng cùng storage boundary; không bật dual-write. Run được lộ dần qua manifest/checkpoint ghi atomic từng file, dashboard chỉ chấp nhận `complete` và checksum hợp lệ. Thư mục run failed/running không bị coi như kết quả hoàn tất; không nhất thiết rename cả thư mục trên Windows.

## 2. Kiểm thử cuối

Lệnh từ gốc repo:

```powershell
.venv-refactor/Scripts/python.exe scripts/verify_refactor.py --database --flutter
```

Biên bản JSON là nguồn có thẩm quyền cho số lượng test, exit code, timeout, thời gian và hash phiên bản code. Nó chạy:

- Python unit/protocol/regression trên file tạm; database tests được skip ở lượt này và chạy opt-in riêng.
- PostgreSQL thật: ownership, ưu tiên nguồn, favorite/watch transaction rollback, ghi đồng thời, DB failure không fallback, pool rollback, statement timeout, replay cũ không đảo feedback/favorite/progress và rollback cả ledger.
- HTTP Uvicorn thật: 8 route đọc thành công, thiếu token trả 401 và reload thiếu admin trả 403; SHA-256 CSV/JSON/model trước/sau không đổi.
- Compile Python, AppTest toàn bộ 7 trang dashboard.
- Flutter analyze, widget/service tests, build web; pip check trong venv sạch.

Lượt nghiệm thu cuối đạt **66 unit/protocol + 9 PostgreSQL integration + 9 Flutter**, analyze không có issue, build web thành công và 7 trang dashboard không có exception. Có thêm kiểm tra 20 danh sách thực của hai model tái tạo đúng từ payload khóa, xem [receipt giải thích](refactor/dashboard_explanations.json). Không cộng các lượt chạy lại thành số test riêng. Một lượt kiểm tra trước đó chờ database quá lâu; biên bản lỗi được giữ, sau đó bổ sung giới hạn truy vấn/lock, TCP keepalive và deadline cho chính harness để lỗi kết thúc có biên bản thay vì treo vô hạn.

## 3. Kết quả nghiên cứu có thể truy vết

- Snapshot research: 8.000 user, **1.237.592 rating** từ toàn ML-25M; TRAIN/VAL/TEST **990.073 / 123.759 / 123.760**. Raw 25.000.095 rating được audit; không upload toàn bộ vào Supabase.
- Run chính `run_20261015T235317064101Z`, 900 user ranking, 12 family; cấu hình SVD 32/15/0,02, hybrid tau20/beta0,75, MMR0 do VAL chọn.
- MostPopular NDCG@10 **0,280358**; AdaptiveHybrid **0,118589**. Delta **-0,161770**, CI95 **[-0,175655; -0,147796]**. Có bằng chứng hybrid kém baseline chính trong giao thức này; không báo “cải tiến” giả.
- Hybrid vượt SVD thuần nhưng chưa chứng minh lợi ích ngoài shared cold fallback; genre chưa có bằng chứng cải thiện. Lợi ích nhỏ so fixed hybrid chỉ là thăm dò chưa hiệu chỉnh đa kiểm định.
- Run chính khoảng **611,8 giây / 940,2 MiB peak RSS nội bộ**, đạt budget 120 phút/2 GiB. Run trước có số đo watchdog ngoài **925,94 MiB**; hai run giống toàn metric family/split/user/delta. Bản sửa process-tree watchdog được kiểm chứng riêng, không thêm số đo chưa quan sát vào run cũ.
- [Profile payload](experiments/v2/profile.json) đo riêng theo selection đã khóa, không chọn lại trên TEST. Model serving chọn MostPopular từ VAL; onboarding app được ghi riêng khỏi benchmark.

Run chính lưu code archive đúng phiên bản đã tính số liệu. Các bản sửa timeout/idempotency/checkpoint/UI sau benchmark có hash riêng ở biên bản kiểm thử; không sửa manifest hay metric của run để làm chúng có vẻ đến từ code mới. Pipeline fixture chạy trên code hiện tại; muốn resume run cũ phải dùng đúng code/config/data đã ghi.

## 4. Database và dữ liệu ứng dụng

Đối soát thực tế: **7 accounts, 62.423 movies, 41 feedback, 13 favorites, 20 watch progress**. Một favorite orphan ở file cũ được cách ly trong backup; file nguồn vẫn nguyên. Chạy lại import không tăng số dòng và không sửa thêm timestamp. Legacy naive timestamps dùng Asia/Ho_Chi_Minh, aware timestamps giữ offset. PostgreSQL tính ratio chính xác từ position/duration; CSV cũ làm tròn 4 chữ số, đối soát cho phép sai số tối đa 0,00005 ở ratio, trạng thái/vị trí/thời lượng phải khớp.

Export rollback được kiểm tra checksum, đọc accounts/feedback/progress qua adapter file trong tiến trình diễn tập; không đổi `.env` hay nguồn ghi của API đang chạy. Sessions không export nên sau rollback cần đăng nhập lại. Model rollback dùng hai bundle thực tế và pointer tạm; live pointer không đổi. Tài khoản integration tạm được xóa, kiểm kê còn 0.

Security advisor Supabase sau migration không có WARN/ERROR; có 8 INFO `rls_enabled_no_policy` đúng thiết kế schema backend riêng, không cấp quyền client. Không gọi đây là bảo đảm an toàn tuyệt đối: SQL owner bypass RLS, API ownership là ranh giới xác thực. [Giải thích advisory](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy).

## 5. Chạy lại và demo

```powershell
# Chuẩn bị snapshot; không cần TMDB/video API cho nghiên cứu.
python -m src.experiments prepare --profile research
python -m src.experiments run --profile research
streamlit run dashboard/app.py
# API đọc .env backend đã chọn PostgreSQL và serving pointer.
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Mở dashboard → provenance → representativeness → comparisons → ablations → examples → operations. Nhấn kiểm tra API để lấy tình trạng database/model và latency health probe; không nhầm latency này với inference model. Worker thủ công theo README; TEST không kích hoạt deployment. Mobile dùng `AppConfig`/`--dart-define`, không đọc `.env`.

## 6. Giới hạn được giữ rõ

Đây là demo học thuật có kiểm thử tự động và database thật, chưa có A/B test hoặc khảo sát người dùng. Chưa chạy trên thiết bị Android/iOS vật lý. Player vẫn mô phỏng; thời lượng mặc định không phải metadata đã xác minh. File adapter không bảo đảm transaction xuyên nhiều file như PostgreSQL. Payload giải thích thiếu/hỏng hoặc không tái tạo ranking thì UI không bịa điểm. Cold-user đông, exposure/demographic thiếu, genre hồi cứu và CI phụ thuộc snapshot/cutoff giới hạn suy luận. BPR/ALS, nhiều cửa sổ xác nhận và đo tác động thực tế là hướng nghiên cứu tiếp theo, không thuộc kết quả đã thực hiện.
