import io
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from dashboard import incident_detail
from services.report_service import ReportService
from utils.formatters import to_local

STATUS_OPTIONS = {
    "": "Tất cả",
    "DRAFT": "Đang xử lý",
    "COMPLETED": "Đã hoàn tất",
    "CANCELLED": "Đã huỷ",
}


@st.cache_resource
def _get_service() -> ReportService:
    return ReportService()


@st.cache_data(ttl=60)
def _load_filter_options():
    return _get_service().get_filter_options()


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Sự cố")
    return buffer.getvalue()


@st.dialog("Chi tiết sự cố", width="large")
def _show_detail_dialog(incident_id: int) -> None:
    incident_detail.render(incident_id)


def render() -> None:
    st.title("🚨 Danh sách sự cố")

    options = _load_filter_options()
    routes_df = options["routes"]
    types_df = options["types"]
    causes_df = options["causes"]

    with st.expander("🔍 Bộ lọc", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            date_from = st.date_input("Từ ngày", value=date.today() - timedelta(days=30))
        with c2:
            date_to = st.date_input("Đến ngày", value=date.today())
        with c3:
            status_key = st.selectbox(
                "Trạng thái", options=list(STATUS_OPTIONS.keys()),
                format_func=lambda k: STATUS_OPTIONS[k],
            )

        c4, c5, c6 = st.columns(3)
        with c4:
            route_choice = st.selectbox(
                "Tuyến", options=[None] + routes_df["route_id"].tolist(),
                format_func=lambda rid: "Tất cả" if rid is None
                else routes_df.loc[routes_df["route_id"] == rid, "route_name"].iloc[0],
            )
        with c5:
            type_choice = st.selectbox(
                "Loại sự cố", options=[None] + types_df["incident_type_id"].tolist(),
                format_func=lambda tid: "Tất cả" if tid is None
                else types_df.loc[types_df["incident_type_id"] == tid, "type_name"].iloc[0],
            )
        with c6:
            cause_choice = st.selectbox(
                "Nguyên nhân", options=[None] + causes_df["cause_id"].tolist(),
                format_func=lambda cid: "Tất cả" if cid is None
                else causes_df.loc[causes_df["cause_id"] == cid, "cause_name"].iloc[0],
            )

        keyword = st.text_input("Tìm theo mã sự cố / tên tuyến", "")

    df = _get_service().search_incidents(
        date_from=date_from,
        date_to=date_to,
        status=status_key or None,
        route_id=route_choice,
        incident_type_id=type_choice,
        cause_id=cause_choice,
        keyword=keyword or None,
    )

    st.caption(f"Tìm thấy **{len(df)}** sự cố.")

    if df.empty:
        st.info("Không có sự cố nào khớp bộ lọc.")
        return

    display_df = df.copy()
    display_df["trang_thai"] = display_df["trang_thai"].map(
        lambda s: STATUS_OPTIONS.get(s, s)
    )
    display_df["thoi_gian_bao_cao"] = display_df["thoi_gian_bao_cao"].apply(
        lambda dt: to_local(dt).strftime("%d/%m/%Y %H:%M") if pd.notna(dt) else ""
    )
    display_df["thoi_gian_hoan_tat"] = display_df["thoi_gian_hoan_tat"].apply(
        lambda dt: to_local(dt).strftime("%d/%m/%Y %H:%M") if pd.notna(dt) else ""
    )

    export_cols = [
        "ma_su_co", "trang_thai", "tuyen", "loai_su_co", "nguyen_nhan",
        "doan_khac_phuc", "nguoi_bao_cao", "thoi_gian_bao_cao", "thoi_gian_hoan_tat",
    ]

    col_export, _ = st.columns([1, 5])
    with col_export:
        st.download_button(
            "📥 Xuất Excel",
            data=_to_excel_bytes(display_df[export_cols]),
            file_name=f"su_co_{date.today():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.dataframe(display_df[export_cols], hide_index=True, width="stretch")

    st.divider()
    st.subheader("🔍 Xem chi tiết 1 sự cố")
    code_options = display_df["ma_su_co"].tolist()
    col_pick, col_btn = st.columns([3, 1])
    with col_pick:
        selected_code = st.selectbox("Chọn mã sự cố", options=code_options, label_visibility="collapsed")
    with col_btn:
        view_clicked = st.button("Xem chi tiết + ảnh", type="primary", width="stretch")

    if view_clicked and selected_code:
        incident_id = int(display_df.loc[display_df["ma_su_co"] == selected_code, "incident_id"].iloc[0])
        _show_detail_dialog(incident_id)
