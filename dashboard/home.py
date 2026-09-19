import plotly.express as px
import streamlit as st

from services.report_service import ReportService


@st.cache_resource
def _get_service() -> ReportService:
    return ReportService()


@st.cache_data(ttl=60)
def _load_kpis():
    return _get_service().get_summary_kpis()


@st.cache_data(ttl=60)
def _load_daily_counts(days: int):
    return _get_service().get_daily_counts(days)


@st.cache_data(ttl=60)
def _load_cause_stats():
    return _get_service().get_cause_stats()


@st.cache_data(ttl=60)
def _load_top_routes(limit: int):
    return _get_service().get_top_routes(limit)


def render() -> None:
    st.title("📊 Tổng quan")

    if st.button("🔄 Làm mới dữ liệu"):
        st.cache_data.clear()

    kpis = _load_kpis()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Tổng số sự cố", kpis["total"])
    col2.metric("Đang xử lý", kpis["draft"])
    col3.metric("Đã hoàn tất", kpis["completed"])
    col4.metric("Hôm nay", kpis["today"])
    col5.metric("7 ngày qua", kpis["last_7_days"])

    st.divider()

    days = st.slider("Số ngày hiển thị", min_value=7, max_value=90, value=30, step=1)
    daily_df = _load_daily_counts(days)

    st.subheader("📅 Sự cố theo ngày")
    if daily_df.empty:
        st.info("Chưa có dữ liệu.")
    else:
        fig = px.bar(
            daily_df, x="ngay", y="so_su_co",
            labels={"ngay": "Ngày", "so_su_co": "Số sự cố"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch", key="home_daily_trend")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("🔎 Nguyên nhân sự cố")
        cause_df = _load_cause_stats()
        if cause_df.empty:
            st.info("Chưa có dữ liệu.")
        else:
            fig = px.pie(cause_df, names="nguyen_nhan", values="so_luong", hole=0.4)
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch", key="home_cause_pie")

    with col_b:
        st.subheader("🛣 Tuyến có nhiều sự cố nhất")
        top_n = st.slider("Top", min_value=5, max_value=20, value=10, step=1)
        route_df = _load_top_routes(top_n)
        if route_df.empty:
            st.info("Chưa có dữ liệu.")
        else:
            fig = px.bar(
                route_df.sort_values("so_su_co"), x="so_su_co", y="tuyen",
                orientation="h",
                labels={"so_su_co": "Số sự cố", "tuyen": "Tuyến"},
            )
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch", key="home_top_routes")
