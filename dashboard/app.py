"""Dashboard V2: chỉ trình bày artifacts có nguồn và kiểm tra khả năng so sánh."""

import os
import sys
from pathlib import Path

import streamlit as st

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from dashboard.services.artifacts import list_runs,load_run
from dashboard.pages import research

st.set_page_config(page_title="MovieRS · Phòng nghiên cứu",page_icon="🎬",layout="wide")
st.title("MovieRS · Phòng nghiên cứu hệ khuyến nghị")
st.caption("Dữ liệu có nguồn · So sánh cùng giao thức · Kiểm chứng cải tiến và đánh đổi")
base=Path(os.getenv("MOVIERS_RUN_DIR",str(ROOT/"artifacts/runs")))
runs=list_runs(base)
if not runs:
    st.info("Chưa có run V2. Chạy pipeline nghiên cứu để tạo kết quả; không có số liệu minh họa.")
    st.code("python -m src.experiments run --profile research")
    st.caption("Kết quả V1 được giữ trong report/experiments; không so Δ với giao thức V2.")
    st.stop()
selected=st.sidebar.selectbox("Run nghiên cứu",runs,format_func=lambda p:p.name)
try:
    run=load_run(selected)
except (OSError,ValueError,KeyError) as error:
    st.error(f"Không thể trình bày run: {error}")
    st.stop()
st.caption(f"Dataset: {run['manifest']['dataset_id']} · Run: {selected.name} · {run['manifest']['status']}")
pages={"Tổng quan":research.overview,"Dữ liệu & provenance":research.data_quality,
       "Tính đại diện của mẫu":research.representativeness,"So sánh mô hình":research.comparison,
       "Phân tích đóng góp":research.ablations,"Khuyến nghị minh họa":research.examples,
       "Vận hành":research.operations}
page=st.sidebar.radio("Nội dung",list(pages))
if page=="So sánh mô hình":
    second=st.sidebar.selectbox("Run đối chiếu",[None,*[p for p in runs if p!=selected]],format_func=lambda p:p.name if p else "Không chọn")
    try:
        other=load_run(second) if second else None
        research.comparison(run,other)
    except (OSError,ValueError,KeyError) as error:
        st.error(str(error))
else:
    pages[page](run)
