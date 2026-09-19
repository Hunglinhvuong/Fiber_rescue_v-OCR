import os
import sys

# streamlit run dashboard/app.py chỉ thêm thư mục dashboard/ vào sys.path,
# KHÔNG thêm thư mục gốc project -> phải tự thêm để các import tuyệt đối
# (dashboard.*, services.*, utils.*, config.*) hoạt động được.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st

from dashboard import analytics, home, incidents, map as map_page, materials, routes

st.set_page_config(
    page_title="Fiber Rescue Dashboard",
    page_icon="🛠️",
    layout="wide",
)

pages = [
    st.Page(home.render, title="Tổng quan", icon="📊", url_path="tong-quan", default=True),
    st.Page(map_page.render, title="Bản đồ sự cố", icon="🗺️", url_path="ban-do-su-co"),
    st.Page(incidents.render, title="Danh sách sự cố", icon="🚨", url_path="danh-sach-su-co"),
    st.Page(analytics.render, title="Phân tích", icon="📈", url_path="phan-tich"),
    st.Page(materials.render, title="Vật tư", icon="🧰", url_path="vat-tu"),
    st.Page(routes.render, title="Tuyến cáp", icon="🛣️", url_path="tuyen-cap"),
]

nav = st.navigation(pages)
nav.run()
