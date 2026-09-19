from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import incident_detail
from services.analytics_service import AnalyticsService

GRANULARITY_LABELS = {"day": "Ngày", "week": "Tuần", "month": "Tháng"}


@st.cache_resource
def _get_service() -> AnalyticsService:
    return AnalyticsService()


@st.cache_data(ttl=60)
def _load_trend(date_from, date_to, granularity):
    return _get_service().get_incident_trend(date_from, date_to, granularity)


@st.cache_data(ttl=60)
def _load_by_cause(date_from, date_to):
    return _get_service().get_by_cause(date_from, date_to)


@st.cache_data(ttl=60)
def _load_by_route_type(date_from, date_to):
    return _get_service().get_by_route_type(date_from, date_to)


@st.cache_data(ttl=60)
def _load_moving_avg(date_from, date_to, window):
    return _get_service().get_trend_with_moving_avg(date_from, date_to, window)


@st.cache_data(ttl=60)
def _load_cause_share(date_from, date_to):
    return _get_service().get_cause_share(date_from, date_to)


@st.cache_data(ttl=60)
def _load_cause_trend_monthly(date_from, date_to):
    return _get_service().get_cause_trend_monthly(date_from, date_to)


@st.cache_data(ttl=300)
def _load_causes():
    return _get_service().get_causes()


@st.cache_data(ttl=60)
def _load_routes_for_cause(cause_id, date_from, date_to):
    return _get_service().get_routes_for_cause(cause_id, date_from, date_to)


@st.cache_data(ttl=60)
def _load_locations(cause_id, route_id, date_from, date_to):
    return _get_service().get_locations_for_cause_route(cause_id, route_id, date_from, date_to)


@st.cache_data(ttl=120)
def _load_route_anomalies(recent_days, baseline_days):
    return _get_service().detect_route_anomalies(recent_days, baseline_days)


@st.cache_data(ttl=120)
def _load_cause_anomalies(recent_days, baseline_days):
    return _get_service().detect_cause_anomalies(recent_days, baseline_days)


@st.cache_data(ttl=120)
def _load_material_anomalies(recent_days, baseline_days):
    return _get_service().detect_material_anomalies(recent_days, baseline_days)


@st.dialog("Chi tiết sự cố", width="large")
def _show_detail_dialog(incident_id: int) -> None:
    incident_detail.render(incident_id)


def _date_range_picker(key_prefix: str, default_days: int = 90):
    c1, c2 = st.columns(2)
    with c1:
        date_from = st.date_input(
            "Từ ngày", value=date.today() - timedelta(days=default_days), key=f"{key_prefix}_from"
        )
    with c2:
        date_to = st.date_input("Đến ngày", value=date.today(), key=f"{key_prefix}_to")
    return date_from, date_to


