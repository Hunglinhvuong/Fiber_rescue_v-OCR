import logging

from telegram import Update
from telegram.ext import Application, ContextTypes, PersistenceInput, PicklePersistence

from bot.handlers.incident_handler import get_incident_handler
from bot.handlers.lookup_handler import get_lookup_handlers
from bot.handlers.start_handler import get_setrole_handler, get_start_handler
from config.settings import settings
from database.connection import close_pool, init_pool
from database.repositories.lookup_repository import LookupRepository
from database.repositories.route_repository import RouteRepository
from database.repositories.user_repository import UserRepository
from services.incident_service import IncidentService
from services.material_service import MaterialService
from services.photo_service import PhotoService

logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    pool = await init_pool()
    application.bot_data["pool"] = pool
    application.bot_data["user_repo"] = UserRepository(pool)
    application.bot_data["route_repo"] = RouteRepository(pool)
    application.bot_data["lookup_repo"] = LookupRepository(pool)
    application.bot_data["material_service"] = MaterialService(pool)
    application.bot_data["incident_service"] = IncidentService(pool)
    application.bot_data["photo_service"] = PhotoService()
    logger.info("Bot initialized, DB pool ready")


async def _post_shutdown(application: Application) -> None:
    await close_pool()
    logger.info("Bot shutdown, DB pool closed")


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lưới an toàn cuối cùng: bất kỳ exception nào lọt qua các handler (kể cả những
    lỗi không nằm trong safe_step/safe_conversation_step, ví dụ lỗi mạng Telegram,
    lỗi nội bộ PTB...) đều dừng lại ở đây — được log lại và KHÔNG làm crash tiến
    trình bot / vòng lặp polling."""
    logger.error("Lỗi không được xử lý khi update=%s", update, exc_info=context.error)

    if isinstance(update, Update):
        chat = update.effective_chat
        if chat is not None:
            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text="❌ Đã xảy ra lỗi không mong muốn. Vui lòng thử lại hoặc gõ /start.",
                )
            except Exception:
                logger.exception("Không gửi được thông báo lỗi tới chat_id=%s", chat.id)


def build_application() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN chưa được cấu hình trong .env")

    # Chỉ persist user_data (user_id, role) để không cần /start lại sau khi restart bot.
    # bot_data chứa DB pool/repositories (không serialize được) nên loại trừ.
    persistence = PicklePersistence(
        filepath=settings.persistence_file,
        store_data=PersistenceInput(bot_data=False, chat_data=False, user_data=True, callback_data=False),
    )

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .persistence(persistence)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    application.add_handler(get_start_handler())
    application.add_handler(get_setrole_handler())
    application.add_handler(get_incident_handler())
    for handler in get_lookup_handlers():
        application.add_handler(handler)
    application.add_error_handler(_on_error)
    return application


def run() -> None:
    application = build_application()
    logger.info("Bot đang chạy...")
    application.run_polling(allowed_updates=["message", "callback_query"])
