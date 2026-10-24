> Đây là biên bản V1 lịch sử. Kết quả hiện tại: [nghiệm thu V2](REFACTOR_ACCEPTANCE.md) và [verification JSON](refactor/verification_v2.json). Không so chênh lệch metric giữa hai giao thức.

# Biên bản kiểm chứng MovieRS — 15/10/2026

## Phạm vi bàn giao

Mã nguồn trên nhánh `codex/academic-recommendation-flow`, thay đổi local chưa commit/push. Không áp dụng Dely. Các thay đổi có sẵn của người dùng ở biểu tượng, Android/iOS và pubspec được giữ nguyên. Không nối API phát video.

## Kiểm tra đã chạy

| Kiểm tra | Kết quả quan sát | Ý nghĩa và giới hạn |
|---|---|---|
| `python -m pytest -q` | 31 passed | Tệp tạm, không sửa dữ liệu/model thật; kiểm tra phương pháp đánh giá và luồng API |
| `python -m compileall -q api src dashboard` | Thành công | Kiểm tra cú pháp Python |
| `flutter analyze` | No issues found | Phân tích tĩnh Flutter/Dart |
| `flutter test` | 7 passed | Splash/Login, metadata trống, lỗi API, endpoint popularity, trạng thái gợi ý, rating/favorite và resume/lưu lỗi |
| `flutter build web` | Built build/web | Build web thành công; chưa kiểm chứng Android/iOS trên thiết bị thật |
| Streamlit `AppTest` | Cả 4 trang không có exception | Dữ liệu, Thực nghiệm, Khuyến nghị trực tiếp, Mô hình vận hành; không kích hoạt ghi dữ liệu |
| `python src/pipeline/verify_runtime.py` | 7 route HTTP trả 200 | Chạy Uvicorn thật trên cổng localhost tạm, AUTO_RETRAIN=0; SHA-256 các đầu vào trước/sau giống nhau |
| Experiment 3 seed trên 2M rating | Hoàn tất trong khoảng 317 giây | RMSE/MAE toàn TEST, ranking cùng mẫu 200 user; không dùng số minh họa |
| Kiểm tra hash artifact | Mọi source hash nghiên cứu và 2 hash CSV nguồn khớp | Git HEAD chưa bao gồm thay đổi local, nên artifact có cả hash nguồn thực tế |

Chi tiết HTTP đo thật: [http_smoke.json](http_smoke.json). Lần gọi health đầu mất khoảng 9,15 giây do tải model/catalog. Sau khi khởi tạo, gợi ý user đã biết khoảng 45 ms, cache khoảng 4 ms, exploration khoảng 144 ms trong lượt smoke này. Đây là số đơn lẻ trên localhost, không phải P95/P99, không chứng minh SLA hay độ trễ qua tunnel/thiết bị di động.

## Các phản ví dụ đã kiểm tra

- Phim được thích trong TEST chỉ đứng đầu nếu bỏ qua distractor chưa quan sát: test buộc nó cạnh tranh toàn catalog và nhận Recall=0 khi xếp sai.
- Cùng timestamp nằm cả TRAIN và VAL: splitter giữ trọn nhóm timestamp về một phía; xáo thứ tự đầu vào không đổi kết quả.
- User không có positive: không được nhận Recall=1.
- Dữ liệu có rating NaN/vượt thang, ID thập phân hoặc timestamp hỏng: bị từ chối.
- Popularity bị giới hạn 20 phim hoặc lấy đầu danh mục: kiểm tra đủ 35 phim và phim tốt nhất ở cuối catalog vẫn đứng đầu.
- Request limit nhỏ rồi lớn dùng chung cache: vẫn trả đủ và bảo toàn prefix.
- Đổi thể loại sau onboarding: kết quả tiếp theo đổi sang thể loại mới.
- Xem xong/thả tim sau một đánh giá 1,5 sao: sao explicit còn nguyên; proxy không xuất hiện trong lịch sử sao.
- Phản hồi cũ thiếu nguồn được giữ nguyên, đếm riêng trong hồ sơ và không tự gán thành sao chủ động.
- Heartbeat hoàn thành gửi lặp: chỉ áp dụng một lần online update cho phản hồi giống hệt.
- Nhiều user ghi feedback đồng thời: không mất bản ghi trong một tiến trình.
- Bỏ phim yêu thích cuối cùng: danh sách và feedback đều rỗng hợp lệ, CSV vẫn có schema.
- Reload thiếu file: snapshot đã tải được giữ nguyên.
- Candidate RMSE kém hơn hoặc NaN: không thay model đang phục vụ; cả candidate và incumbent được chấm cùng validation.
- Phản hồi runtime mới: không thay nội dung holdout CSV, không nhập log vào thí nghiệm; chạy lặp không nhân đôi TRAIN.
- Chạy lại thí nghiệm fixture cùng seed: kết quả và hash split giống nhau, CSV nguồn không đổi.
- Client nhận lỗi lưu rating: không báo “đã lưu”; lưu yêu thích chỉ gọi một request.
- Player có tiến độ cũ: khôi phục đúng vị trí, đợi lưu trước khi thoát; khi lưu lỗi còn ở màn hình và cho thử lại.

## Chưa được chứng minh

Không chạy huấn luyện/retrain ghi đè model production hiện tại; kiểm tra nhánh promote/reject chạy trên model/tệp tạm. Không có thử nghiệm người dùng thật, A/B test, kiểm định significance ghép cặp, benchmark đa worker hoặc kiểm chứng ngrok trên điện thoại thật. Không suy ra chất lượng ranking đã tốt chỉ vì functional test xanh.

Các giới hạn về lọc dữ liệu trước temporal split, tỷ lệ cold-user cao, thiếu nghiên cứu cold-item và xác thực prototype được nêu trong [báo cáo kỹ thuật](Bao_Cao_Thuc_Tap_MovieRS.md).