def _render_overview_tab() -> None:
    date_from, date_to = _date_range_picker("an_overview")
    granularity = st.radio(
        "Đơn vị thời gian", options=["day", "week", "month"],
        format_func=lambda g: GRANULARITY_LABELS[g], horizontal=True, key="an_gran",
    )

    st.subheader("📅 Sự cố theo thời gian")
    trend_df = _load_trend(date_from, date_to, granularity)
    if trend_df.empty:
        st.info("Chưa có dữ liệu.")
    else:
        fig = px.bar(trend_df, x="ky", y="so_su_co", labels={"ky": "Kỳ", "so_su_co": "Số sự cố"})
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch", key="an_overview_trend")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🔎 Theo nguyên nhân")
        cause_df = _load_by_cause(date_from, date_to)
        if cause_df.empty:
            st.info("Chưa có dữ liệu.")
        else:
            fig = px.pie(cause_df, names="nguyen_nhan", values="so_luong", hole=0.4)
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch", key="an_overview_cause_pie")

    with col_b:
        st.subheader("🛣 Theo loại tuyến")
        rt_df = _load_by_route_type(date_from, date_to)
        if rt_df.empty:
            st.info("Chưa có dữ liệu.")
        else:
            fig = px.bar(
                rt_df, x="loai_tuyen", y="so_su_co",
                labels={"loai_tuyen": "Loại tuyến", "so_su_co": "Số sự cố"},
            )
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch", key="an_overview_route_type")

    st.subheader("📈 Xu hướng sự cố (trung bình động)")
    window = st.slider("Cửa sổ trung bình động (ngày)", min_value=3, max_value=30, value=7, key="an_window")
    ma_df = _load_moving_avg(date_from, date_to, window)
    if ma_df.empty:
        st.info("Chưa có dữ liệu.")
    else:
        fig = px.line(
            ma_df, x="ky", y=["so_su_co", "trung_binh_dong"],
            labels={"ky": "Ngày", "value": "Số sự cố", "variable": ""},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch", key="an_overview_moving_avg")


def _render_cause_analysis_tab() -> None:
    date_from, date_to = _date_range_picker("an_cause")

    st.subheader("🧮 Tỷ trọng từng nguyên nhân")
    share_df = _load_cause_share(date_from, date_to)
    if share_df.empty:
        st.info("Chưa có dữ liệu.")
    else:
        st.dataframe(
            share_df.rename(columns={
                "nguyen_nhan": "Nguyên nhân", "so_luong": "Số lượng", "ty_trong": "Tỷ trọng (%)",
            }),
            hide_index=True, width="stretch",
        )
        fig = px.pie(share_df, names="nguyen_nhan", values="so_luong", hole=0.4)
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch", key="an_cause_share_pie")

    st.subheader("📈 Xu hướng nguyên nhân theo thời gian")
    trend_df = _load_cause_trend_monthly(date_from, date_to)
    if trend_df.empty:
        st.info("Chưa có dữ liệu.")
    else:
        pivot = trend_df.pivot(index="thang", columns="nguyen_nhan", values="so_luong").fillna(0)
        fig = px.line(
            pivot, x=pivot.index, y=pivot.columns,
            labels={"thang": "Tháng", "value": "Số lượng", "variable": "Nguyên nhân"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch", key="an_cause_trend_monthly")

    st.divider()
    st.subheader("🔬 Drill-down: Nguyên nhân → Tuyến → Địa điểm → Sự cố")
    causes_df = _load_causes()
    if causes_df.empty:
        st.info("Chưa có nguyên nhân nào.")
        return

    cause_id = st.selectbox(
        "1️⃣ Chọn nguyên nhân", options=causes_df["cause_id"].tolist(),
        format_func=lambda cid: causes_df.loc[causes_df["cause_id"] == cid, "cause_name"].iloc[0],
        key="dd_cause",
    )

    routes_df = _load_routes_for_cause(cause_id, date_from, date_to)
    if routes_df.empty:
        st.info("Không có tuyến nào ghi nhận sự cố với nguyên nhân này trong khoảng thời gian đã chọn.")
        return

    route_id = st.selectbox(
        "2️⃣ Chọn tuyến", options=routes_df["route_id"].tolist(),
        format_func=lambda rid: (
            f"{routes_df.loc[routes_df['route_id'] == rid, 'route_name'].iloc[0]} "
            f"({int(routes_df.loc[routes_df['route_id'] == rid, 'so_su_co'].iloc[0])} sự cố)"
        ),
        key="dd_route",
    )

    locations_df = _load_locations(cause_id, route_id, date_from, date_to)
    if locations_df.empty:
        st.info("Không có sự cố nào khớp.")
        return

    st.markdown("**3️⃣ Địa điểm / Sự cố**")
    display_df = locations_df.copy()
    display_df["thoi_gian_bao_cao"] = display_df["reported_at"].apply(
        lambda dt: dt.strftime("%d/%m/%Y %H:%M") if pd.notna(dt) else ""
    )
    st.dataframe(
        display_df[["incident_code", "doan_khac_phuc", "latitude", "longitude", "thoi_gian_bao_cao"]].rename(
            columns={
                "incident_code": "Mã sự cố", "doan_khac_phuc": "Đoạn khắc phục",
                "latitude": "Vĩ độ", "longitude": "Kinh độ", "thoi_gian_bao_cao": "Thời gian",
            }
        ),
        hide_index=True, width="stretch",
    )

    code_options = display_df["incident_code"].tolist()
    col_pick, col_btn = st.columns([3, 1])
    with col_pick:
        selected_code = st.selectbox("4️⃣ Xem chi tiết sự cố", options=code_options, key="dd_incident")
    with col_btn:
        view_clicked = st.button("Xem chi tiết + ảnh", type="primary", width="stretch", key="dd_view_btn")

    if view_clicked and selected_code:
        incident_id = int(display_df.loc[display_df["incident_code"] == selected_code, "incident_id"].iloc[0])
        _show_detail_dialog(incident_id)


def _render_anomaly_table(
    df: pd.DataFrame, threshold: float, name_col: str, name_label: str,
    recent_label: str, extra_cols: dict
) -> None:
    if df.empty:
        st.success("Không phát hiện bất thường.")
        return
    filtered = df[df["ty_le_tang"] >= threshold]
    if filtered.empty:
        st.success("Không phát hiện bất thường với ngưỡng hiện tại.")
        return
    rename_map = {
        name_col: name_label, "gan_day": recent_label,
        "binh_quan_nen_quy_doi": "Bình quân nền (quy đổi)", "ty_le_tang": "Tỷ lệ tăng (lần)",
    }
    rename_map.update(extra_cols)
    cols = list(rename_map.values())
    st.dataframe(filtered.rename(columns=rename_map)[cols], hide_index=True, width="stretch")


def _render_trend_analysis_tab() -> None:
    st.caption("So sánh số liệu gần đây với nền trước đó để phát hiện bất thường.")
    c1, c2, c3 = st.columns(3)
    with c1:
        recent_days = st.number_input("Số ngày gần đây", min_value=7, max_value=90, value=30, key="anom_recent")
    with c2:
        baseline_days = st.number_input(
            "Tổng số ngày nền (gồm cả gần đây)", min_value=int(recent_days) + 7, max_value=365,
            value=90, key="anom_baseline",
        )
    with c3:
        threshold = st.slider("Ngưỡng tăng (lần)", min_value=1.2, max_value=5.0, value=2.0, step=0.1, key="anom_threshold")

    st.subheader("🛣 Tuyến có xu hướng sự cố bất thường")
    route_df = _load_route_anomalies(int(recent_days), int(baseline_days))
    _render_anomaly_table(
        route_df, threshold, "route_name", "Tuyến", f"{int(recent_days)} ngày gần đây", {}
    )

    st.subheader("🔎 Nguyên nhân có xu hướng tăng")
    cause_df = _load_cause_anomalies(int(recent_days), int(baseline_days))
    _render_anomaly_table(
        cause_df, threshold, "nguyen_nhan", "Nguyên nhân", f"{int(recent_days)} ngày gần đây", {}
    )

    st.subheader("🧰 Vật tư có mức tiêu hao bất thường")
    material_df = _load_material_anomalies(int(recent_days), int(baseline_days))
    _render_anomaly_table(
        material_df, threshold, "material_name", "Vật tư",
        f"Tiêu hao {int(recent_days)} ngày gần đây", {"unit": "Đơn vị"},
    )


def render() -> None:
    st.title("📈 Phân tích")

    if st.button("🔄 Làm mới dữ liệu", key="an_refresh"):
        st.cache_data.clear()

    tab1, tab2, tab3 = st.tabs(["Tổng quan sự cố", "Phân tích nguyên nhân", "Phân tích xu hướng"])
    with tab1:
        _render_overview_tab()
    with tab2:
        _render_cause_analysis_tab()
    with tab3:
        _render_trend_analysis_tab()
