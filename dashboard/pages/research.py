"""Các màn hình đối chiếu bằng chứng thực nghiệm, dữ liệu và vận hành."""

from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st
import altair as alt

from dashboard.services.artifacts import load_quality, require_comparable


def overview(run):
    st.subheader('Kết luận nghiên cứu')
    comparison=run['comparisons']
    st.info(f"{comparison['candidate']} so với {comparison['baseline']}: {comparison['interpretation'].lower()}")
    cols=st.columns(3)
    cols[0].metric('Baseline chọn từ validation',comparison['baseline'])
    cols[1].metric('Δ NDCG@10 tuyệt đối',f"{comparison['delta']:+.6f}")
    cols[2].metric('User ghép cặp',comparison['users'])
    st.write(f"CI95 của Δ: [{comparison['ci95'][0]:+.6f}, {comparison['ci95'][1]:+.6f}]")
    st.caption('Bootstrap ghép cặp sau khi trung bình qua seed. CI có điều kiện trên snapshot và giao thức; không đo hài lòng người dùng thật.')
    st.markdown((Path(run['folder'])/'model_card.md').read_text(encoding='utf-8'))
    with st.expander('Giao thức và phiên bản thực thi'):
        st.json({k:run['manifest'][k] for k in ['protocol','config','environment','provenance']})


def data_quality(run):
    manifest,quality=load_quality(run)
    st.subheader('Nguồn gốc và chất lượng dữ liệu')
    st.write('Trạng thái kiểm tra:',quality['status'])
    st.dataframe(pd.DataFrame(manifest['splits']).T,width='stretch')
    st.json(quality['hard_checks'])
    st.write('Đối chiếu checksum ZIP:',quality['archive_checksum'])
    st.metric('Phim thiếu thể loại',quality['missing_genre_movies'])
    for message in quality['warnings']:
        st.warning(message)
    for message in quality['limitations']:
        st.info(message)
    st.caption('Checksum xác nhận toàn vẹn file. Tính đại diện, thiếu nhãn exposure và thiên lệch tự chọn được trình bày riêng.')
    st.download_button('Tải data card',(Path(run['manifest']['snapshot'])/'data_card.md').read_bytes(),'data_card.md')


def representativeness(run):
    _,q=load_quality(run)
    st.subheader('Mẫu so với toàn bộ nguồn ML-25M')
    st.metric('Total variation của phân phối số sao',f"{q['rating_total_variation']:.6f}")
    st.metric('Lệch tỷ trọng năm lớn nhất',f"{q['max_year_share_delta']:.2%}")
    for source,sample,title in [('source_rating_histogram','ratings','Số sao'),('source_year_histogram','years','Năm rating')]:
        left=pd.Series(q[source],dtype=float)
        right=pd.Series(q['sample_distributions'][sample],dtype=float)
        frame=pd.DataFrame({'Nguồn':left/left.sum(),'Mẫu':right/right.sum()}).fillna(0).sort_index()
        st.write(title,'— tỷ trọng theo rating')
        st.bar_chart(frame)
    st.write('Quantile hoạt động theo user: 0%, 25%, 50%, 75%, 90%, 99%, 100%')
    st.dataframe(pd.DataFrame({'Nguồn':q['source_user_activity_quantiles'],'Mẫu':q['sample_user_activity_quantiles']}))
    st.caption('Mẫu cụm user giữ lịch sử; tương đồng số sao không đủ chứng minh đại diện toàn bộ thị trường.')
    for left_key,right_key,title in [
        ('source_genre_assignments','sample_genre_assignments','Tỷ trọng lượt gán thể loại theo rating (một phim có thể có nhiều thể loại)'),
        ('source_popularity_bins_rating_counts','sample_popularity_bins_rating_counts','Tỷ trọng rating theo độ phổ biến phim trong nguồn — chỉ dùng cho audit')]:
        if left_key in q:
            left=pd.Series(q[left_key],dtype=float);right=pd.Series(q[right_key],dtype=float)
            st.write(title)
            st.bar_chart(pd.DataFrame({'Nguồn':left/left.sum(),'Mẫu':right/right.sum()}).fillna(0))


