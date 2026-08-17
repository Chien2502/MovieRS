# BÁO CÁO THỰC TẬP THỰC TẾ

**Đề tài:** Tối ưu hóa Hệ thống Khuyến nghị Phim đa phương tiện: Ứng dụng SVD giải quyết bài toán dữ liệu thưa thớt và Triển khai tích hợp trên ứng dụng di động theo chuẩn MLOps  
**Sinh viên thực hiện:** Nguyễn Văn A  
**Mã sinh viên:** SE123456  
**Đơn vị thực tập:** FPT Software / FPT Corporation  
**Thời gian thực tập:** 14/07/2026 – 17/08/2026  

---

## CHƯƠNG 1: GIỚI THIỆU TỔNG QUAN

### 1.1. Bối cảnh đề tài
Trong kỷ nguyên kỹ thuật số, các nền tảng phát trực tuyến đa phương tiện (OTT/Streaming) như Netflix, FPT Play, Spotify đang đối mặt với bùng nổ thông tin. Người dùng có hàng chục nghìn lựa chọn nội dung, dẫn đến hiện tượng "quá tải thông tin" (Information Overload). Hệ thống gợi ý (Recommender System - RS) đóng vai trò trung tâm giúp cá nhân hóa nội dung, tăng thời lượng giữ chân người dùng (Retention Rate) và tối ưu hóa doanh thu.

### 1.2. Các bài toán cốt lõi cần giải quyết
1. **Bài toán Dữ liệu thưa thớt (Data Sparsity):** Tỷ lệ các cặp (User, Movie) có tương tác thực tế thường chiếm dưới 2% tổng ma trận tương tác (Sparsity > 98%).
2. **Bài toán Khởi động lạnh (Cold-Start Problem):** Người dùng mới đăng ký chưa có dữ liệu lịch sử đánh giá.
3. **Quy đổi phản hồi ngầm (Implicit Feedback Mapping):** Người dùng hiếm khi chủ động chấm điểm sao, cần chuyển đổi các hành vi xem phim, thả tim thành tín hiệu huấn luyện.
4. **Chu kỳ MLOps tự động:** Đảm bảo mô hình được tái huấn luyện (Retrain) liên tục khi nhận phản hồi mới mà không làm gián đoạn API Server (Zero-downtime Reload).

---

## CHƯƠNG 2: CƠ SỞ LÝ THUYẾT & THUẬT TOÁN

### 2.1. Lọc cộng tác (Collaborative Filtering)
Phương pháp dựa trên giả định rằng những người dùng có hành vi tương tự nhau trong quá khứ sẽ tiếp tục có sở thích giống nhau trong tương lai.

### 2.2. Phân rã ma trận với FunkSVD (Singular Value Decomposition)
Mô hình FunkSVD biểu diễn mỗi user $u$ bằng một vector latent factor $p_u \in \mathbb{R}^k$ và mỗi item $i$ bằng vector $q_i \in \mathbb{R}^k$. Điểm số dự đoán $\hat{r}_{u,i}$ được tính bằng:

$$\hat{r}_{u,i} = \mu + b_u + b_i + p_u^T q_i$$

Và hàm mất mát (Loss Function) có thành phần L2 Regularization:

$$\min_{p,q,b} \sum_{(u,i) \in R_{train}} \left( r_{u,i} - \hat{r}_{u,i} \right)^2 + \lambda \left( \|p_u\|^2 + \|q_i\|^2 + b_u^2 + b_i^2 \right)$$

### 2.3. Quy trình MLOps (Machine Learning Operations)
Khác với mô hình nghiên cứu offline, MLOps tập trung vào vòng lặp khép kín:
$$\text{Data} \longrightarrow \text{Train} \longrightarrow \text{Evaluate} \longrightarrow \text{Serve (FastAPI)} \longrightarrow \text{Client (Flutter)} \longrightarrow \text{Feedback} \longrightarrow \text{Retrain}$$

---

## CHƯƠNG 3: THU THẬP & PHÂN TÍCH DỮ LIỆU (EDA)

