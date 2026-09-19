from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from config.settings import settings

_LOCAL_TZ = ZoneInfo(settings.timezone)


def to_local(dt: Optional[datetime]) -> Optional[datetime]:
    """Chuyển datetime (tz-aware, thường là UTC từ asyncpg với cột TIMESTAMPTZ)
    sang giờ địa phương (APP_TIMEZONE) để hiển thị cho người dùng.
    Nếu dt là naive (dữ liệu cũ / cột không timezone) thì coi như đã là giờ
    địa phương sẵn, chỉ gắn tzinfo mà không đổi giá trị."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_LOCAL_TZ)
    return dt.astimezone(_LOCAL_TZ)


def format_quantity(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_material_line(name: str, unit: str, qty: Decimal) -> str:
    return f"• {name}: {format_quantity(qty)} {unit}"


def format_incident_summary(data: Dict) -> str:
    lines = [
        "📋 <b>Xác nhận báo cáo sự cố</b>",
        f"Tuyến: {data['route_name']} ({data['cable_type']}-{data['fiber_count']}FO)",
        f"Loại sự cố: {data['incident_type_name']}",
    ]
    if data.get("cause_name"):
        lines.append(f"Nguyên nhân: {data['cause_name']}")
    lines.append(f"Đoạn khắc phục: {data['span_name']}")
    if data.get("description"):
        lines.append(f"Mô tả: {data['description']}")

    materials: List[dict] = [m for m in data["materials"] if m["qty"] > 0]
    if materials:
        lines.append("")
        lines.append("🧰 Vật tư sử dụng:")
        for m in materials:
            lines.append(format_material_line(m["name"], m["unit"], m["qty"]))

    lines.append("")
    lines.append(f"📍 Vị trí: {data['latitude']:.6f}, {data['longitude']:.6f}")
    lines.append(f"📷 Ảnh trước: {data['before_count']} | Ảnh sau: {data['after_count']}")
    return "\n".join(lines)


STATUS_LABELS = {
    "DRAFT": "Đang xử lý",
    "COMPLETED": "Đã hoàn tất",
    "CANCELLED": "Đã huỷ",
}


def format_incident_detail(incident, materials: List, photos: List) -> str:
    status_label = STATUS_LABELS.get(incident["status"], incident["status"])
    lines = [
        f"📄 <b>Sự cố {incident['incident_code']}</b> — {status_label}",
        f"Tuyến: {incident['route_name']} ({incident['cable_type']}-{incident['fiber_count']}FO)",
        f"Loại sự cố: {incident['type_name']}",
    ]
    if incident["cause_name"]:
        lines.append(f"Nguyên nhân: {incident['cause_name']}")
    lines.append(f"Đoạn khắc phục: {incident['span_name']}")
    if incident["description"]:
        lines.append(f"Mô tả: {incident['description']}")
    lines.append(f"Người báo cáo: {incident['reporter_name']}")
    lines.append(f"Thời gian báo cáo: {to_local(incident['reported_at']):%d/%m/%Y %H:%M}")
    if incident["completed_at"]:
        lines.append(f"Thời gian hoàn tất: {to_local(incident['completed_at']):%d/%m/%Y %H:%M}")

    if materials:
        lines.append("")
        lines.append("🧰 Vật tư sử dụng:")
        for m in materials:
            lines.append(format_material_line(m["material_name"], m["unit"], m["quantity"]))

    lines.append("")
    lines.append(f"📍 Vị trí: {incident['latitude']:.6f}, {incident['longitude']:.6f}")

    before_count = sum(1 for p in photos if p["photo_type"] == "BEFORE")
    after_count = sum(1 for p in photos if p["photo_type"] == "AFTER")
    lines.append(f"📷 Ảnh trước: {before_count} | Ảnh sau: {after_count}")
    return "\n".join(lines)
