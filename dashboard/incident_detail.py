import streamlit as st

from services.report_service import ReportService
from utils.formatters import to_local

STATUS_LABELS = {
    "DRAFT": "🟡 Đang xử lý",
    "COMPLETED": "🟢 Đã hoàn tất",
    "CANCELLED": "🔴 Đã huỷ",
}


@st.cache_resource
def _get_service() -> ReportService:
    return ReportService()


def _render_photo(cloudinary_url: str) -> None:
    """Nhúng thẳng URL Cloudinary - trình duyệt người xem tự tải ảnh,
    server Streamlit không xử lý/tải ảnh."""
    st.image(cloudinary_url, width="stretch")


def render(incident_id: int) -> None:
    service = _get_service()
    incident = service.get_incident_detail(incident_id)

    if incident is None:
        st.error("Không tìm thấy sự cố này.")
        return

    status_label = STATUS_LABELS.get(incident["status"], incident["status"])
    st.subheader(f"📄 {incident['incident_code']} — {status_label}")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Tuyến:** {incident['route_name']} "
                    f"({incident['cable_type']}-{incident['fiber_count']}FO)")
        st.markdown(f"**Loại sự cố:** {incident['type_name']}")
        st.markdown(f"**Nguyên nhân:** {incident['cause_name'] or '—'}")
        st.markdown(f"**Đoạn khắc phục:** {incident['span_name']}")
    with col2:
        st.markdown(f"**Người báo cáo:** {incident['reporter_name']}"
                    + (f" ({incident['team_name']})" if incident["team_name"] else ""))
        reported_local = to_local(incident["reported_at"])
        st.markdown(f"**Thời gian báo cáo:** {reported_local:%d/%m/%Y %H:%M}")
        if incident["completed_at"]:
            completed_local = to_local(incident["completed_at"])
            st.markdown(f"**Thời gian hoàn tất:** {completed_local:%d/%m/%Y %H:%M}")
        st.markdown(
            f"**Vị trí:** {incident['latitude']:.6f}, {incident['longitude']:.6f} "
            f"[Xem trên Google Maps](https://www.google.com/maps?q={incident['latitude']},{incident['longitude']})"
        )

    if incident["description"]:
        st.markdown(f"**Mô tả:** {incident['description']}")

    st.divider()
    st.markdown("**🧰 Vật tư sử dụng**")
    materials_df = service.get_incident_materials(incident_id)
    if materials_df.empty:
        st.caption("Không có vật tư nào được ghi nhận.")
    else:
        st.dataframe(materials_df, hide_index=True, width="stretch")

    st.divider()
    st.markdown("**📷 Hình ảnh**")
    photos = service.get_incident_photos(incident_id)
    before_photos = [p for p in photos if p["photo_type"] == "BEFORE"]
    after_photos = [p for p in photos if p["photo_type"] == "AFTER"]

    col_before, col_after = st.columns(2)
    with col_before:
        st.caption(f"Trước khắc phục ({len(before_photos)})")
        for p in before_photos:
            _render_photo(p["cloudinary_url"])
    with col_after:
        st.caption(f"Sau khắc phục ({len(after_photos)})")
        for p in after_photos:
            _render_photo(p["cloudinary_url"])