def comparison(run,other=None):
    st.subheader('So sánh mô hình trên cùng giao thức')
    table=pd.DataFrame(run['metrics']['families']).T
    st.dataframe(table.sort_values('ndcg',ascending=False),width='stretch')
    st.write('NDCG@10 và khoảng tin cậy 95% — cao hơn tốt hơn')
    from src.experiments.artifacts import read_json
    interval_path=Path(run['folder'])/'intervals.json'
    if interval_path.exists():
        intervals=pd.DataFrame(read_json(interval_path))
        order=intervals.sort_values('mean',ascending=False).model.tolist()
        points=alt.Chart(intervals).mark_point().encode(x=alt.X('mean:Q',title='NDCG@10'),y=alt.Y('model:N',sort=order,title='Mô hình'))
        errorbars=alt.Chart(intervals).mark_rule().encode(x=alt.X('lower:Q',title='NDCG@10'),x2='upper:Q',y=alt.Y('model:N',sort=order,title='Mô hình'))
        st.altair_chart(points+errorbars,width='stretch')
        st.caption('CI95 theo user của từng model. CI chồng lấp không thay thế phép so sánh paired delta.')
    else:st.bar_chart(table[['ndcg']])
    st.write('Sai số dự đoán rating — mô hình chỉ ranking để N/A')
    st.bar_chart(table[['RMSE','MAE']].dropna())
    st.write('Đa dạng thể loại')
    st.bar_chart(table[['diversity']])
    rows=pd.read_parquet(Path(run['folder'])/'per_user_metrics.parquet')
    cohort=st.selectbox('Nhóm lịch sử trước cutoff',['Tất cả',*sorted(rows.cohort.unique())])
    if cohort!='Tất cả': rows=rows[rows.cohort==cohort]
    user_means=rows.groupby(['model','user_id'])[['ndcg','recall','precision','diversity']].mean().reset_index()
    st.dataframe(user_means.groupby('model').agg(users=('user_id','nunique'),ndcg=('ndcg','mean'),recall=('recall','mean')),width='stretch')
    st.caption('Headline giữ positive ngoài catalog. Conditional NDCG nằm trong chi tiết từng model; không thay thế mẫu số chính.')
    st.json(run['comparisons'])
    if other:
        try:
            require_comparable(run,other)
            second=pd.DataFrame(other['metrics']['families']).T
            st.write('Chênh lệch NDCG với run đối chiếu (không phải paired CI)')
            st.dataframe((table.ndcg-second.ndcg).rename('Δ NDCG').dropna())
        except ValueError as error:
            st.warning(str(error))
    st.download_button('Tải bảng kết quả',(Path(run['folder'])/'summary.csv').read_bytes(),'summary.csv','text/csv')


def ablations(run):
    st.subheader('Đóng góp của các thành phần và đánh đổi')
    table=pd.DataFrame(run['metrics']['families']).T
    names=['BiasedSVD','SVDSharedFallback','FixedHybrid','AdaptiveWithoutGenre','AdaptiveHybrid','AdaptiveMMR']
    st.dataframe(table.loc[table.index.intersection(names)],width='stretch')
    st.scatter_chart(table.reset_index(names='model'),x='ndcg',y='diversity',color='model')
    st.caption('Tăng đa dạng không tự động đồng nghĩa tăng độ liên quan. MMR được chọn bằng validation.')
    st.dataframe(pd.DataFrame(run['selection']['mmr_validation']))
    entries=pd.DataFrame(run['metrics']['entries']).T
    st.write('Chi phí fit và latency scoring; hybrid tái sử dụng SVD, không cộng lại chi phí fit backbone.')
    st.dataframe(entries[['model','seed','fit_seconds','latency_ms']],width='stretch')
    st.json(run['resource_usage'])
    # Root repo là parents[2] của dashboard/pages/research.py.
    profile_path=Path(__file__).resolve().parents[2]/'artifacts'/'resource_profiles'/Path(run['folder']).name/'profile.json'
    if profile_path.exists():
        from src.experiments.artifacts import read_json,sha256
        profile=read_json(profile_path)
        if profile['selection_sha256']==sha256(Path(run['folder'])/'selection.json'):
            st.write('Kích thước payload — đo độc lập bằng cùng cấu hình đã khóa')
            st.dataframe(pd.DataFrame(profile['measurements']),width='stretch')
    from src.experiments.artifacts import read_json
    path=Path(run['folder'])/'ablations.json'
    if path.exists():
        st.write('Chênh lệch ghép cặp theo thành phần — phân tích thăm dò')
        st.dataframe(pd.DataFrame(read_json(path)),width='stretch')


