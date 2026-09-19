import io
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from services.material_report_service import MATERIAL_GROUP_LABELS, MaterialReportService
from services.report_service import ReportService


@st.cache_resource
def _get_service() -> MaterialReportService:
    return MaterialReportService()


@st.cache_resource
def _get_filter_service() -> ReportService:
    return ReportService()


@st.cache_data(ttl=60)
def _load_catalog(group, active_only, keyword):
    return _get_service().get_material_catalog(group, active_only, keyword)


@st.cache_data(ttl=300)
def _load_groups():
    return _get_service().get_material_groups()


@st.cache_data(ttl=60)
def _load_material_per_incident(date_from, date_to):
    return _get_service().get_material_per_incident(date_from, date_to)


@st.cache_data(ttl=60)
def _load_cable_per_incident(date_from, date_to):
    return _get_service().get_cable_per_incident(date_from, date_to)


@st.cache_data(ttl=60)
def _load_route_comparison(date_from, date_to, material_group):
    return _get_service().compare_routes_consumption(date_from, date_to, material_group)


@st.cache_data(ttl=60)
def _load_usage_summary(date_from, date_to, route_id, cable_type, cause_id):
    return _get_service().get_material_usage_summary(date_from, date_to, route_id, cable_type, cause_id)


@st.cache_data(ttl=60)
def _load_filter_options():
    return _get_filter_service().get_filter_options()


def _to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Vật tư") -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buffer.getvalue()


def _date_range_picker(key_prefix: str, default_days: int = 90):
    c1, c2 = st.columns(2)
    with c1:
        date_from = st.date_input(
            "Từ ngày", value=date.today() - timedelta(days=default_days), key=f"{key_prefix}_from"
        )
    with c2:
        date_to = st.date_input("Đến ngày", value=date.today(), key=f"{key_prefix}_to")
    return date_from, date_to


def _render_catalog_tab() -> None:
    groups = _load_groups()
    c1, c2, c3 = st.columns([2, 2, 3])
    with c1:
        group = st.selectbox(
            "Nhóm vật tư", options=[None] + groups,
            format_func=lambda g: "Tất cả" if g is None else MATERIAL_GROUP_LABELS.get(g, g),
            key="mat_group",
        )
    with c2:
        active_only = st.checkbox("Chỉ hiện đang dùng", value=False, key="mat_active_only")
    with c3:
        keyword = st.text_input("Tìm theo mã / tên vật tư", "", key="mat_keyword")

    df = _load_catalog(group, active_only, keyword or None)
    st.caption(f"Tìm thấy **{len(df)}** vật tư.")
    if df.empty:
        st.info("Không có vật tư nào khớp.")
        return

    st.dataframe(
        df.rename(columns={
            "ma_vat_tu": "Mã vật tư", "ten_vat_tu": "Tên vật tư", "nhom_vat_tu": "Nhóm vật tư",
            "don_vi_tinh": "Đơn vị tính", "trang_thai": "Trạng thái",
        }),
        hide_index=True, width="stretch",
    )


def _render_consumption_tab() -> None:
    date_from, date_to = _date_range_picker("mat_consumption")

    st.subheader("🧰 Vật tư / sự cố")
    per_incident_df = _load_material_per_incident(date_from, date_to)
    if per_incident_df.empty:
        st.info("Chưa có dữ liệu.")
    else:
        st.dataframe(
            per_incident_df.rename(columns={
                "vat_tu": "Vật tư", "don_vi": "Đơn vị", "so_su_co_dung": "Số sự cố dùng",
                "tong_so_luong": "Tổng số lượng", "binh_quan_moi_su_co": "Bình quân / sự cố",
            }),
            hide_index=True, width="stretch",
        )

    st.subheader("🔌 Cáp / sự cố")
    cable_stat = _load_cable_per_incident(date_from, date_to)
    c1, c2, c3 = st.columns(3)
    c1.metric("Số sự cố dùng cáp", int(cable_stat["so_su_co"] or 0))
    c2.metric("Tổng mét cáp", f"{float(cable_stat['tong_met_cap'] or 0):,.0f} m")
    c3.metric("Bình quân / sự cố", f"{float(cable_stat['binh_quan_met_moi_su_co'] or 0):,.1f} m")

    st.subheader("📊 So sánh mức tiêu hao giữa các tuyến")
    groups = _load_groups()
    compare_group = st.selectbox(
        "Lọc theo nhóm vật tư", options=[None] + groups,
        format_func=lambda g: "Tất cả" if g is None else MATERIAL_GROUP_LABELS.get(g, g),
        key="mat_compare_group",
    )
    route_compare_df = _load_route_comparison(date_from, date_to, compare_group)
    if route_compare_df.empty:
        st.info("Chưa có dữ liệu.")
    else:
        fig = px.bar(
            route_compare_df.sort_values("tong_tieu_hao"), x="tong_tieu_hao", y="tuyen",
            orientation="h", labels={"tong_tieu_hao": "Tổng tiêu hao", "tuyen": "Tuyến"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch", key="mat_route_comparison")


def _render_usage_summary_tab() -> None:
    date_from, date_to = _date_range_picker("mat_usage")

    options = _load_filter_options()
    routes_df = options["routes"]
    causes_df = options["causes"]

    c1, c2, c3 = st.columns(3)
    with c1:
        route_choice = st.selectbox(
            "Tuyến", options=[None] + routes_df["route_id"].tolist(),
            format_func=lambda rid: "Tất cả" if rid is None
            else routes_df.loc[routes_df["route_id"] == rid, "route_name"].iloc[0],
            key="mat_usage_route",
        )
    with c2:
        cable_type_choice = st.selectbox(
            "Loại cáp", options=[None, "F8", "ADSS"],
            format_func=lambda c: "Tất cả" if c is None else c,
            key="mat_usage_cable",
        )
    with c3:
        cause_choice = st.selectbox(
            "Nguyên nhân", options=[None] + causes_df["cause_id"].tolist(),
            format_func=lambda cid: "Tất cả" if cid is None
            else causes_df.loc[causes_df["cause_id"] == cid, "cause_name"].iloc[0],
            key="mat_usage_cause",
        )

    df = _load_usage_summary(date_from, date_to, route_choice, cable_type_choice, cause_choice)
    st.caption(f"Tìm thấy **{len(df)}** loại vật tư được sử dụng.")
    if df.empty:
        st.info("Không có dữ liệu khớp bộ lọc.")
        return

    display_df = df.rename(columns={
        "ma_vat_tu": "Mã vật tư", "ten_vat_tu": "Tên vật tư", "don_vi": "Đơn vị",
        "tong_su_dung": "Tổng sử dụng", "so_su_co": "Số sự cố",
    })
    st.download_button(
        "📥 Xuất Excel",
        data=_to_excel_bytes(display_df),
        file_name=f"thong_ke_vat_tu_{date.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="mat_export_btn",
    )
    st.dataframe(display_df, hide_index=True, width="stretch")


def render() -> None:
    st.title("🧰 Vật tư")

    if st.button("🔄 Làm mới dữ liệu", key="mat_refresh"):
        st.cache_data.clear()

    tab1, tab2, tab3 = st.tabs(["Danh mục vật tư", "Phân tích tiêu hao", "Thống kê sử dụng"])
    with tab1:
        _render_catalog_tab()
    with tab2:
        _render_consumption_tab()
    with tab3:
        _render_usage_summary_tab()
