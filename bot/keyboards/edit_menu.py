from typing import Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# (khoá hiển thị trong inc, callback key ngắn, nhãn hiển thị)
_FIELDS = [
    ("route_id", "route", "🛣 Tuyến"),
    ("incident_type_id", "itype", "⚠️ Loại sự cố"),
    ("repair_span_type_id", "span", "📏 Đoạn khắc phục"),
    ("selected", "materials", "🧰 Vật tư"),
    ("description", "description", "✏️ Mô tả"),
    ("latitude", "location", "📍 Vị trí GPS"),
    ("before_photos", "photo_before", "📷 Ảnh trước"),
    ("after_photos", "photo_after", "📷 Ảnh sau"),
]


def _has_value(inc: Dict, data_key: str) -> bool:
    if data_key in ("before_photos", "after_photos"):
        return len(inc.get(data_key, [])) > 0
    if data_key == "selected":
        return bool(inc.get("selected"))
    if data_key == "description":
        return "description" in inc
    return inc.get(data_key) is not None


def edit_menu_keyboard(inc: Dict) -> InlineKeyboardMarkup:
    buttons = []
    for data_key, short_key, label in _FIELDS:
        if _has_value(inc, data_key):
            buttons.append([InlineKeyboardButton(label, callback_data=f"edit_field:{short_key}")])

    # Nguyên nhân có thể đã bị "Bỏ qua" (cause_id=None) nhưng vẫn coi là đã nhập.
    if "cause_id" in inc:
        buttons.insert(2, [InlineKeyboardButton("🔎 Nguyên nhân", callback_data="edit_field:cause")])

    buttons.append([InlineKeyboardButton("⬅️ Không sửa, quay lại tóm tắt", callback_data="edit_menu_back")])
    return InlineKeyboardMarkup(buttons)