### 3.1. Nguồn dữ liệu & Tiền xử lý
- **Dataset:** MovieLens **ml-25m** với 25,000,095 đánh giá từ 162,541 người dùng trên 62,423 bộ phim (ID user từ 1 → 162,541).
- **Cân đối tài nguyên (Compute Balance):** Pipeline giới hạn `--max-ratings 2,000,000` + `--min-movie-ratings 50` → tập huấn luyện hiệu quả 13,176 phim phổ biến (~152 rating/phim) để giữ thời gian retrain ≈ 11s trong khi catalog phục vụ giữ nguyên 62,316 phim.
- **Enrichment:** Gọi TMDb API (rate-limit 40 req/10s, cache `tmdb_cache.json`) với chế độ `--prioritize-ratings` — ưu tiên fetch 7,200 phim được đánh giá nhiều nhất (~26% metadata thật, 16,497 phim có poster/overview thật sau 2 vòng fetch), các phim còn lại dùng mock fallback.
- **Data Splitting:** Áp dụng **Temporal Split** (80% Train, 10% Validation, 10% Test) theo mốc thời gian để tránh rò rỉ dữ liệu (Data Leakage). Dữ liệu feedback từ API (`interactions_log.csv`) sau khi gộp được chuyển vào TRAIN để vòng phản hồi thực sự làm nóng user mới (xem Chương 5.4).
- **Tránh xung đột ID:** Tài khoản app đăng ký bắt đầu từ `user_id = 200000` để không trùng không gian ID với ml-25m (162,541 users).

### 3.2. Chỉ số độ thưa & Đặc trưng phân phối
- **Sparsity Index (toàn bộ ml-25m):** $1 - \frac{25,000,095}{162,541 \times 62,423} = 99.75\%$
- **Sparsity Index (tập huấn luyện 2M):** $1 - \frac{2,000,000}{157,068 \times 13,176} = 99.90\%$ — xác nhận bài toán dữ liệu cực thưa, là thách thức trung tâm của đề tài.
- **Đuôi dài (Long-tail):** Phân phối lượt tương tác tập trung ở top 5% phim phổ biến, đa số phim có rất ít lượt đánh giá.

---

## CHƯƠNG 4: THIẾT KẾ KẾT CẤU HỆ THỐNG & CÔNG NGHỆ

### 4.1. Kiến trúc hệ thống tổng thể
Mô hình Client-Server phục vụ qua Ngrok tunnel:
- **Mobile Client:** Flutter App (iOS/Android) giao tiếp qua REST API.
- **Backend Serving:** FastAPI Server (Python 3.10) với in-memory caching.
- **MLOps Pipeline:** `retrain.py` tự động nạp dữ liệu mới, lưu phiên bản `model_v_timestamp.pkl` và gọi hot-reload.
- **Dashboard Management:** Streamlit Dashboard phục vụ trực quan hóa EDA, benchmark offline và trigger retrain.

---

## CHƯƠNG 5: KẾT QUẢ THỰC NGHIỆM & ĐÁNH GIÁ

### 5.1. Bảng so sánh hiệu năng các thuật toán (Offline Benchmark)

| Algorithm | RMSE ↓ | MAE ↓ | Precision@10 ↑ | Recall@10 ↑ | NDCG@10 ↑ | Coverage ↑ |
|---|---|---|---|---|---|---|
| **Mean Predictor** | 1.0461 | 0.8250 | 0.5520 | 0.3840 | 0.4850 | 1.20% |
| **Popularity Recommender** | 0.9850 | 0.7620 | 0.6430 | 0.4410 | 0.5620 | 3.50% |
| **KNN (Cosine)** | 0.9634 | 0.7410 | 0.6840 | 0.4950 | 0.6210 | 24.60% |
| **FunkSVD (NumPy - Tự code)** | 0.9125 | 0.7020 | 0.7250 | 0.5340 | 0.6780 | 35.80% |
| **SVD (Surprise - Optimal)** | **0.8845** | **0.6780** | **0.7510** | **0.5620** | **0.7100** | **42.50%** |

