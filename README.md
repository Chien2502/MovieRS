# 🎬 MovieRS — Movie Recommendation System

> **Hệ thống Khuyến nghị Phim Cá Nhân Hóa theo chuẩn MLOps**  
> *Ứng dụng thuật toán SVD (Matrix Factorization) giải quyết bài toán ma trận thưa (Data Sparsity) & Khởi động lạnh (Cold-Start)*

---

## 📌 Tổng Quan

MovieRS là một nguyên mẫu (Prototype) hệ thống gợi ý phim end-to-end hoàn chỉnh, được xây dựng theo kiến trúc và quy trình MLOps tiên tiến tương tự các hệ thống streaming lớn (như FPT Play, Netflix):

```
Data Collection ──► Feature Engineering ──► SVD Training ──► Evaluation ──► FastAPI Serving ──► Flutter App ──► Implicit/Explicit Feedback ──► Auto Retrain
```

### các bài toán kỹ thuật cốt lõi

| Bài toán | Thách thức | Giải pháp áp dụng |
|---|---|---|
| **Data Sparsity** | Ma trận thưa > 98.3% | FunkSVD (Matrix Factorization) nén biểu diễn latent factors |
| **Cold-Start** | User mới chưa có tương tác | Màn hình Onboarding chọn thể loại + Popularity Recommender fallback |
| **Implicit Feedback** | User không chủ động rate | Quy đổi thời lượng xem phim (Watch Ratio) & Thả tim (Favorite) sang sao |
| **MLOps Loop** | Model bị trôi (Model Drift) | Retraining pipeline tự động, versioning và zero-downtime hot reload |

---

## 🏗️ Kiến Trúc Hệ Thống

```
┌─────────────────────────┐       HTTPS       ┌─────────────────────────┐
│   📱 Flutter Mobile     │ ────────────────► │    🌐 Ngrok Tunnel      │
│   (App Client UI)       │ ◄──────────────── │ (Public HTTPS Endpoint) │
└─────────────────────────┘                   └─────────────────────────┘
                                                           │
                                                           ▼
┌─────────────────────────┐       Local       ┌─────────────────────────┐
│   📊 Streamlit AI       │ ────────────────► │    ⚡ FastAPI Server    │
│   (Dashboard Management)│ ◄──────────────── │   (Port 8000 REST API)  │
└─────────────────────────┘                   └─────────────────────────┘
                                                           │
                                           ┌───────────────┴───────────────┐
                                           ▼                               ▼
                                ┌─────────────────────┐         ┌─────────────────────┐
                                │  🧠 SVD Model       │         │  🌐 TMDb API        │
                                │  (model_latest.pkl) │         │  (Metadata & Cover) │
                                └─────────────────────┘         └─────────────────────┘
```

---

## 🛠️ Tech Stack

| Tầng | Công nghệ | Mô tả |
|---|---|---|
| **ML / AI Engine** | Python 3.10+, scikit-surprise, NumPy, Pandas | SVD toán học tự viết (NumPy) + Surprise library |
| **Backend Serving** | FastAPI, Uvicorn, Pydantic | REST API tốc độ cao, swagger docs tự động, CORS |
| **Mobile App** | Flutter 3.x, Dart | App đa nền tảng (Android/iOS), Provider, CachedNetworkImage |
| **Dashboard** | Streamlit, Matplotlib, Seaborn | Giao diện EDA, benchmark offline và trigger retraining |
| **Tunneling** | Ngrok | Triển khai public endpoint từ local cho thiết bị di động |
| **Data Engineering** | MovieLens (ml-latest-small) + TMDb API | 100k+ ratings, làm giàu thông tin poster & tóm tắt |

---

## 📁 Cấu Trúc Dự Án

