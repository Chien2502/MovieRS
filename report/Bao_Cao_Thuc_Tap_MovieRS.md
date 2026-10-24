# MovieRS V2 — Báo cáo kỹ thuật và thực nghiệm

**Đề tài:** Đánh giá hệ khuyến nghị phim lai theo mức độ lịch sử người dùng trên mẫu MovieLens 25M, dưới giới hạn tài nguyên máy cá nhân.

Ngày kiểm chứng: 16/10/2026. Phạm vi: nghiên cứu offline và ứng dụng FastAPI–Flutter có PostgreSQL; trình phát mô phỏng. Thông tin sinh viên/cơ sở thực tập chưa cung cấp không được tự điền. Báo cáo V1 lưu riêng tại [bản lịch sử](Bao_Cao_Thuc_Tap_MovieRS_V1.md); không tính phần trăm cải tiến giữa hai giao thức.

## 1. Câu hỏi nghiên cứu

1. SVD tối ưu dự đoán rating có xếp hạng tốt hơn baseline đơn giản không?
2. Hybrid thích ứng theo độ dài lịch sử có thêm giá trị ngoài fallback cold-start không?
3. Thể loại và MMR thay đổi độ liên quan, đa dạng và chi phí thế nào?
4. Kết luận còn đúng ở những nhóm người dùng nào, với mức bất định nào?

Đóng góp chính là quy trình tái lập, khả năng đối chứng và công bố kết quả âm. Hybrid là giả thuyết được kiểm tra, không phải kết luận mặc định. Rating prediction và Top-K là hai tác vụ riêng; ranking score không phải xác suất thích hoặc số sao dự đoán.

## 2. Dữ liệu và mức độ tin cậy