### 5.2. Đánh giá trên nhóm User thưa dữ liệu (Cold vs Warm vs Heavy)
SVD thể hiện ưu thế tuyệt đối ở nhóm **Cold Users (< 5 ratings)** với RMSE 0.9950 so với KNN 1.1850, chứng minh năng lực nén đặc trưng qua các yếu tố ẩn (latent factors).

### 5.3. Nâng cấp lên ml-25m & Model Gate Rebase
Sau khi migrate dataset, val set mới (200,000 ratings) có **~84% user lạnh** (không xuất hiện trong TRAIN → SVD dự đoán gần giá trị trung bình, RMSE ≈ 1.00). Điều này khiến việc so sánh RMSE xuyên dataset trở nên không công bằng:

| Model | Dataset | Val RMSE | Warm-user RMSE | Ghi chú |
|---|---|---|---|---|
| SVD cũ | ml-latest-small (80K train) | 0.9498 | — | val gần như toàn user ấm |
| SVD mới | ml-25m (1.6M train) | 0.9971 | **0.8822** | 84% user lạnh trong val |

Kết quả quan trọng: trên nhóm user ấm (đối tượng mà SVD thực sự được "học"), RMSE mới **0.8822 < 0.9498** của model cũ — cá nhân hóa cải thiện rõ rệt với dữ liệu lớn. Model Gate được rebase một lần với `GATE_TOLERANCE=1.0` (baseline mới = 0.9971); các lần retrain sau trên cùng dataset giữ `GATE_TOLERANCE=0.0` nên so sánh công bằng.

### 5.4. Vòng phản hồi (Feedback Loop) — vấn đề và giải pháp
Khi gộp feedback vào temporal split thuần túy, các bản ghi feedback luôn có timestamp mới nhất → rơi vào TEST (10% cuối) → user mới **không bao giờ** trở thành user ấm dù đã tương tác. Đã sửa tại `merge_interactions.py`: mọi cặp user-movie trong `interactions_log.csv` được chuyển vào TRAIN. **Verify end-to-end:** user mới (cold-start → popularity theo thể loại) → đánh giá phim = 1.0 sao → retrain → gợi ý chuyển sang SVD path (~750ms), loại bỏ đúng phim vừa chấm và cá nhân hóa rõ rệt.

### 5.5. Đo lường Latency (Live HTTP Benchmark — catalog 62,316 phim)
50 requests qua API: **100% thành công**, trung bình 621ms, P50 741ms, P95 813ms, P99 831ms (warm-user path tính điểm vector hóa trên toàn catalog; cold-start path ~6ms nhờ popularity baseline + cache 5 phút).

---

## CHƯƠNG 6: QUY TRÌNH THU THẬP DỮ LIỆU TƯƠNG TÁC & VÒNG PHẢN HỒI

### 6.1. Các loại dữ liệu tương tác & trọng số quy đổi
Hệ thống thu thập 3 loại tín hiệu từ ứng dụng di động, tất cả được quy đổi về **thang rating 0.5–5.0** trước khi tham gia huấn luyện:

| Loại | Hành vi | Endpoint | Quy đổi | Ghi chú |
|---|---|---|---|---|
| **Explicit** | Chấm sao | `POST /api/interactions/rating` | Rating gốc (0.5–5.0) | Tín hiệu tường minh, độ tin cậy cao nhất |
| **Implicit** | Thả tim / bỏ tim | `POST /api/interactions/favorite` | Tim = **4.5**; Bỏ tim = **2.5** | Quy đổi hành vi ngầm thành điểm số |
| **Implicit** | Xem phim | `POST /api/interactions/watch` | Tỷ lệ xem ≥ 80% → **5.0**; ≥ 50% → **4.0**; ≥ 20% → **3.0**; < 20% → **1.5** | `Watch Ratio = thời gian xem / tổng thời lượng`; xem dưới 20% bị phạt (bỏ xem giữa chừng) |

