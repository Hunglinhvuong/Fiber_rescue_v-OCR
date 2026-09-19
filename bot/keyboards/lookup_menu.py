from typing import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def date_list_keyboard(dates: Sequence) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                f"📅 {d['report_date']:%d/%m/%Y} ({d['total']} sự cố)",
                callback_data=f"kt_date:{d['report_date'].isoformat()}",
            )
        ]
        for d in dates
    ]
    return InlineKeyboardMarkup(buttons)


def incident_list_keyboard(incidents: Sequence) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                f"{i['incident_code']} — {i['route_name']} ({i['type_name']})",
                callback_data=f"kt_incident:{i['incident_id']}",
            )
        ]
        for i in incidents
    ]
    buttons.append([InlineKeyboardButton("⬅️ Chọn ngày khác", callback_data="kt_restart")])
    return InlineKeyboardMarkup(buttons)
