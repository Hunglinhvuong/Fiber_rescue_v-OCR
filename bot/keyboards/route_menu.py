from typing import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def route_list_keyboard(
    routes: Sequence, page: int, total: int, page_size: int
) -> InlineKeyboardMarkup:
    buttons = []
    for r in routes:
        label = f"{r['route_name']} ({r['cable_type']}-{r['fiber_count']}FO)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"route:{r['route_id']}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Trước", callback_data=f"route_page:{page - 1}"))
    if (page + 1) * page_size < total:
        nav_row.append(InlineKeyboardButton("Sau ➡️", callback_data=f"route_page:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🔍 Tìm theo tên", callback_data="route_search")])
    return InlineKeyboardMarkup(buttons)


def incident_type_keyboard(types: Sequence) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(t["type_name"], callback_data=f"itype:{t['incident_type_id']}")]
        for t in types
    ]
    return InlineKeyboardMarkup(buttons)


def incident_cause_keyboard(causes: Sequence) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(c["cause_name"], callback_data=f"cause:{c['cause_id']}")]
        for c in causes
    ]
    buttons.append([InlineKeyboardButton("⏭ Bỏ qua", callback_data="cause:skip")])
    return InlineKeyboardMarkup(buttons)


def repair_span_keyboard(spans: Sequence) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(s["span_name"], callback_data=f"span:{s['repair_span_type_id']}")]
        for s in spans
    ]
    return InlineKeyboardMarkup(buttons)