Lưu ý phân biệt **hai kênh favorites**: endpoint `/api/users/{id}/favorites` chỉ ghi vào `user_favorites.csv` phục vụ hiển thị màn hình Yêu thích (KHÔNG vào huấn luyện); còn `/api/interactions/favorite` mới ghi tín hiệu vào `interactions_log.csv` — nguồn duy nhất của vòng feedback MLOps. Ứng dụng gọi cả hai kênh song song.

### 6.2. Ghi nhận & lưu trữ
- Mọi tương tác ghi vào `data/processed/interactions_log.csv`, **tách biệt hoàn toàn với train set** — train set không bao giờ bị thay đổi trực tiếp bởi request API.
- **Cơ chế upsert theo cặp (userId, movieId):** nếu user chấm lại một phim đã chấm, bản ghi có `timestamp` mới nhất được giữ lại → việc "sửa rating" phản ánh đúng sở thích mới nhất của user.
- **Cache gợi ý (TTL 5 phút):** mỗi tương tác mới chỉ xóa cache của đúng user đó (`_invalidate_recommendation_cache`), các user khác không bị ảnh hưởng.

### 6.3. Chu kỳ tái huấn luyện (Retrain Cycle)
Retrain được kích hoạt theo hai cách — **tự động (Auto-Retrain)** hoặc **thủ công** (`python src/pipeline/retrain.py`), trọn chu kỳ ≈ 16 giây:

1. **Merge & Re-split** (`merge_interactions.py`): gộp `interactions_log.csv` vào dữ liệu gốc, dedupe, temporal split 80/10/10 — **toàn bộ bản ghi feedback được chuyển vào TRAIN** để user mới tương tác trở thành "user ấm" sau đúng 1 chu kỳ.
2. **Huấn luyện SVD** trên 1.6M ratings (50 factors, 20 epochs) ≈ 11 giây.
3. **Model Gate:** promote lên `model_latest.pkl` chỉ khi RMSE val mới ≤ baseline hiện tại + `GATE_TOLERANCE` (0.0); nếu tệ hơn, phiên bản mới được lưu dưới tên `model_v_{timestamp}.pkl` nhưng không thay thế bản đang phục vụ.
4. **Zero-downtime Reload:** POST `/api/recommendations/reload` để API nạp model mới tại chỗ, không cần restart server.

**Auto-Retrain:** một daemon thread chạy bên trong API (khởi động cùng `api/main.py`), mỗi 30 giây đếm số interaction mới trong `interactions_log.csv` và kích hoạt `run_retrain()` khi: (a) có ≥ `AUTO_RETRAIN_MIN_ROWS` (mặc định 5) bản ghi mới, hoặc (b) đã có bản ghi mới nhưng chờ quá `AUTO_RETRAIN_MAX_IDLE` (3600s); luôn tôn trọng khoảng cách tối thiểu `AUTO_RETRAIN_MIN_INTERVAL` (300s) giữa hai lần retrain. Cấu hình trong `.env`, tắt bằng `AUTO_RETRAIN=0`. Trong thử nghiệm thực tế: 21 bản ghi feedback mới được gộp vào TRAIN (1,600,021 rows), RMSE val 0.9972 → 0.9970, model promoted và nạp nóng thành công trong 15.9 giây.

### 6.4. Hành trình của một user: khi nào khuyến nghị "sát thực tế"

| Giai đoạn | Trạng thái | Khuyến nghị nhận được | Độ sát thực tế |
|---|---|---|---|
| 1. Vừa đăng ký (chọn thể loại) | Cold-start | Popularity + ưu tiên thể loại đã khai báo (~6ms) | Thấp — chỉ dựa trên 2–3 thể loại |
| 2. Đã tương tác, chưa retrain | Vẫn lạnh nhưng đã **online-update** | Embedding $p_u$ khởi tạo và cập nhật ngay bằng 1 bước SGD cho từng rating → gợi ý cá nhân hóa tức thời qua path vectorized (extra_users) | Trung bình, phản hồi tức thời |
| 3. Sau ≥ 1 chu kỳ retrain | **Ấm** | SVD cá nhân hóa (~750ms): loại phim đã rate, vector ẩn $p_u$ được học từ chính lịch sử của user, tiếp tục được online-update sau mỗi tương tác mới | **Cao** |
| 4. Xem xong một phim | Ấm | Watch-finished quy đổi rating 5.0 + online update; phim bị loại khỏi hàng "Tiếp tục xem" | Cao, cải thiện dần theo chu kỳ |

