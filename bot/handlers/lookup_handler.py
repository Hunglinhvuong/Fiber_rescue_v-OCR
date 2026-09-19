import logging
from datetime import date

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from bot.keyboards.lookup_menu import date_list_keyboard, incident_list_keyboard
from utils.formatters import format_incident_detail
from utils.safety import safe_step
from utils.user_context import ensure_user_context

logger = logging.getLogger(__name__)

# FIELD chỉ xem sự cố do chính mình báo cáo; các role khác xem toàn bộ.
SCOPED_ROLES = {"FIELD"}


def _scope_user_id(context: ContextTypes.DEFAULT_TYPE):
    role = context.user_data.get("role")
    if role in SCOPED_ROLES:
        return context.user_data.get("user_id")
    return None


@safe_step
async def kt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app_user = await ensure_user_context(update, context)
    if app_user is None:
        await update.message.reply_text("Vui lòng gõ /start trước để đăng ký.")
        return

    if app_user["status"] != "ACTIVE":
        await update.message.reply_text(
            "⛔ Tài khoản của bạn đã bị vô hiệu hóa. Vui lòng liên hệ quản trị viên."
        )
        return

    incident_service = context.bot_data["incident_service"]
    scope_user_id = _scope_user_id(context)
    dates = await incident_service.list_report_dates(scope_user_id, limit=14)

    if not dates:
        await update.message.reply_text("📭 Chưa có sự cố nào được ghi nhận.")
        return

    await update.message.reply_text(
        "🗓 Chọn ngày cần tra cứu:",
        reply_markup=date_list_keyboard(dates),
    )


@safe_step
async def kt_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    report_date = date.fromisoformat(query.data.split(":", 1)[1])
    incident_service = context.bot_data["incident_service"]
    scope_user_id = _scope_user_id(context)
    incidents = await incident_service.list_by_date(report_date, scope_user_id)

    if not incidents:
        await query.edit_message_text(f"📭 Không có sự cố nào ngày {report_date:%d/%m/%Y}.")
        return

    await query.edit_message_text(
        f"📋 Sự cố ngày {report_date:%d/%m/%Y}:",
        reply_markup=incident_list_keyboard(incidents),
    )


@safe_step
async def kt_incident_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    incident_id = int(query.data.split(":", 1)[1])
    incident_service = context.bot_data["incident_service"]
    detail = await incident_service.get_incident_detail(incident_id)

    if detail is None:
        await query.edit_message_text("Không tìm thấy sự cố này.")
        return

    text = format_incident_detail(detail["incident"], detail["materials"], detail["photos"])
    await query.edit_message_text(text, parse_mode="HTML")

    for photo in detail["photos"]:
        if not photo["telegram_file_id"]:
            continue
        caption = "📷 Trước khi khắc phục" if photo["photo_type"] == "BEFORE" else "📷 Sau khi khắc phục"
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo["telegram_file_id"],
                caption=caption,
            )
        except Exception:
            # 1 ảnh lỗi (VD: file_id hết hạn trên Telegram) không được làm dừng
            # việc gửi các ảnh còn lại.
            logger.exception("Không gửi được ảnh incident_id=%s", incident_id)


@safe_step
async def kt_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    incident_service = context.bot_data["incident_service"]
    scope_user_id = _scope_user_id(context)
    dates = await incident_service.list_report_dates(scope_user_id, limit=14)

    if not dates:
        await query.edit_message_text("📭 Chưa có sự cố nào được ghi nhận.")
        return

    await query.edit_message_text(
        "🗓 Chọn ngày cần tra cứu:",
        reply_markup=date_list_keyboard(dates),
    )


def get_lookup_handlers() -> list:
    return [
        CommandHandler("kt", kt_command),
        CallbackQueryHandler(kt_date_selected, pattern=r"^kt_date:\d{4}-\d{2}-\d{2}$"),
        CallbackQueryHandler(kt_incident_selected, pattern=r"^kt_incident:\d+$"),
        CallbackQueryHandler(kt_restart, pattern=r"^kt_restart$"),
    ]