def examples(run):
    st.subheader('Hai danh sách với cùng user và cutoff')
    rows=pd.read_parquet(Path(run['folder'])/'per_user_metrics.parquet')
    uid=st.selectbox('User được đánh giá',sorted(rows.user_id.unique()))
    models=sorted(rows.model.unique())
    left=st.selectbox('Mô hình bên trái',models,index=models.index(run['comparisons']['baseline']))
    right=st.selectbox('Mô hình bên phải',models,index=models.index('AdaptiveHybrid'))
    snapshot=Path(run['manifest']['snapshot'])
    fit=pd.concat([pd.read_parquet(snapshot/'train.parquet'),pd.read_parquet(snapshot/'validation.parquet')])
    movies=pd.read_parquet(snapshot/'movies.parquet').set_index('movieId')
    st.write('Lịch sử trước cutoff; không dùng nhãn TEST để tạo hồ sơ')
    st.dataframe(fit[fit.userId==uid][['movieId','rating','timestamp']].tail(20),width='stretch')
    for col,name in zip(st.columns(2),[left,right]):
        with col:
            st.write(name)
            row=rows[(rows.user_id==uid)&(rows.model==name)].iloc[0]
            ids=list(row.recommended_ids)
            st.dataframe(movies.loc[ids][['title','genres']],width='stretch')
            st.caption(f"Seed={row.seed}; NDCG={row.ndcg:.5f}. Danh sách lấy từ run đã khóa, không tính lại theo nhãn tương lai.")
            from dashboard.services.explanations import explain_list
            try:
                explanation=explain_list(run,fit,int(uid),name,row.seed,ids)
                if explanation is not None:
                    st.dataframe(explanation,width='stretch')
                    st.caption('Điểm tái tạo từ payload đã fit, kiểm tra đúng danh sách lưu. Đóng góp hybrid chuẩn hóa trên toàn candidate set; không phải xác suất thích.')
                else:st.caption('Chưa có payload giải thích cho model này; danh sách vẫn lấy nguyên từ benchmark.')
            except (ValueError,OSError):
                st.warning('Không xác minh được payload giải thích; không hiển thị điểm suy đoán.')


def operations(run):
    st.subheader('Trạng thái vận hành')
    st.info('Run nghiên cứu và phiên bản đang phục vụ có vòng đời riêng; TEST không kích hoạt deployment.')
    from src.experiments.config import ROOT
    from src.experiments.artifacts import read_json
    jobs=sorted((ROOT/'artifacts/serving').glob('model_*/job.json'))
    if jobs:
        st.write('Job serving gần nhất')
        st.json(read_json(jobs[-1]))
    if st.button('Kiểm tra API localhost'):
        for endpoint in ['/api/health','/api/health/database']:
            try:
                import time
                started=time.perf_counter()
                response=requests.get('http://127.0.0.1:8000'+endpoint,timeout=10)
                st.write(endpoint,response.status_code,f'{(time.perf_counter()-started)*1000:.1f} ms HTTP health probe')
                st.json(response.json())
            except requests.RequestException:
                st.warning('API chưa chạy hoặc không truy cập được')
    st.json(run['resource_usage'])
