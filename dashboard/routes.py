import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from dashboard import incident_detail
from services.route_report_service import RouteReportService
from utils.formatters import to_local
from utils.kml_loader import load_route_path

STATUS_LABELS = {
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
def _get_service() -> RouteReportService:
    return RouteReportService()


@st.cache_data(ttl=60)
def _load_route_list(keyword, status):
    return _get_service().get_route_list(keyword, status)


@st.cache_data(ttl=60)
def _load_route_detail(route_id):
    return _get_service().get_route_detail(route_id)


@st.cache_data(ttl=60)
def _load_route_history(route_id):
    return _get_service().get_route_incident_history(route_id)


@st.cache_data(ttl=60)
def _load_route_causes(route_id):
    return _get_service().get_route_cause_breakdown(route_id)


@st.cache_data(ttl=60)
def _load_route_materials(route_id):
    return _get_service().get_route_materials_used(route_id)


@st.cache_data(ttl=60)
def _load_route_coords(route_id):
    return _get_service().get_route_incidents_with_coords(route_id)


@st.cache_data(ttl=300)
def _load_route_kml(route_code, route_name):
    return load_route_path(route_code, route_name)


@st.dialog("Chi tiết sự cố", width="large")
def _show_detail_dialog(incident_id: int) -> None:
    incident_detail.render(incident_id)


def _render_list_tab() -> None:
    c1, c2 = st.columns([3, 1])
    with c1:
        keyword = st.text_input("Tìm theo mã / tên tuyến", "", key="route_keyword")
    with c2:
        status = st.selectbox(
            "Trạng thái", options=[None, "ACTIVE", "INACTIVE"],
            format_func=lambda s: "Tất cả" if s is None else ("Đang hoạt động" if s == "ACTIVE" else "Ngừng hoạt động"),
            key="route_status",
        )

    df = _load_route_list(keyword or None, status)
    st.caption(f"Tìm thấy **{len(df)}** tuyến.")
    if df.empty:
        st.info("Không có tuyến nào khớp.")
        return

    st.dataframe(
        df.drop(columns=["route_id"]).rename(columns={
            "ma_tuyen": "Mã tuyến", "ten_tuyen": "Tên tuyến", "loai_tuyen": "Route type",
            "chieu_dai_km": "Chiều dài (km)", "loai_cap": "Loại cáp", "so_fo": "Số FO",
            "province": "Tỉnh/thành", "trang_thai": "Trạng thái", "so_su_co": "Số sự cố",
        }),
        hide_index=True, width="stretch",
    )


def _render_detail_tab() -> None:
    df = _load_route_list(None, None)
    if df.empty:
        st.info("Chưa có tuyến nào trong hệ thống.")
        return

    route_id = st.selectbox(
        "Chọn tuyến", options=df["route_id"].tolist(),
        format_func=lambda rid: df.loc[df["route_id"] == rid, "ten_tuyen"].iloc[0],
        key="route_detail_pick",
    )

    detail = _load_route_detail(route_id)
    if detail is None:
        st.error("Không tìm thấy tuyến này.")
        return

    st.subheader(f"🛣 {detail['route_name']} ({detail['route_code']})")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Chiều dài", f"{detail['length_km']:.2f} km" if detail["length_km"] else "—")
    col2.metric("Loại cáp", f"{detail['cable_type']}-{detail['fiber_count']}FO")
    col3.metric("Route type", detail["route_type"] or "—")
    col4.metric("Tổng sự cố", int(detail["total_incidents"]))

    if detail["description"]:
        st.caption(detail["description"])

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**🔎 Nguyên nhân sự cố trên tuyến**")
        cause_df = _load_route_causes(route_id)
        if cause_df.empty:
            st.info("Chưa có sự cố nào.")
        else:
            fig = px.pie(cause_df, names="nguyen_nhan", values="so_luong", hole=0.4)
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch", key="route_cause_pie")

    with col_b:
        st.markdown("**🧰 Vật tư đã sử dụng**")
        materials_df = _load_route_materials(route_id)
        if materials_df.empty:
            st.info("Chưa sử dụng vật tư nào.")
        else:
            st.dataframe(
                materials_df.rename(columns={"vat_tu": "Vật tư", "don_vi": "Đơn vị", "tong_su_dung": "Tổng sử dụng"}),
                hide_index=True, width="stretch",
            )

    st.divider()
    st.markdown("**📋 Lịch sử sự cố**")
    history_df = _load_route_history(route_id)
    if history_df.empty:
        st.info("Chưa có sự cố nào trên tuyến này.")
        return

    display_df = history_df.copy()
    display_df["trang_thai"] = display_df["trang_thai"].map(lambda s: STATUS_LABELS.get(s, s))
    display_df["thoi_gian_bao_cao"] = display_df["thoi_gian_bao_cao"].apply(
        lambda dt: to_local(dt).strftime("%d/%m/%Y %H:%M") if pd.notna(dt) else ""
    )
    st.dataframe(
        display_df.rename(columns={
            "ma_su_co": "Mã sự cố", "trang_thai": "Trạng thái", "loai_su_co": "Loại sự cố",
            "nguyen_nhan": "Nguyên nhân", "doan_khac_phuc": "Đoạn khắc phục", "thoi_gian_bao_cao": "Thời gian",
        }),
        hide_index=True, width="stretch",
    )


def _render_map_tab() -> None:
    df = _load_route_list(None, None)
    if df.empty:
        st.info("Chưa có tuyến nào trong hệ thống.")
        return

    route_id = st.selectbox(
        "Chọn tuyến", options=df["route_id"].tolist(),
        format_func=lambda rid: df.loc[df["route_id"] == rid, "ten_tuyen"].iloc[0],
        key="route_map_pick",
    )
    route_row = df.loc[df["route_id"] == route_id].iloc[0]

    kml_lines = _load_route_kml(route_row["ma_tuyen"], route_row["ten_tuyen"])
    incidents_df = _load_route_coords(route_id)

    if kml_lines:
        all_points = [pt for line in kml_lines for pt in line]
        center = (
            sum(p[0] for p in all_points) / len(all_points),
            sum(p[1] for p in all_points) / len(all_points),
        )
    elif not incidents_df.empty:
        center = (incidents_df["latitude"].mean(), incidents_df["longitude"].mean())
    else:
        center = DEFAULT_CENTER

    fmap = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap")

    if kml_lines:
        for line in kml_lines:
            folium.PolyLine(locations=line, color="#1f77b4", weight=4, opacity=0.8).add_to(fmap)
        st.caption(f"Đã tải {len(kml_lines)} đoạn tuyến từ file KML.")
    else:
        st.warning("Không tìm thấy file KML cho tuyến này — chỉ hiển thị vị trí các sự cố.")

    for _, row in incidents_df.iterrows():
        color = STATUS_COLORS.get(row["trang_thai"], "blue")
        reported_local = to_local(row["reported_at"])
        popup_html = (
            f"<b>{row['ma_su_co']}</b><br>"
            f"Trạng thái: {STATUS_LABELS.get(row['trang_thai'], row['trang_thai'])}<br>"
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
        match = incidents_df[incidents_df["ma_su_co"] == clicked_code]
        if not match.empty and st.button(f"🔍 Xem chi tiết {clicked_code}", key="route_map_view_btn"):
            _show_detail_dialog(int(match.iloc[0]["incident_id"]))


def render() -> None:
    st.title("🛣️ Tuyến cáp")

    if st.button("🔄 Làm mới dữ liệu", key="route_refresh"):
        st.cache_data.clear()

    tab1, tab2, tab3 = st.tabs(["Danh sách tuyến", "Chi tiết tuyến", "Bản đồ tuyến"])
    with tab1:
        _render_list_tab()
    with tab2:
        _render_detail_tab()
    with tab3:
        _render_map_tab()
