# MovieRS — Báo cáo kỹ thuật và thực nghiệm

**Đề tài:** Hệ khuyến nghị phim cá nhân hóa kết hợp SVD, sở thích thể loại và độ phổ biến, có giải thích và đánh giá tái lập.

**Ngày kiểm chứng:** 15/10/2026.
**Phạm vi:** bản demo học thuật end-to-end FastAPI–Flutter; trình phát mô phỏng.

Thông tin sinh viên, cơ sở thực tập và kết quả chưa có bằng chứng không được tự điền. Báo cáo này thay thế các bảng điểm minh họa và kết luận vượt quá bằng chứng của bản trước.

## 1. Dự án nghiên cứu vấn đề gì?

Một ứng dụng phim cần chọn một danh sách ngắn từ danh mục lớn cho từng người dùng. Đề tài gồm hai bài toán liên quan nhưng khác nhau:

- **Dự đoán rating:** dự đoán số sao cho một cặp user–movie đã có nhãn trong tập đánh giá; đo RMSE/MAE.
- **Khuyến nghị Top-K:** xếp phim chưa tương tác trong danh mục có thể phục vụ, rồi kiểm tra mức trùng với những phim người dùng thích ở tương lai; đo Precision, Recall, NDCG và các thuộc tính đa dạng/độ phủ.

