"""Chạy 1 lần: áp dụng database/migrations/002_ocr_coordinate.sql lên DB.

Sử dụng:
    python -m scripts.migrate_002_ocr_coordinate
"""
import asyncio
import logging
from pathlib import Path

import asyncpg

from config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MIGRATION_FILE = Path(__file__).resolve().parent.parent / "database" / "migrations" / "002_ocr_coordinate.sql"


async def main() -> None:
    sql = MIGRATION_FILE.read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn=settings.dsn)
    try:
        logger.info("Áp dụng migration: %s", MIGRATION_FILE.name)
        await conn.execute(sql)
        logger.info("Migration thành công.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
