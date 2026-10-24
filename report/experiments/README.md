# Artifacts thực nghiệm MovieRS

`latest.json` là toàn bộ kết quả đo; `experiment_<UTC>.json` giữ bản của run; `summary.csv` là bảng trung bình để nhập báo cáo. Dashboard đọc JSON, không dùng bảng số tự viết.

Lệnh tái lập run đã bàn giao:

```powershell
$env:PYTHONIOENCODING="utf-8"
python src/models/train_pipeline.py --seeds 42 43 44 --ranking-users 200
```

Run 15/10/2026 chạy 3 seed, 20 epoch, 50 factors, trong khoảng 317 giây trên máy kiểm chứng. RMSE/MAE dùng toàn bộ split; ranking lấy mẫu user nhưng chấm toàn bộ ứng viên. Không gộp log demo, không ghi lại processed CSV hoặc production pickle.

Để kiểm tra provenance, đối chiếu SHA-256 file nguồn trong `environment.source_sha256`, hash CSV trong `dataset`, hash từng split và phiên bản Python/thư viện. `working_tree_dirty=true` nghĩa mã chạy có thay đổi chưa commit; hash nguồn ghi rõ phiên bản thực tế, không chỉ dựa vào Git HEAD. Tên timestamp trong artifact dùng UTC.

`std_across_seeds=null` ở baseline nghĩa không có nhiều lượt huấn luyện ngẫu nhiên; không phải lỗi hoặc sai số bằng 0. CI95 bootstrap user trong mẫu cố định nằm trong từng `test_ranking.ci95`. Những CI này không đo bất định do chọn mẫu dataset hay thay đổi giao thức.

Giới hạn và cách diễn giải nằm trong báo cáo. Không đối chiếu các số Top-K mới với bảng minh họa của bản cũ. Muốn mở rộng thành 1.000 user: thay `--ranking-users 1000`, ghi sang thư mục khác với `--output-dir` để giữ nguyên run tham chiếu.