RMSE giảm không bảo đảm Top-K tăng. Người dùng chưa có lịch sử cũng không thể có biểu diễn cá nhân được học chỉ từ SVD. Theo mô tả chính thức của Surprise, phần bias và vector user chưa biết được coi bằng 0; cần một chiến lược ngoài SVD cho khởi đầu. [Tài liệu SVD](https://surprise.readthedocs.io/en/stable/matrix_factorization.html).

Các câu hỏi thực nghiệm:

1. SVD dự đoán rating có tốt hơn global mean và Bayesian popularity trên cùng cách chia dữ liệu không?
2. Kết quả khác nhau thế nào giữa cold-user thực sự (0 rating TRAIN), ít lịch sử (1–4), warm (5–20) và heavy (>20)?
3. Điểm dự đoán tốt có dẫn đến xếp hạng tốt trên toàn bộ ứng viên chưa tương tác không?
4. Kết hợp thể loại và MMR thay đổi độ liên quan, độ phủ và đa dạng như thế nào?

## 2. Khảo sát hiện trạng trước khi sửa

| Phát hiện từ mã và artifacts | Ảnh hưởng | Thay đổi đã thực hiện |
|---|---|---|
| README và dashboard có bảng điểm ghi cứng, không truy về run | Không đủ bằng chứng học thuật | Dashboard chỉ đọc JSON thực nghiệm; lưu hash, tham số, seed, môi trường |
| Top-K chỉ sắp các rating có trong TEST | Không kiểm tra cạnh tranh với phim chưa quan sát | Chấm toàn bộ phim TRAIN chưa tương tác rồi đối chiếu positive TEST |
| Recall user không có positive được đặt 1 | Làm đẹp chỉ số không có cơ sở | User cần ít nhất một positive có thể phục vụ; công bố điều kiện và mẫu |
| TRAIN vận hành có feedback năm 2026; holdout lịch sử đến 2019 | Không còn split thời gian thuần | Thực nghiệm dựng split từ processed gốc; runtime dùng luồng riêng |
| Popularity chỉ giữ 20 phim rồi lọc thể loại/đã xem | Thiếu kết quả, sở thích có thể không xuất hiện trong pool | Giữ toàn bộ bảng xếp hạng và rerank toàn bộ ứng viên |
| “Phim phổ biến” trên app đọc đầu `/movies` | Nhãn UI không đúng dữ liệu | Endpoint `/movies/popular` dùng Bayesian popularity |
| Watch/favorite ghi đè sao chủ động; xem xong hiển thị như 5 sao của user | Sai nghĩa nhãn và lịch sử | Nguồn có ưu tiên; lịch sử sao chỉ hiển thị explicit |
| Cache phụ thuộc kích thước request đầu và không xóa khi đổi genres | Kết quả thiếu hoặc lỗi thời | Cache top 50 theo user/chế độ; xóa khi sở thích/feedback đổi |
| Client nuốt lỗi mạng thành danh sách rỗng, rating luôn báo thành công | Khó phân biệt lỗi và không có dữ liệu | Timeout, trạng thái lỗi/thử lại; báo thành công sau xác nhận server |
| Metadata gate cũ chỉ ghi một số RMSE | Có thể so sánh khác tập | Chấm lại incumbent/candidate trên cùng validation, lưu fingerprint |

Khảo sát local cho thấy 2.000.000 rating processed, 157.068 user, 13.163 phim có rating, 62.316 phim trong danh mục; độ thưa trên tập phim có rating khoảng **99,9033%**. Hai số lượng phim có ý nghĩa khác nhau. TRAIN vận hành có 1.600.061 dòng tại thời điểm khảo sát, không được dùng thay thế TRAIN nghiên cứu 1.600.000 dòng.

## 3. Kiến trúc và phương pháp

### 3.1. Dữ liệu

MovieLens 25M là dataset đánh giá phim do GroupLens công bố. Checkout hiện tại dùng một mẫu 2M đã tiền xử lý từ bộ lớn, không phải ml-latest-small. TMDb bổ sung mô tả, poster và thời lượng, không cung cấp video. [Nguồn dataset](https://grouplens.org/datasets/movielens/25m/).

`src/data/protocol.py` kiểm tra ID, rating, timestamp, null và trùng cặp user–movie. Dữ liệu được sắp theo timestamp, userId, movieId; cùng timestamp không bị chia qua ranh giới. Ba split nghiên cứu chỉ hình thành từ `ratings_processed.csv`; không nhập log ứng dụng.

| Split | Rating | User | Phim | Khoảng thời gian UTC |
|---|---:|---:|---:|---|
| TRAIN | 1.600.000 | 132.272 | 12.100 | 1996-01-29 → 2016-05-28 |
| VAL | 200.000 | 16.668 | 9.637 | 2016-05-28 → 2017-12-12 |
| TEST | 200.000 | 17.020 | 10.034 | 2017-12-12 → 2019-11-21 |

Hash chính xác và timestamp đầy đủ nằm trong artifact; không dùng tên file để suy ra hai lần chạy cùng dữ liệu.

### 3.2. Dự đoán và xếp hạng

SVD có bias dự đoán `r̂_ui = μ + b_u + b_i + p_uᵀq_i`, tối ưu sai số bình phương có regularization bằng SGD. Đây là biased matrix factorization cho ma trận rating thiếu dữ liệu, không phải lấy SVD đầy đủ của một ma trận điền 0. Bản NumPy tự viết vẫn ở `src/models/svd_numpy.py` để nghiên cứu thuật toán; không có kết quả đo mới của nó trong bảng benchmark này.

Bayesian popularity dùng `(vR + 5C)/(v+5)`, với `v` là số rating phim trong TRAIN, `R` là trung bình phim, `C` là trung bình toàn TRAIN. User mới dùng mô hình này; user đã có vector dùng SVD. Điểm được clip về [0,5;5], chuẩn hóa về [0;1] để phối hợp với độ phù hợp thể loại.

Hồ sơ thể loại chỉ lấy lựa chọn người dùng và các rating lịch sử >=3,5. Trọng số mỗi rating dương là `rating−3`; onboarding có trọng số 2 mỗi thể loại. Affinity là trung bình trọng số các thể loại phim, chia cho trọng số thể loại cao nhất. `score=(1−α)*normalized_rating + α*affinity`, `α=0,2` là giá trị thiết kế trong tập cấu hình kiểm tra, không được tuyên bố tối ưu toàn cục.

MMR xếp lại pool 200 phim có score cao nhất bằng `(1−d)*score−d*max Jaccard` giữa thể loại ứng viên và các phim đã chọn. Toàn bộ catalog TRAIN được chấm trước khi lấy pool. `d=0` là mặc định; `d=0,1` là tùy chọn khám phá. MMR gốc xuất phát từ truy hồi thông tin; dự án sử dụng ý tưởng giảm trùng lặp với độ giống thể loại, không tuyên bố tái lập toàn bộ nghiên cứu gốc. [Carbonell & Goldstein, 1998](https://www.cs.cmu.edu/afs/cs/Web/People/jgc/publication/MMR_DiversityBased_Reranking_SIGIR_1998.pdf).

Lý do gợi ý mô tả nguồn thực tế: điểm SVD, điểm cộng đồng hoặc trùng thể loại quan tâm. Đây là giải thích theo thành phần xếp hạng, chưa phải giải thích nhân quả hoặc giải mã ý nghĩa từng yếu tố ẩn. Điểm dự đoán không phải xác suất hài lòng.

### 3.3. Phản hồi và vận hành

| Source | Nội dung | Mức ưu tiên | Có hiển thị trong lịch sử sao? |
|---|---|---:|---|
| explicit | 0,5–5 sao user chủ động nhập | 3 | Có |
| legacy_unknown | Bản ghi cũ thiếu nguồn, giữ nguyên giá trị | 3 | Không tự gán là explicit |
| favorite | Lưu yêu thích, proxy 4,5 | 2 | Không |
| watch_complete | Hoàn thành mô phỏng >=95%, proxy 4,0 | 1 | Không |

Bỏ lưu phim rút tín hiệu favorite hiện tại, không tự biến thành đánh giá xấu. Xem dở không được suy thành không thích. Một user–movie giữ một phản hồi hiệu lực có ưu tiên cao nhất; đây chưa phải event log giữ mọi sự kiện. Ghi atomic và khóa trong một tiến trình; không tuyên bố an toàn ghi đa worker/máy.

Surprise làm việc với explicit ratings; proxy hành vi trong dự án là quy tắc heuristic bổ sung cho demo, không phải mô hình implicit feedback có confidence weighting. [Giới hạn chính thức của Surprise](https://surpriselib.com/).

Phản hồi mới có thể cập nhật một bước SGD trên vector user trong RAM, không cập nhật vector item. Bước này là điều chỉnh gần đúng, mất khi restart và không thay cho retrain. Sau restart, hồ sơ thể loại vẫn dựng từ log đã lưu; lần retrain tiếp theo học lại phản hồi. Khử trùng cùng source/rating tránh heartbeat hoặc retry áp dụng lại cùng một bước SGD.

Reload dựng snapshot mới trong khóa rồi thay trạng thái; lỗi tải giữ snapshot cũ. Có thể có thời gian request chờ khi reload, nên không khẳng định đã chứng minh zero-downtime. Gate vận hành đọc holdout lịch sử cố định, chấm cả hai model trên cùng tập và từ chối giá trị không hữu hạn. Đây là kiểm tra hồi quy vận hành, không phải test độc lập để công bố chất lượng nghiên cứu.

## 4. Giao thức thực nghiệm

- Chạy `python src/models/train_pipeline.py --seeds 42 43 44 --ranking-users 200` từ gốc repo.
- SVD: 50 factors, 20 epochs, learning rate 0,005, regularization 0,05; cùng TRAIN ở tất cả seed.
- Cấu hình so sánh định trước trong runner: SVD; hybrid α=0,2; hybrid α=0,2 và MMR d=0,1. Chọn cấu hình xếp hạng bằng NDCG VAL, sau đó báo cáo TEST của các biến thể. Sự thay đổi predictor cold-user giữa SVD và hybrid là một thành phần của phương pháp, nên không quy toàn bộ chênh lệch cho thể loại.
- RMSE/MAE đánh giá toàn bộ split. Nhóm user dựa duy nhất vào số rating TRAIN; cold=0 và sparse=1–4 được phân biệt.
- Ranking có relevance nhị phân `rating>=3,5`. Ứng viên là toàn bộ phim TRAIN chưa có trong lịch sử trước thời điểm đánh giá. Khi đánh giá TEST, loại cả các phim đã tương tác ở VAL. Phim TEST chưa có trong TRAIN không được ép thêm vào ứng viên chỉ vì đã biết nhãn.
- User cần ít nhất một positive có thể phục vụ. Lấy cùng mẫu 200 user từ 15.623 user đủ điều kiện bằng RNG seed 42. Không lấy mẫu negative items. Khuyến cáo tránh metrics dựa trên lấy mẫu phim được nêu trong nghiên cứu của Krichene & Rendle. [KDD 2020](https://research.google/pubs/on-sampled-metrics-for-item-recommendation/).
- Precision là số hit/K; Recall là số hit/số positive có thể phục vụ; NDCG dùng gain nhị phân. Không có positive thì không gán Recall=1. Recall báo cáo là **conditional on servable catalog**: 11,835% positive TEST chưa có trong catalog TRAIN được công bố riêng, không tính là đã giải quyết cold-item.
- Coverage là số phim xuất hiện trong danh sách của mẫu user chia 12.100 phim TRAIN. Diversity là trung bình khoảng cách Jaccard thể loại từng cặp trong danh sách. Novelty là `−log2(count_item/total_train_ratings)`, đo ít phổ biến chứ không đo hài lòng.
- CI95 dùng 1.000 bootstrap theo user của mẫu cố định, không phải khoảng tin cậy cho toàn bộ quần thể hay chênh lệch ghép cặp. Độ lệch chuẩn qua ba seed là bất định huấn luyện, không phải nhiều mẫu user độc lập.

## 5. Kết quả và diễn giải

Kết quả trung bình qua seed, nguồn [JSON](experiments/latest.json) và [CSV](experiments/summary.csv). Mean và popularity không có ngẫu nhiên huấn luyện nên chỉ chạy một lần.

| Mô hình | RMSE ↓ | MAE ↓ | Precision@10 ↑ | Recall@10 ↑ | NDCG@10 ↑ | Coverage | Diversity |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mean | 1,060273 | 0,829415 | 0,00250 | 0,001485 | 0,005370 | 0,0909% | 0,826134 |
| Bayesian popularity | 0,996153 | 0,764583 | 0,01350 | 0,016858 | 0,021515 | 0,0992% | 0,660944 |
| SVD | 0,987929 | 0,755787 | 0,00050 | 0,000164 | 0,000358 | 0,4904% | 0,582490 |
| Hybrid SVD + thể loại + popularity khi cold | 0,990604 | 0,759782 | 0,01350 | 0,016858 | 0,021515 | 0,6777% | 0,596236 |
| Hybrid + MMR | 0,990604 | 0,759782 | 0,01050 | 0,016801 | 0,017673 | 0,8099% | 0,847519 |

176.535/200.000 rating TEST thuộc user có **0 rating TRAIN** (88,2675%). Trong mẫu ranking có 176 user cold và chỉ 24 user đã biết. SVD có RMSE thấp nhất trong các mô hình đo, nhưng Top-K yếu. Hybrid khôi phục Top-K nhờ fallback, **chưa vượt popularity về NDCG/Recall trên mẫu này**. Mọi hit của hybrid không MMR trong mẫu seed 42 đến từ nhóm cold; nhóm đã biết có 0 hit, nên chưa có bằng chứng cá nhân hóa ranking tốt cho nhóm này.

Ví dụ nhóm RMSE của SVD seed 42: cold=1,001025; sparse=0,962093; warm=0,954614; heavy=0,839715. Đây là khác biệt giữa các nhóm trên cùng run, không chứng minh quan hệ nhân quả vì độ khó/phân phối giữa nhóm khác nhau.

MMR tăng Diversity từ khoảng 0,596 lên 0,848, đồng thời giảm NDCG TEST từ 0,021515 xuống 0,017673. Trên VAL, hybrid không MMR có NDCG≈0,023838 so với MMR≈0,016232; lựa chọn mặc định tắt MMR dựa trên VAL. Người dùng có thể chủ động khám phá để đánh đổi. Không khẳng định một biến thể tốt nhất trên mọi tiêu chí.

## 6. Luồng ứng dụng đã hoàn thiện

1. Đăng ký và chọn thể loại, hoặc đăng nhập tài khoản đã có.
2. Home đọc profile server theo tài khoản, cho biết cơ sở gợi ý và số phim đã tương tác.
3. Mỗi gợi ý có lý do; danh sách cộng đồng dùng endpoint xếp hạng riêng.
4. Chi tiết phim đồng bộ trạng thái yêu thích/sao; chỉ báo đã lưu khi server xác nhận. Yêu thích dùng một request thay vì hai kênh dễ lệch nhau.
5. Player ghi rõ mô phỏng. Heartbeat được xếp hàng để phản hồi đến sau không ghi đè thứ tự trước. Khi thoát, chờ xác nhận lưu; lỗi cho phép thử lại.
6. Quay về Home và đổi tab sẽ làm mới dữ liệu cần thiết; sửa thể loại xóa cache server.
7. Gợi ý mặc định theo độ liên quan; switch khám phá bật MMR. Điểm TMDb bị thiếu được ghi thiếu, không tự thay bằng 7,0.

## 7. Giới hạn và hướng cải tiến ưu tiên

**Chất lượng ranking:** đây là điểm yếu còn lại có bằng chứng. Cần thử item-bias, popularity theo tần suất, BPR hoặc implicit ALS trên cùng giao thức; chọn siêu tham số bằng VAL, rồi dùng một cửa sổ thời gian mới chưa xem để kiểm tra. Không chọn mô hình bằng cách làm đẹp số TEST hiện tại.

**Dữ liệu:** bước preprocessing hiện tại đã lọc số rating phim/user trên toàn dataset trước temporal split. Dù giao thức mới không trộn feedback vào học thuật, chưa loại được thiên lệch do bộ lọc nhìn tần suất tương lai. Thực nghiệm chặt hơn cần dựng lại từ raw: chia thời gian trước, fit các điều kiện chọn catalog trên TRAIN, rồi áp dụng quy tắc phục vụ cho VAL/TEST.

**Khởi đầu và cold-item:** MovieLens không có lựa chọn onboarding của người dùng. Không được lấy thể loại từ positive TEST để giả lập onboarding. Tác dụng onboarding hiện được kiểm thử chức năng, chưa được đo bằng nghiên cứu người dùng độc lập. Catalog ứng viên chỉ chứa phim có trong TRAIN; khuyến nghị phim hoàn toàn mới cần thêm truy hồi nội dung riêng.

**Suy rộng:** 200 user ranking là mẫu nhỏ, đặc biệt chỉ 24 user đã biết. Cần tăng mẫu, báo cáo stratified user cohorts và nhiều cửa sổ thời gian. Coverage phụ thuộc kích thước mẫu; không so với số của protocol khác. Chưa có kiểm định chênh lệch ghép cặp hay A/B test; không khẳng định tăng giữ chân/hài lòng.

**Vận hành:** hệ thống file-backed và khóa trong tiến trình phù hợp demo một worker; chưa có transactional database, durable event log hoặc job queue. SHA-256+salt và xác thực bằng user ID là prototype, chưa đáp ứng triển khai công khai. Trước production cần token phiên, phân quyền endpoint quản trị, password KDF, giới hạn tốc độ và retrain worker độc lập.

**Mô phỏng:** kéo tiến độ không chứng minh đã xem phim. Các proxy không được đưa vào benchmark MovieLens hoặc xem là nhãn thực. Không cần API/video thật để chứng minh vòng gợi ý–tương tác–cập nhật.

## 8. Bằng chứng và tái lập

Kiểm chứng chức năng: [VERIFICATION.md](VERIFICATION.md). Giao thức và artifact: [experiments/README.md](experiments/README.md). Hướng chạy: [README gốc](../README.md). Không thay model đang phục vụ bằng model nghiên cứu và không sửa dữ liệu runtime thật trong quá trình kiểm thử.