Nguồn ML-25M chứa 25.000.095 rating, 162.541 user, 59.047 phim có rating và 62.423 phim trong catalog. Quét toàn bộ nguồn không phát hiện null trong cột bắt buộc, ID sai, rating ngoài miền/bước 0,5, cặp user–movie trùng hoặc movie ID không có catalog. MD5 ZIP khớp GroupLens, SHA-256 của CSV được lưu trong manifest. [Mô tả nguồn](https://files.grouplens.org/datasets/movielens/ml-25m-README.html).

Với mỗi ID trong toàn bộ quần thể, tính SHA-256 của chuỗi `20261015:<userId>`, sắp digest tăng và lấy 8.000 user đầu; giữ toàn bộ lịch sử của họ. Không chọn rating độc lập, user đầu file hoặc chỉ phim phổ biến. Mẫu có **1.237.592 rating, 27.498 phim được chấm**, trung vị 71 rating/user. TV distance phân phối số sao so với nguồn là 0,002337. Dashboard còn so sánh năm, mức hoạt động, thể loại và long-tail với mẫu số tách biệt. Chỉ số tương đồng không phải chứng chỉ đại diện mọi khán giả.

Snapshot `0bf8337c28f8baeb49a9` lưu Parquet, user IDs, data card, quality và checksum bất biến. Profile smoke/dev/research/extended lần lượt 1.000/4.000/8.000/12.000 user, cùng thứ tự lấy mẫu và cutoff. Không áp dụng bộ lọc phim tối thiểu 50 rating cho benchmark chính.

Checksum chứng minh toàn vẹn file, không chứng minh mọi rating là sở thích khách quan. ML-25M có thiên lệch tự chọn và điều kiện tối thiểu 20 rating/user; không có exposure hay nhân khẩu học. Timestamp là lúc rating, không khẳng định lúc xem. Genre là snapshot hồi cứu; metadata TMDb hiện tại phục vụ UI, không dùng làm feature lịch sử trong benchmark.

## 3. Giao thức đã khóa

| Split | Khoảng thời gian UTC | Rating |
|---|---|---:|
| TRAIN | trước 2016-07-25T17:31:14Z | 990.073 |
| VAL | từ T1 đến trước 2018-01-23T19:51:49Z | 123.759 |
| TEST | từ T2 | 123.760 |

Sắp timestamp/user/movie; timestamp bằng nhau ở cùng phía cutoff. Fit TRAIN và chọn cấu hình trên VAL; ghi bền vững `selection.json` trước khi đọc TEST. Refit TRAIN+VAL để đánh giá cửa sổ TEST tĩnh. Feature, popularity và profile không cập nhật bằng nhãn trong cửa sổ được chấm. Chia thời gian toàn cục tránh tương tác tương lai của user khác lọt vào training. [Ji và cộng sự](https://arxiv.org/abs/2010.11060).

Positive là rating ≥3,5; metric chính macro NDCG@10. Chấm toàn catalog đã biết khi fit, trừ lịch sử trước cutoff, không lấy mẫu âm tính. [Krichene và Rendle](https://research.google/pubs/on-sampled-metrics-for-item-recommendation/). Positive ngoài catalog vẫn nằm trong mẫu số chính; user có toàn positive ngoài catalog nhận 0. Bảng conditional-on-servable báo riêng. User không có positive không thuộc mẫu ranking, có đếm loại trừ.

TEST có 903 user xuất hiện, **900 user đủ điều kiện ranking**; 342 known/561 cold trong toàn TEST, khoảng 75,29% rating TEST thuộc cold user. Catalog sau refit có 22.821 phim, khoảng 7,30% positive ngoài catalog. Cohort dựa trên số rating trước cutoff: cold=0, sparse=1–4, warm=5–19, heavy≥20.

Seed huấn luyện 42/43/44 cho mô hình ngẫu nhiên. Trung bình metric theo user qua seed rồi bootstrap ghép cặp user 2.000 lần để tính CI95 của delta. Baseline chính là model có NDCG VAL cao nhất, được chọn trước TEST. CI có điều kiện trên snapshot/cutoff; seed huấn luyện không tạo ra ba dataset độc lập. Phân tích ablation là thăm dò, chưa hiệu chỉnh đa kiểm định.

Nguồn ML-25M đã được khảo sát trong V1; V2 không được mô tả là thử nghiệm mù trên nguồn chưa từng xem. Sau khi thấy TEST, không chỉnh tham số để hybrid thắng. Mở rộng giả thuyết cần giao thức và holdout xác nhận mới.

## 4. Mô hình và cấu hình

GlobalMean, regularized user/item bias, MostPopular theo số rating, Bayesian item mean, genre content, ItemKNN sparse, BiasedSVD, adaptive hybrid và MMR dùng cùng evaluator. Thêm fixed hybrid, không genre và SVD dùng chung fallback để tách đóng góp.

BiasedSVD dùng Surprise, factorization có bias học bằng SGD, không phải phép SVD đại số trực tiếp. [Tài liệu implementation](https://surprise.readthedocs.io/en/stable/matrix_factorization.html). VAL chọn 32 factors, 15 epochs, regularization 0,02; ItemKNN giữ 50 hàng xóm, shrinkage 10. Hybrid có tau=20, beta=0,75; trọng số cá nhân hóa thay đổi theo lịch sử, cold user dùng Bayesian fallback. MMR được VAL chọn trọng số **0**: không đủ lợi ích liên quan để bật mặc định. Bảng thử MMR vẫn được công bố để thấy đánh đổi đa dạng.

## 5. Kết quả benchmark

Run chính: `run_20261015T235317064101Z`. [Bảng máy đọc được](experiments/v2/summary.csv), [paired comparison](experiments/v2/comparisons.json), [CI từng mô hình](experiments/v2/intervals.json).

| Mô hình | NDCG@10 | RMSE nếu hỗ trợ rating |
|---|---:|---:|
| MostPopular | 0,280358 | N/A |
| SparseItemKNN | 0,157700 | N/A |
| RegularizedBias | 0,146360 | 0,963670 |
| SVDSharedFallback | 0,121020 | N/A |
| AdaptiveWithoutGenre | 0,120240 | N/A |
| BayesianItemMean | 0,118847 | 0,985963 |
| AdaptiveHybrid | 0,118589 | N/A |
| AdaptiveMMR | 0,118589 | N/A |
| FixedHybrid | 0,116170 | N/A |
| GenreContent | 0,107684 | N/A |
| GlobalMean | 0,054245 | 1,048255 |
| BiasedSVD | 0,027047 | 0,955751 |

So sánh chính AdaptiveHybrid − MostPopular: **ΔNDCG=-0,161770**, tương đối **-57,70%**, CI95 **[-0,175655; -0,147796]**, n=900. Có bằng chứng giảm chất lượng xếp hạng theo giao thức này. Không tuyên bố hybrid vượt baseline mạnh.

SVD có RMSE tốt nhất trong các mô hình rating được thử nhưng NDCG thấp. Kết quả phù hợp với sự khác biệt giữa tối ưu sai số sao và xếp hạng toàn catalog; không chứng minh SVD luôn kém trong mọi ngữ cảnh. Tỷ trọng cold user lớn cũng ảnh hưởng kết quả tổng thể, vì vậy dashboard cho xem cohort và mẫu số.

## 6. Phân tích đóng góp

| Đối chứng cho AdaptiveHybrid | Delta NDCG | CI95 | Diễn giải thăm dò |
|---|---:|---|---|
| BiasedSVD | +0,091542 | [0,082123; 0,100679] | Gain có thể chủ yếu từ fallback |
| SVDSharedFallback | -0,002432 | [-0,006068; 0,000926] | Chưa có bằng chứng thêm giá trị ngoài fallback |
| FixedHybrid | +0,002419 | [0,001075; 0,003877] | Lợi ích nhỏ của trọng số thích ứng; chưa hiệu chỉnh đa kiểm định |
| AdaptiveWithoutGenre | -0,001651 | [-0,005154; 0,001642] | Chưa có bằng chứng phần genre cải thiện |

Không lấy so sánh với SVD yếu làm bằng chứng hybrid vượt mọi model. MMR=0 làm AdaptiveMMR trùng AdaptiveHybrid ở TEST là kết quả selection thật. Coverage/diversity/novelty là proxy danh sách, không phải độ hài lòng người dùng.

## 7. Chi phí và tái lập

Run chính hoàn thành khoảng **611,8 giây**, peak RSS nội bộ quan sát **940,2 MiB**, dưới budget 2 GiB/120 phút. Run độc lập trước đó cho cùng metric của cả 12 family, split hash, user hash và delta chính; watchdog ngoài quan sát 925,94 MiB ở run trước. Không gán số đo watchdog ngoài của run trước cho run chính. Bản sửa sau đó kiểm thử theo dõi cả tiến trình con của launcher Windows và hard timeout.

Đo payload độc lập trên TRAIN+VAL bằng cùng cấu hình khóa: MostPopular 64.134 byte, ItemKNN khoảng 4,52 MB, SVD khoảng 14,78 MB và hybrid khoảng 16,08 MB ở seed 42. Joblib nén mức 3; kích thước không gồm cache evaluator. Thời gian fit riêng hybrid không bao gồm fit backbone dùng chung. [Profile chi tiết](experiments/v2/profile.json).

Môi trường Python 3.14.2 được cài lại trong `.venv-refactor`, dependency có lock và `pip check`. Manifest lưu source archive, environment/config/data hashes và per-user metrics. Research không đọc feedback runtime. [Bằng chứng tái lập](experiments/v2/reproducibility.json).

## 8. Kiến trúc ứng dụng

Luồng nghiên cứu: raw → audit → user sample → temporal snapshot → fit/select VAL → freeze/refit → TEST/statistics → artifacts → dashboard bảy trang. Dashboard kiểm tra checksum và compatibility trước tính delta; không huấn luyện khi mở trang.

Luồng vận hành: Flutter → FastAPI → PostgreSQL schema riêng. Accounts, sessions, feedback, favorites, watch progress và idempotency ledger được quản lý qua backend. Mật khẩu Argon2id, token có hạn và chỉ lưu digest, kiểm tra quyền sở hữu. Explicit ưu tiên hơn proxy; partial watch không thành dislike. Favorite/progress cùng feedback commit trong transaction; replay request cũ không đảo cập nhật mới. Database lỗi trả lỗi rõ ràng, không tự ghi CSV.

ML-25M/model giữ local. Worker thủ công ngoài API đánh giá candidate/incumbent trên cùng validation, kiểm tra ranking/cohort/latency và rating khi phù hợp, rồi promote pointer nguyên tử; có rollback. Model serving hiện chọn MostPopular từ VAL. Onboarding genre rerank của app là chức năng ứng dụng riêng, không được gọi là kết quả MovieLens offline.

Player mô phỏng, heartbeat/resume được giữ; không nối API video thật. Migration giữ nguyên nguồn, cách ly một favorite không có user, bổ sung catalog từ raw. Export/đối soát/rollback có bằng chứng ở [nghiệm thu](REFACTOR_ACCEPTANCE.md).

## 9. Kiểm chứng và giới hạn

[Biên bản kiểm thử](refactor/verification_v2.json) ghi lệnh, exit code, thời gian và source hashes; [biên bản nghiệm thu](REFACTOR_ACCEPTANCE.md) ánh xạ yêu cầu sang code/test/artifact. Có unit/protocol, tích hợp PostgreSQL thật, HTTP smoke bảo toàn dữ liệu, bảy trang dashboard, Flutter analyze/test/web build. Chưa kiểm tra trên thiết bị Android/iOS vật lý; kiểm thử widget và web không thay cho đánh giá người dùng thực tế.

Kết luận nghiên cứu chỉ áp dụng cho mẫu/cửa sổ đã nêu. Tương quan user và shared items có thể làm CI theo user chưa bao quát mọi bất định. Không có A/B test, nhãn exposure, nhân khẩu học hoặc nhãn onboarding lịch sử. Hướng tiếp theo là ranking objective và negative/exposure-aware learning, xác nhận trên cửa sổ mới; BPR/ALS là mở rộng tương lai, không được giả làm kết quả đã chạy.

Refactor đạt mục tiêu xây dựng quy trình có thể kiểm tra và vận hành nhất quán. Kết quả âm của hybrid là kết quả học thuật cần giữ, không phải lý do thay dữ liệu hoặc giao thức sau khi xem TEST.
