from typing import Dict, Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from utils.formatters import format_quantity


def material_selection_keyboard(selected: Dict[int, dict]) -> InlineKeyboardMarkup:
    # Vật tư CABLE luôn hiển thị trên cùng, các nhóm khác giữ nguyên thứ tự hiện có.
    ordered_items = sorted(
        selected.items(),
        key=lambda pair: 0 if pair[1]["group"] == "CABLE" else 1,
    )

    buttons = []
    for mid, item in ordered_items:
        qty_text = f"{format_quantity(item['qty'])} {item['unit']}"
        buttons.append([
            InlineKeyboardButton(item["name"], callback_data=f"qty_noop:{mid}"),
        ])
        buttons.append([
            InlineKeyboardButton("➖", callback_data=f"qty_dec:{mid}"),
            InlineKeyboardButton(qty_text, callback_data=f"qty_noop:{mid}"),
            InlineKeyboardButton("➕", callback_data=f"qty_inc:{mid}"),
        ])
    buttons.append([InlineKeyboardButton("➕ Vật tư khác", callback_data="material_add_other")])
    buttons.append([InlineKeyboardButton("✅ Xong, tiếp tục", callback_data="material_done")])
    return InlineKeyboardMarkup(buttons)


def additional_material_keyboard(materials: Sequence[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(m["material_name"], callback_data=f"add_material:{m['material_id']}")]
        for m in materials
    ]
    buttons.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="material_back")])
    return InlineKeyboardMarkup(buttons)
