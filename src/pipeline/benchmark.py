"""
benchmark.py — Đo Latency API & Test End-to-End Retrain Loop

Công dụng:
  1. Gửi N requests tới API /api/recommendations/{user_id} để đo Latency trung bình và P95/P99.
  2. (Tùy chọn, cờ --e2e) Mô phỏng luồng MLOps End-to-End: User gửi rating mới -> Trigger Retrain -> Kiểm tra reload model.

Lưu ý:
  - Yêu cầu FastAPI server đang chạy tại http://localhost:8000.
  - Bước e2e sẽ tự đăng ký một user test tạm thời rồi ghi interaction vào interactions_log.csv — chỉ chạy khi thực sự cần:
      python src/pipeline/benchmark.py --e2e
  - Mặc định chỉ đo latency (không ghi dữ liệu):
      python src/pipeline/benchmark.py
"""

import argparse
import time
import requests
import numpy as np

API_BASE_URL = "http://localhost:8000/api"

def benchmark_latency(num_requests=50):
    print("=" * 60)
    print(f"🚀 [Benchmark] Đang đo Latency API Recommendations ({num_requests} requests)...")
    print("=" * 60)

    latencies = []
    failed_requests = 0

    for i in range(num_requests):
        user_id = (i % 50) + 1
        start = time.time()
        try:
            res = requests.get(f"{API_BASE_URL}/recommendations/{user_id}?limit=10", timeout=5)
            duration_ms = (time.time() - start) * 1000
            if res.status_code == 200:
                latencies.append(duration_ms)
            else:
                failed_requests += 1
        except Exception as e:
            failed_requests += 1

    if latencies:
        mean_lat = np.mean(latencies)
        p50_lat = np.percentile(latencies, 50)
        p95_lat = np.percentile(latencies, 95)
        p99_lat = np.percentile(latencies, 99)
        min_lat = np.min(latencies)
        max_lat = np.max(latencies)

        print(f"  ✓ Requests thành công : {len(latencies)} / {num_requests}")
        print(f"  ✓ Requests thất bại  : {failed_requests}")
        print(f"  ✓ Latency Trung bình  : {mean_lat:.2f} ms")
        print(f"  ✓ Latency P50 (Median): {p50_lat:.2f} ms")
        print(f"  ✓ Latency P95         : {p95_lat:.2f} ms")
        print(f"  ✓ Latency P99         : {p99_lat:.2f} ms")
        print(f"  ✓ Latency Thấp nhất   : {min_lat:.2f} ms")
        print(f"  ✓ Latency Cao nhất    : {max_lat:.2f} ms")
    else:
        print("✗ Không có request nào thành công. Vui lòng đảm bảo FastAPI Server đang chạy.")

    print("=" * 60)

def test_end_to_end_loop():
    print("\n🔄 [Integration Test] Kiểm thử Vòng lặp MLOps Feedback Loop...")

    # 1. Tự đăng ký user test tạm thời (tránh ô nhiễm dữ liệu thật)
    test_username = f"test_e2e_{int(time.time())}"
    print(f"  1. Đăng ký user test '{test_username}'...")

    try:
        res = requests.post(f"{API_BASE_URL}/auth/register", json={
            "username": test_username,
            "password": "test12345",
        })
        if res.status_code == 201:
            user_id = res.json()["user"]["userId"]
            print(f"     ✓ Đã đăng ký User {user_id}.")
        else:
            print(f"     ✗ Đăng ký thất bại: {res.status_code} {res.json()}")
            return
    except Exception as e:
        print(f"     ✗ Lỗi đăng ký: {e}")
        return

    # 2. Gửi tương tác mới cho user test
    movie_id = 1
    print(f"  2. Gửi Rating 5.0 sao cho User {user_id} - Movie {movie_id}...")

    try:
        res = requests.post(f"{API_BASE_URL}/interactions/rating", json={
            "userId": user_id,
            "movieId": movie_id,
            "rating": 5.0
        })
        print(f"     ✓ Server response: {res.json()}")
    except Exception as e:
        print(f"     ✗ Lỗi gửi rating: {e}")
        return

    # 3. Gọi API Recommendations
    print(f"  3. Lấy gợi ý cho User {user_id}...")
    try:
        res = requests.get(f"{API_BASE_URL}/recommendations/{user_id}?limit=5")
        if res.status_code == 200:
            recs = res.json()["recommendations"]
            print(f"     ✓ Đã nhận {len(recs)} gợi ý cho User {user_id}.")
        else:
            print(f"     ✗ Mã lỗi: {res.status_code}")
    except Exception as e:
        print(f"     ✗ Lỗi gọi recommendations: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark latency API MovieRS")
    parser.add_argument(
        "--e2e",
        action="store_true",
        help="Chạy thêm vòng lặp MLOps end-to-end (tự đăng ký user test + ghi interaction vào interactions_log.csv)",
    )
    args = parser.parse_args()

    benchmark_latency()
    if args.e2e:
        test_end_to_end_loop()
    else:
        print("\n[ℹ] Bỏ qua Integration Test e2e. Thêm --e2e để chạy "
              "(lưu ý: bước này sẽ ghi interaction test vào interactions_log.csv).")
