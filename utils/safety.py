import logging
from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

_ERROR_TEXT = "❌ Đã xảy ra lỗi không mong muốn. Vui lòng thử lại."


async def _notify_error(update: Update) -> None:
    try:
        if update.callback_query is not None:
            try:
                await update.callback_query.answer()
            except Exception:
                pass
            await update.callback_query.message.reply_text(_ERROR_TEXT)
        elif update.effective_message is not None:
            await update.effective_message.reply_text(_ERROR_TEXT)
    except Exception:
        logger.exception("Không thể gửi thông báo lỗi cho người dùng")


def safe_conversation_step(func):
    """Bọc 1 bước trong ConversationHandler: nếu lỗi (DB timeout, dữ liệu thiếu,
    Telegram API lỗi...) -> log, báo người dùng, dọn dữ liệu tạm và kết thúc
    conversation gọn gàng thay vì để exception làm crash/kẹt state của bot."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception:
            logger.exception("Lỗi trong bước '%s'", func.__name__)
            await _notify_error(update)
            context.user_data.pop("incident", None)
            return ConversationHandler.END

    return wrapper


def safe_step(func):
    """Bọc 1 handler độc lập (ngoài ConversationHandler, trả về None):
    nuốt lỗi, báo người dùng, không để exception làm crash tiến trình bot."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception:
            logger.exception("Lỗi trong handler '%s'", func.__name__)
            await _notify_error(update)
            return None

    return wrapper