**Kết luận:** với **online personalization** (6.6), khuyến nghị thay đổi **ngay sau tương tác** kể cả khi chưa retrain; Auto-Retrain (6.3) tiếp tục đưa user từ "ảo" (extra_users) thành "ấm" thực sự trong model chính sau mỗi chu kỳ. Hai cơ chế bổ sung cho nhau: online update cho phản hồi tức thời (ms), batch retrain cho chất lượng lâu dài.

### 6.5. Hạn chế & hướng cải tiến
- **Online update chưa tinh chỉnh learning rate riêng:** 1 bước SGD mỗi tương tác với `lr = 0.005` — với user mới có rất ít dữ liệu, embedding có thể dao động; có thể dùng adaptive learning rate hoặc mini-batch các tương tác gần đây.
- **Trọng số quy đổi chưa phân biệt độ tin cậy:** điểm 5.0 từ "xem hết phim" và 5.0 từ "chấm sao" hiện tương đương nhau; có thể gắn confidence weight trong hàm mất mát.
- **Auto-Retrain tối giản:** chỉ kích hoạt theo số dòng log và thời gian chờ; chưa xét chất lượng (ví dụ độ phân tán rating, số user mới). Có thể mở rộng bằng kiểm tra data drift.
- **Player mô phỏng:** chưa có video thật; cấu trúc Timer đã tách sẵn để thay bằng `video_player` khi có nguồn video.

### 6.6. Cá nhân hóa tức thời (Online Update / Instant Personalization)
Để rút ngắn khoảng cách giữa tương tác và khuyến nghị mà **không cần retrain**, hệ thống áp dụng online update theo đúng công thức bước cập nhật của FunkSVD. Với một tương tác mới (user $u$, item $i$, rating $r$), gọi $e_{ui} = r - (\mu + b_u + b_i + p_u^T q_i)$, hệ thống thực hiện:

$$b_u \leftarrow b_u + \eta \cdot (e_{ui} - \lambda \cdot b_u), \quad p_u \leftarrow p_u + \eta \cdot (e_{ui} \cdot q_i - \lambda \cdot p_u)$$

với $\eta$ là learning rate (0.005) và $\lambda$ là regularization (0.05) — đúng phép cập nhật mà thuật toán đã dùng khi huấn luyện. User chưa từng xuất hiện trong train set được khởi tạo embedding $p_u = \mathbf{0}, b_u = 0$ và lưu vào từ điển `extra_users` trong `svd_surprise.py`; quá trình recommend cho các user này chạy trên **path vectorized** (không phải fallback từng phim) nên vẫn trả về toàn bộ catalog 62K phim trong ~5ms.

- **Kích hoạt khi:** chấm sao (`/api/interactions/rating`) và xem xong phim (`PUT /api/watch/progress` với ratio ≥ 95%).
- **Hiệu ứng:** gợi ý của đúng user đó thay đổi ngay lập tức (cache bị invalidate + embedding mới), các user khác không bị ảnh hưởng.
- **Kiểm chứng:** user mới (ngoài train set) nhận rating dự đoán giảm dần đúng hướng sau mỗi rating 1 sao (4.2113 → 4.1905 sau 1 bước); user trong train set vẫn cập nhật embedding như cũ.

### 6.7. Tiếp tục xem (Continue Watching) & Watch Progress
Tính năng chuẩn các nền tảng streaming (FPT Play, Netflix): player gửi **heartbeat tiến độ** định kỳ, server lưu vị trí để user có thể quay lại đúng chỗ đã dừng.

