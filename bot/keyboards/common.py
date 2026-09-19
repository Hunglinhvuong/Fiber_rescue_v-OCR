from telegram import InlineKeyboardButton

CANCEL_CALLBACK_DATA = "cancel_incident_inline"


def cancel_button_row() -> list:
    return [InlineKeyboardButton("❌ Huỷ báo cáo", callback_data=CANCEL_CALLBACK_DATA)]
