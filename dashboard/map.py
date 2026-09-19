from datetime import date, timedelta

import folium
import streamlit as st
from streamlit_folium import st_folium

from dashboard import incident_detail
from services.report_service import ReportService
from utils.formatters import to_local

STATUS_OPTIONS = {
    "": "Tất cả",
    "DRAFT": "Đang xử lý",
    "COMPLETED": "Đã hoàn tất",
    "CANCELLED": "Đã huỷ",
}

STATUS_COLORS = {
    "DRAFT": "orange",
    "COMPLETED": "green",
    "CANCELLED": "gray",
}

# Tâm bản đồ mặc định (Hà Nội) khi chưa có dữ liệu để định vị
DEFAULT_CENTER = (21.0278, 105.8342)


@st.cache_resource
def _get_service() -> ReportService:
    return ReportService()


@st.dialog("Chi tiết sự cố", width="large")
def _show_detail_dialog(incident_id: int) -> None:
    incident_detail.render(incident_id)


def render() -> None:
    st.title("🗺️ Bản đồ sự cố")

    c1, c2, c3 = st.columns(3)
    with c1:
        date_from = st.date_input("Từ ngày", value=date.today() - timedelta(days=30), key="map_from")
    with c2:
        date_to = st.date_input("Đến ngày", value=date.today(), key="map_to")
    with c3:
        status_key = st.selectbox(
            "Trạng thái", options=list(STATUS_OPTIONS.keys()),
            format_func=lambda k: STATUS_OPTIONS[k], key="map_status",
        )

    df = _get_service().get_incidents_with_coords(
        date_from=date_from, date_to=date_to, status=status_key or None
    )
    st.caption(f"Hiển thị **{len(df)}** sự cố có toạ độ trên bản đồ.")

    if df.empty:
        st.info("Không có sự cố nào khớp bộ lọc trong khoảng thời gian này.")
        return

    center = (df["latitude"].mean(), df["longitude"].mean())
    fmap = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")

    for _, row in df.iterrows():
        color = STATUS_COLORS.get(row["trang_thai"], "blue")
        reported_local = to_local(row["thoi_gian_bao_cao"])
        popup_html = (
            f"<b>{row['ma_su_co']}</b><br>"
            f"Tuyến: {row['tuyen']}<br>"
            f"Loại: {row['loai_su_co']}<br>"
            f"Trạng thái: {STATUS_OPTIONS.get(row['trang_thai'], row['trang_thai'])}<br>"
            f"Thời gian: {reported_local:%d/%m/%Y %H:%M}"
        )
        folium.Marker(
            location=(row["latitude"], row["longitude"]),
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=row["ma_su_co"],
            icon=folium.Icon(color=color, icon="wrench", prefix="fa"),
        ).add_to(fmap)

    map_state = st_folium(fmap, use_container_width=True, height=550, returned_objects=["last_object_clicked_tooltip"])

    clicked_code = map_state.get("last_object_clicked_tooltip") if map_state else None
    if clicked_code:
        match = df[df["ma_su_co"] == clicked_code]
        if not match.empty and st.button(f"🔍 Xem chi tiết {clicked_code}"):
            _show_detail_dialog(int(match.iloc[0]["incident_id"]))