- **Heartbeat:** `PUT /api/watch/progress` với `{userId, movieId, positionSeconds, durationSeconds}` — player mô phỏng gửi mỗi 5 giây; server upsert theo cặp (userId, movieId) vào `watch_progress.csv` (ghi atomic + khóa thread).
- **Trạng thái:** ratio < 5% → bỏ qua (chưa đủ để track); 5%–95% → `in_progress`, hiện trong hàng "▶ Tiếp Tục Xem" ở Home (poster + vị trí `MM:SS` + %); ≥ 95% → `finished`: ẩn khỏi hàng, đồng thời **tự quy đổi thành rating 5.0** ghi vào vòng feedback + kích hoạt online update (6.6).
- **Resume:** `GET /api/watch/progress/{userId}/{movieId}` trả vị trí dừng; player mở lại seek đúng giây và hiện banner "Bạn đã xem đến phút X — tiếp tục nhé!" với 2 lựa chọn (Tiếp tục xem / Xem từ đầu).
- **Quản lý:** người dùng có thể xóa phim khỏi danh sách (`DELETE`) mà không xóa lịch sử feedback.
- **Thời lượng phim:** bổ sung cột `runtime_minutes` vào catalog (`preprocess.py --movies-only`, giá trị thật cho ~300 phim phổ biến qua TMDB, mặc định 100 phút) để player mô phỏng tính đúng tổng thời lượng.

---

## CHƯƠNG 7: DEMO NGUYÊN MẪU ỨNG DỤNG DI ĐỘNG & DASHBOARD

Các luồng demo chính:
1. **Đăng ký / Đăng nhập → chọn thể loại:** user mới được gợi ý theo thể loại khai báo.
2. **Đánh giá & thả tim:** gợi ý cá nhân hóa thay đổi ngay (online update) — hàng "🤖 Gợi Ý Cho Bạn (AI SVD)".
3. **Xem phim (player mô phỏng):** bấm "▶ Xem Phim" → player với thanh tiến độ, banner resume khi xem dở; xem hết ≥ 95% tự ghi nhận "đã xem xong".
4. **Tiếp tục xem:** thoát giữa chừng (5–95%) → phim xuất hiện ở hàng "▶ Tiếp Tục Xem" trên Home với vị trí `MM:SS`; mở lại seek đúng giây.
5. **Model Registry:** dashboard Streamlit (port 8501) hiển thị lịch sử phiên bản mô hình sau mỗi lần Auto-Retrain.

*(Xem chi tiết tài liệu hình ảnh và screenshots đính kèm trong thư mục docs/screenshots)*

---

## CHƯƠNG 8: KẾT LUẬN & HƯỚNG PHÁT TRIỂN

### 8.1. Kết quả đạt được
1. Xây dựng thành công hệ thống gợi ý cá nhân hóa hoàn chỉnh end-to-end.
2. Triển khai mô hình FunkSVD toán học tự cài đặt và SVD (Surprise) trên dữ liệu quy mô 25 triệu đánh giá (2M sau cân đối tài nguyên): warm-user RMSE 0.8822, cải thiện so với 0.9498 của dataset nhỏ.
3. Hoàn thiện ứng dụng di động Flutter mượt mà, hỗ trợ cả Explicit và Implicit Feedback.
4. Xây dựng vòng lặp tái huấn luyện tự động MLOps theo thời gian thực (retrain ≈ 11s, reload zero-downtime, Model Gate có rebase baseline, feedback được đưa vào TRAIN để user mới thành user ấm).
5. Cá nhân hóa **tức thời** (online update 1 bước SGD) — khuyến nghị đổi ngay sau mỗi tương tác mà không cần retrain; Auto-Retrain thread trong API kích hoạt khi đủ tương tác mới (đã kiểm chứng: 21 bản ghi → retrain 15.9s, RMSE 0.9972→0.9970, promote + reload tự động).
6. Tính năng **Continue Watching** chuẩn streaming: player mô phỏng có heartbeat 5s, resume đúng vị trí (banner "Tiếp tục xem"), xem xong ≥ 95% tự quy đổi rating 5.0 vào vòng feedback.

### 8.2. Hướng phát triển tiếp theo
- Triển khai thuật toán Hybrid (kết hợp Content-based TF-IDF/BERT với SVD).
- Nâng cấp lưu trữ dữ liệu từ CSV sang PostgreSQL và Caching Redis.
