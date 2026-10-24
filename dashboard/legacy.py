"""Dashboard đọc kết quả thực nghiệm có nguồn; không sinh bảng số minh họa."""

import json
import sys
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
PROCESSED_DIR = PROJECT_ROOT / 'data/processed'
EXPERIMENT = PROJECT_ROOT / 'report/experiments/latest.json'

st.set_page_config(page_title='MovieRS · Phòng thực nghiệm', page_icon='🎬', layout='wide')
st.title('MovieRS · Hệ khuyến nghị phim cá nhân hóa')
st.caption('SVD · Bayesian popularity · Sở thích thể loại · Đa dạng MMR. Trình phát của ứng dụng là mô phỏng.')
page = st.sidebar.radio('Nội dung', ['Dữ liệu', 'Thực nghiệm', 'Khuyến nghị trực tiếp', 'Mô hình vận hành'])


@st.cache_data
def load_data():
    """Chỉ đọc dữ liệu để thống kê, không ghi CSV."""
    return (pd.read_csv(PROCESSED_DIR / 'movies_processed.csv'),
            pd.read_csv(PROCESSED_DIR / 'ratings_processed.csv'))


if page == 'Dữ liệu':
    try:
        movies, ratings = load_data()
    except (OSError, ValueError):
        st.info('Chưa có dữ liệu. Xem quy trình chuẩn bị MovieLens 25M trong README.')
        st.stop()
    users, items = int(ratings.userId.nunique()), int(ratings.movieId.nunique())
    columns = st.columns(4)
    for col, label, value in zip(columns, ['Đánh giá đã xử lý', 'Người dùng', 'Phim có đánh giá', 'Danh mục phim'],
                                 [len(ratings), users, items, len(movies)]):
        col.metric(label, f'{value:,}')
    st.metric('Độ thưa trên ma trận user × phim có đánh giá', f'{(1-len(ratings)/(users*items))*100:.4f}%')
    st.caption('Danh mục metadata và tập phim có đánh giá là hai tập khác nhau. Dữ liệu gốc là MovieLens 25M, được lấy mẫu xuống 2M trong checkout hiện tại.')
    a, b = st.columns(2)
    with a:
        st.write('Phân phối số sao')
        st.bar_chart(ratings.rating.value_counts().sort_index())
    with b:
        st.write('Phân phối số đánh giá của phim (sắp giảm dần)')
        counts = ratings.movieId.value_counts().reset_index(drop=True)
        st.line_chart(counts)

elif page == 'Thực nghiệm':
    if not EXPERIMENT.exists():
        st.info('Chưa có kết quả đo. Dashboard không hiển thị số giả lập.')
        st.code('python src/models/train_pipeline.py --seeds 42 43 44 --ranking-users 300')
        st.stop()
    try:
        experiment = json.loads(EXPERIMENT.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        st.error(f'Không đọc được artifact: {error}')
        st.stop()
    st.write(f"Thời điểm chạy (UTC): {experiment['created_at']}")
    st.caption(f"Seed huấn luyện: {experiment['parameters']['seeds']} · "
               f"Tối đa {experiment['protocol']['ranking_users_limit']} user cho ranking; chấm toàn bộ ứng viên TRAIN chưa tương tác.")
    st.write('So sánh trên TEST')
    table = pd.DataFrame([{'Mô hình': name, **{metric: result['mean'] for metric, result in metrics.items()}}
                          for name, metrics in experiment['summary'].items()])
    st.dataframe(table, hide_index=True, width='stretch')
    st.caption('RMSE/MAE: thấp hơn tốt hơn. Precision/Recall/NDCG/Coverage/Diversity: cao hơn thường tốt hơn, cần xét cùng nhau. '
               'Novelty đo độ ít phổ biến theo TRAIN, không chứng minh người dùng hài lòng hơn.')
    st.bar_chart(table.set_index('Mô hình')[['ndcg', 'coverage', 'diversity']])
    selected = st.selectbox('Chi tiết mô hình và seed', list(experiment['results']))
    result = experiment['results'][selected]
    st.write('Sai số dự đoán theo nhóm lịch sử TRAIN')
    st.dataframe(pd.DataFrame(result['test_rating']['groups']).T, width='stretch')
    ranking = result['test_ranking']
    st.write('Xếp hạng theo nhóm user')
    st.dataframe(pd.DataFrame(ranking['groups']).T, width='stretch')
    st.write('Khoảng tin cậy 95% (bootstrap người dùng trong mẫu cố định)')
    st.json(ranking['ci95'])
    st.caption(f"Đánh giá {ranking['users']}/{ranking['eligible_users']} user đủ điều kiện · "
               f"Danh mục ứng viên: {ranking['catalog_size']} phim · "
               f"Positive nằm ngoài danh mục TRAIN: {ranking['unavailable_positive_fraction']:.2%}.")
    with st.expander('Giao thức, hash dữ liệu, tham số và lựa chọn trên validation'):
        st.json({key: experiment[key] for key in ['protocol', 'dataset', 'parameters', 'validation_selection', 'environment']})
    for limitation in experiment['limitations']:
        st.info(limitation)
    st.download_button('Tải toàn bộ bằng chứng JSON', EXPERIMENT.read_bytes(), 'moviers_experiment.json', 'application/json')

elif page == 'Khuyến nghị trực tiếp':
    uid = st.number_input('User ID (có thể dùng tài khoản demo >=200000)', min_value=1, value=200000)
    if st.button('Lấy gợi ý'):
        try:
            response = requests.get(f'http://localhost:8000/api/recommendations/{uid}', timeout=20)
            response.raise_for_status()
            data = response.json()
            st.write(f"Chiến lược: {data['strategy']} · Trạng thái: {data['stage']} · {data['latency_ms']} ms")
            st.caption('SVD chỉ được dùng khi user đã có vector; người mới dùng thể loại và điểm cộng đồng.')
            for movie in data['recommendations']:
                st.write(f"**{movie['title']}**")
                st.write(movie['reason'])
                st.caption(f"Thể loại: {movie['genres']} · Điểm xếp hạng: {movie['ranking_score']:.3f}")
        except (requests.RequestException, ValueError, KeyError) as error:
            st.error(f'Không lấy được gợi ý. Khởi chạy API từ gốc dự án. {error}')

else:
    st.info('Registry vận hành và kết quả học thuật được quản lý riêng. Một số metadata cũ chưa có hash validation; '
            'retrain mới sẽ đánh giá lại cả ứng viên và mô hình hiện tại trên cùng validation.')
    latest = PROJECT_ROOT / 'models/model_latest.json'
    if latest.exists():
        st.json(json.loads(latest.read_text(encoding='utf-8')))
    else:
        st.write('Chưa có mô hình vận hành.')
    st.write('Chạy từ gốc dự án để tạo phiên bản và kiểm tra gate:')
    st.code('python src/pipeline/retrain.py')
    st.caption('Lệnh này ghi artifacts model và TRAIN vận hành nếu được promote. Không dùng kết quả này thay cho benchmark học thuật.')
