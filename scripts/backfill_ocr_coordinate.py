"""Chạy 1 lần: backfill coordinate_extraction cho các sự cố CŨ (nhập trước
khi triển khai OCR worker) — những ảnh BEFORE/AFTER này chưa từng có job OCR
nào vì lúc nhập chưa có tính năng, nên ocr_worker sẽ KHÔNG bao giờ tự động
động tới chúng (worker chỉ poll bảng coordinate_extraction, không quét
incident_photo). Script này tạo job PENDING cho các ảnh còn thiếu, sau đó
ocr_worker đang chạy sẽ tự nhặt và xử lý như job bình thường.

An toàn chạy lại nhiều lần: chỉ insert ảnh CHƯA có coordinate_extraction
(ON CONFLICT (photo_id) DO NOTHING), không đụng tới job đã tồn tại
(PENDING/PROCESSING/SUCCESS/INVALID/FAILED).

Sử dụng:
    python -m scripts.backfill_ocr_coordinate --dry-run        # xem trước
    python -m scripts.backfill_ocr_coordinate                  # backfill toàn bộ
    python -m scripts.backfill_ocr_coordinate --incident-id 123  # chỉ 1 sự cố
"""
import argparse
import asyncio
import logging

import asyncpg

from config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_SELECT_MISSING = """
    SELECT p.incident_photo_id, p.incident_id, p.photo_type, p.cloudinary_url
    FROM incident_photo p
    LEFT JOIN coordinate_extraction ce ON ce.photo_id = p.incident_photo_id
    WHERE p.photo_type IN ('BEFORE', 'AFTER')
      AND p.cloudinary_url IS NOT NULL
      AND ce.coordinate_extraction_id IS NULL
      AND ($1::bigint IS NULL OR p.incident_id = $1)
    ORDER BY p.incident_id, p.incident_photo_id
"""

_INSERT_BACKFILL = """
    INSERT INTO coordinate_extraction (incident_id, photo_id, source, status)
    SELECT p.incident_id, p.incident_photo_id, p.photo_type, 'PENDING'
    FROM incident_photo p
    LEFT JOIN coordinate_extraction ce ON ce.photo_id = p.incident_photo_id
    WHERE p.photo_type IN ('BEFORE', 'AFTER')
      AND p.cloudinary_url IS NOT NULL
      AND ce.coordinate_extraction_id IS NULL
      AND ($1::bigint IS NULL OR p.incident_id = $1)
    ON CONFLICT (photo_id) DO NOTHING
    RETURNING coordinate_extraction_id, incident_id, photo_id, source
"""


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Chỉ xem trước, KHÔNG tạo job")
    parser.add_argument("--incident-id", type=int, default=None, help="Chỉ backfill 1 incident_id cụ thể")
    args = parser.parse_args()

    conn = await asyncpg.connect(dsn=settings.dsn)
    try:
        if args.dry_run:
            rows = await conn.fetch(_SELECT_MISSING, args.incident_id)
            logger.info("DRY-RUN: %d ảnh BEFORE/AFTER cũ chưa có job OCR sẽ được tạo:", len(rows))
            for r in rows[:50]:
                logger.info(
                    "  incident=%s photo=%s source=%s url=%s",
                    r["incident_id"], r["incident_photo_id"], r["photo_type"], r["cloudinary_url"],
                )
            if len(rows) > 50:
                logger.info("  ... và %d ảnh khác", len(rows) - 50)
            logger.info("Chạy lại KHÔNG có --dry-run để thực sự tạo job.")
            return

        async with conn.transaction():
            inserted = await conn.fetch(_INSERT_BACKFILL, args.incident_id)

        logger.info("Đã tạo %d job OCR PENDING (backfill).", len(inserted))
        affected_incidents = {r["incident_id"] for r in inserted}
        logger.info("Số incident bị ảnh hưởng: %d", len(affected_incidents))
        if inserted:
            logger.info("ocr_worker (systemd: fiber_rescue_ocr_worker) sẽ tự nhặt các job này ở lượt poll kế tiếp.")
        else:
            logger.info("Không có ảnh nào cần backfill — mọi ảnh BEFORE/AFTER đã có job OCR.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