```
MovieRS/
├── api/                     # Backend FastAPI
│   ├── main.py              # Application Entry Point
│   ├── routes/              # Health, Movies, Recommendations, Interactions
│   └── services/            # Recommender Service & Caching Layer
├── dashboard/               # Streamlit AI & Evaluation Dashboard
│   └── app.py               # Dashboard quản trị, EDA & Retrain trigger
├── data/                    # Dữ liệu
│   ├── raw/                 # MovieLens gốc
│   ├── enriched/            # Metadata đã làm giàu từ TMDb API
│   └── processed/           # Ratings train/val/test splits (Temporal Split)
├── mobile_app/              # 📱 Ứng dụng di động Flutter
│   ├── pubspec.yaml         # Dependencies configuration
│   └── lib/
│       ├── main.dart        # Flutter Entrypoint
│       ├── config/          # AppConfig (Ngrok URL)
│       ├── constants/       # AppColors (Dark-mode palette)
│       ├── models/          # Movie Data Model
│       ├── services/        # ApiService HTTP Client
│       ├── widgets/         # MovieCard, EmptyStateWidget, ErrorStateWidget
│       └── screens/         # Splash, Onboarding, Home, Detail, Search, Favorites, Profile
├── models/                  # File lưu trữ mô hình SVD (.pkl)
├── notebooks/               # Jupyter Notebooks phân tích & huấn luyện
│   ├── 01_data_exploration.ipynb   # Notebook EDA & Sparsity Index
│   └── 02_model_training.ipynb     # Notebook Offline Evaluation & User Groups
├── report/                  # 📜 Báo cáo Thực tập chính thức
│   └── Bao_Cao_Thuc_Tap_MovieRS.md
├── src/                     # Source code Python (Data, Models, Pipeline)
│   ├── data/                # download_movielens.py, fetch_tmdb.py, preprocess.py, split.py
│   ├── models/              # baseline.py, svd_surprise.py, svd_numpy.py, evaluate.py
│   └── pipeline/            # retrain.py, benchmark.py
├── .env                     # Biến môi trường & cấu hình NGROK_URL
├── requirements.txt         # Thư viện Python phụ thuộc
└── README.md
```

---

## 🚀 Hướng Dẫn Khởi Chạy

### 1. Cài đặt Môi trường Python

```powershell
# Tạo môi trường ảo
python -m venv venv
.\venv\Scripts\Activate.ps1

# Cài đặt phụ thuộc
pip install -r requirements.txt
```

### 2. Khởi chạy Backend API (FastAPI)

```powershell
$env:PYTHONIOENCODING="utf-8"; python api/main.py
```
- API Docs (Swagger UI): `http://localhost:8000/docs`

### 3. Mở Cổng Ngrok Tunnel (Cho App Mobile)

```powershell
ngrok http 8000
```
- Copy URL Ngrok (ví dụ `https://xxxx.ngrok-free.dev`) dán vào:
  - File `.env` -> `NGROK_URL=https://xxxx.ngrok-free.dev`
  - File `mobile_app/lib/config/app_config.dart` -> `ngrokUrl = 'https://xxxx.ngrok-free.dev'`

### 4. Khởi chạy AI Dashboard (Streamlit)

```powershell
streamlit run dashboard/app.py
```
- Dashboard URL: `http://localhost:8501`

### 5. Khởi chạy Mobile App (Flutter)

```powershell
cd mobile_app
flutter pub get
flutter run
```

### 6. Chạy Benchmark API Latency & Integration Test

```powershell
python src/pipeline/benchmark.py
```

---

## 📊 So Sánh Hiệu Năng Mô Hình (Offline Benchmark)

| Mô hình (Model) | RMSE ↓ | MAE ↓ | Precision@10 ↑ | Recall@10 ↑ | NDCG@10 ↑ | Catalog Coverage ↑ |
|---|---|---|---|---|---|---|
| **Mean Predictor** | 1.0461 | 0.8250 | 0.5520 | 0.3840 | 0.4850 | 1.20% |
| **Popularity Recommender** | 0.9850 | 0.7620 | 0.6430 | 0.4410 | 0.5620 | 3.50% |
| **KNN Collaborative Filtering** | 0.9634 | 0.7410 | 0.6840 | 0.4950 | 0.6210 | 24.60% |
| **FunkSVD (NumPy - Tự code)** | 0.9125 | 0.7020 | 0.7250 | 0.5340 | 0.6780 | 35.80% |
| **SVD (Surprise - Optimal)** | **0.8845** | **0.6780** | **0.7510** | **0.5620** | **0.7100** | **42.50%** |

---

## 📄 Báo Cáo Thực Tập

Xem báo cáo thực tập chính thức chi tiết tại file [report/Bao_Cao_Thuc_Tap_MovieRS.md](file:///d:/Users/BT/N3_K1/ThucTapThucTe/MovieRS/report/Bao_Cao_Thuc_Tap_MovieRS.md).
