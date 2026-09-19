import logging

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.keyboards.main_menu import main_menu_text
from config.settings import settings
from utils.safety import safe_conversation_step, safe_step
from utils.validators import validate_full_name

logger = logging.getLogger(__name__)

REGISTER_NAME = 1000
VALID_ROLES = {"ADMIN", "MANAGER", "FIELD", "VIEWER"}


async def _notify_admins_new_user(context: ContextTypes.DEFAULT_TYPE, app_user) -> None:
    if not settings.admin_telegram_ids:
        return
    text = (
        f"🆕 Người dùng mới đăng ký:\n"
        f"Tên: {app_user['full_name']}\n"
        f"Telegram ID: {app_user['telegram_user_id']}\n"
        f"Quyền hiện tại: VIEWER (chỉ xem)\n\n"
        f"Gõ /setrole {app_user['telegram_user_id']} <ADMIN|MANAGER|FIELD|VIEWER> để cấp quyền."
    )
    for admin_id in settings.admin_telegram_ids:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            logger.exception("Không gửi được thông báo cho admin_id=%s", admin_id)


@safe_conversation_step
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_repo = context.bot_data["user_repo"]
    tg_user = update.effective_user

    app_user = await user_repo.get_by_telegram_id(tg_user.id)

    if app_user is None:
        await update.message.reply_text(
            "👋 Chào bạn! Bạn chưa được đăng ký trong hệ thống.\n"
            "Vui lòng nhập họ và tên đầy đủ để đăng ký:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return REGISTER_NAME

    if app_user["status"] != "ACTIVE":
        await update.message.reply_text(
            "⛔ Tài khoản của bạn đã bị vô hiệu hóa. Vui lòng liên hệ quản trị viên."
        )
        return ConversationHandler.END

    context.user_data["user_id"] = app_user["user_id"]
    context.user_data["role"] = app_user["role"]

    await update.message.reply_text(
        f"👋 Chào {app_user['full_name']}!\n\n{main_menu_text(app_user['role'])}",
        parse_mode="HTML",
    )
    return ConversationHandler.END


@safe_conversation_step
async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    full_name = update.message.text.strip()
    if not validate_full_name(full_name):
        await update.message.reply_text("Tên quá ngắn. Vui lòng nhập lại họ và tên đầy đủ:")
        return REGISTER_NAME

    user_repo = context.bot_data["user_repo"]
    tg_user = update.effective_user

    app_user = await user_repo.create_user(
        telegram_user_id=tg_user.id,
        telegram_username=tg_user.username,
        full_name=full_name,
        role="VIEWER",
    )
    context.user_data["user_id"] = app_user["user_id"]
    context.user_data["role"] = app_user["role"]

    await update.message.reply_text(
        f"✅ Đăng ký thành công, {full_name}!\n"
        "Tài khoản của bạn mặc định ở quyền <b>VIEWER (chỉ xem)</b>. "
        "Quản trị viên sẽ được thông báo để cấp quyền báo cáo nếu cần.\n\n"
        f"{main_menu_text(app_user['role'])}",
        parse_mode="HTML",
    )
    await _notify_admins_new_user(context, app_user)
    return ConversationHandler.END


@safe_conversation_step
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Đã huỷ thao tác.")
    return ConversationHandler.END


@safe_step
async def set_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in settings.admin_telegram_ids:
        await update.message.reply_text("⛔ Lệnh này chỉ dành cho quản trị viên.")
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "Cú pháp: /setrole <telegram_id> <ADMIN|MANAGER|FIELD|VIEWER>"
        )
        return

    telegram_id_str, role = context.args
    role = role.upper()

    if not telegram_id_str.isdigit():
        await update.message.reply_text("telegram_id phải là số.")
        return

    if role not in VALID_ROLES:
        await update.message.reply_text(f"Quyền không hợp lệ. Chọn 1 trong: {', '.join(VALID_ROLES)}")
        return

    telegram_id = int(telegram_id_str)
    user_repo = context.bot_data["user_repo"]
    updated = await user_repo.update_role(telegram_id, role)

    if updated is None:
        await update.message.reply_text("Không tìm thấy người dùng với telegram_id này.")
        return

    await update.message.reply_text(
        f"✅ Đã cấp quyền {role} cho {updated['full_name']} (id={telegram_id})."
    )

    # Cập nhật ngay context.user_data của người dùng đó (không cần họ /start lại).
    context.application.user_data[telegram_id]["role"] = role
    context.application.user_data[telegram_id]["user_id"] = updated["user_id"]

    try:
        await context.bot.send_message(
            chat_id=telegram_id,
            text=f"🔑 Quyền của bạn đã được cập nhật thành: {role}.\n\n{main_menu_text(role)}",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Không gửi được thông báo đổi quyền cho telegram_id=%s", telegram_id)


def get_start_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="start_conversation",
        persistent=False,
    )


def get_setrole_handler() -> CommandHandler:
    return CommandHandler("setrole", set_role)
