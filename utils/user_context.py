from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes


async def ensure_user_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[dict]:
    """Đảm bảo context.user_data có 'user_id' và 'role' hợp lệ.

    - Nếu đã có cache (user_data) -> dùng luôn, KHÔNG query DB.
    - Nếu thiếu (VD: mất file persistence, hoặc user_data['role'] chưa được nạp)
      -> query lại app_user theo telegram_user_id 1 lần và nạp cache nếu tài khoản ACTIVE.

    Trả về:
    - dict {"user_id", "role", "status", "full_name"} nếu tài khoản tồn tại (kể cả bị khoá).
    - None nếu chưa đăng ký (chưa /start).
    """
    if "user_id" in context.user_data and "role" in context.user_data:
        return {
            "user_id": context.user_data["user_id"],
            "role": context.user_data["role"],
            "status": "ACTIVE",
            "full_name": context.user_data.get("full_name"),
        }

    user_repo = context.bot_data["user_repo"]
    app_user = await user_repo.get_by_telegram_id(update.effective_user.id)
    if app_user is None:
        return None

    if app_user["status"] == "ACTIVE":
        context.user_data["user_id"] = app_user["user_id"]
        context.user_data["role"] = app_user["role"]
        context.user_data["full_name"] = app_user["full_name"]

    return dict(app_user)
