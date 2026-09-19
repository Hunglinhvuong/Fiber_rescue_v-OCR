import logging
from typing import Optional

import asyncpg

from config.settings import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.dsn,
            min_size=settings.db_min_pool,
            max_size=settings.db_max_pool,
            # Đảm bảo mọi session dùng đúng timezone hiển thị (APP_TIMEZONE),
            # để các phép cast kiểu reported_at::date (dùng trong /kt) không bị
            # lệch ngày khi PostgreSQL mặc định phiên làm việc theo UTC.
            server_settings={"timezone": settings.timezone},
        )
        logger.info(
            "Database pool initialized (min=%s, max=%s, timezone=%s)",
            settings.db_min_pool, settings.db_max_pool, settings.timezone,
        )
    return _pool


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        return await init_pool()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")
