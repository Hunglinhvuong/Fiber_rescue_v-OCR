"""Worker nền độc lập với bot Telegram — xử lý OCR trích toạ độ từ ảnh sự cố.

Chạy: python -m workers.ocr_worker
Deploy: systemd riêng (xem deploy/fiber_rescue_ocr_worker.service.template),
        có thể scale nhiều instance vì hàng đợi dùng FOR UPDATE SKIP LOCKED.

Luồng mỗi job: PENDING -> PROCESSING -> gọi OCR (OCRService fallback
               OCR.space -> Google Vision) -> parse -> validate
               -> SUCCESS/INVALID/FAILED -> recompute_final_coordinate().
"""
import asyncio
import logging
import signal

from config.settings import settings
from database.connection import close_pool, init_pool
from database.repositories.coordinate_repository import CoordinateExtractionRepository
from ocr.parser import parse_coordinates
from ocr.service import OCRService
from services.coordinate_service import CoordinateService, is_within_valid_range, is_within_vietnam_bounds

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_shutdown_event = asyncio.Event()


def _handle_signal(*_args) -> None:
    logger.info("Nhận tín hiệu dừng, worker sẽ thoát sau khi xử lý xong batch hiện tại...")
    _shutdown_event.set()


async def _process_one(
    row, extraction_repo: CoordinateExtractionRepository, ocr_service: OCRService, coordinate_service: CoordinateService
) -> None:
    extraction_id = row["coordinate_extraction_id"]
    incident_id = row["incident_id"]
    image_url = row["cloudinary_url"]

    ocr_result = await ocr_service.extract_text(image_url)

    if not ocr_result.success:
        logger.warning(
            "OCR thất bại cho extraction=%s (provider=%s): %s",
            extraction_id, ocr_result.provider, ocr_result.error,
        )
        will_retry = await extraction_repo.mark_failed_or_retry(
            extraction_id, row["retry_count"], ocr_result.error or "OCR thất bại", settings.ocr_worker_max_retries
        )
        if not will_retry:
            await coordinate_service.recompute_final_coordinate(incident_id)
        return

    if ocr_result.confidence and ocr_result.confidence < settings.ocr_min_confidence:
        await extraction_repo.mark_invalid(
            extraction_id, ocr_result.text, f"Confidence quá thấp: {ocr_result.confidence:.2f}"
        )
        await coordinate_service.recompute_final_coordinate(incident_id)
        return

    parsed = parse_coordinates(ocr_result.text)
    if parsed is None:
        await extraction_repo.mark_invalid(extraction_id, ocr_result.text, "Không tìm thấy toạ độ trong text OCR")
        await coordinate_service.recompute_final_coordinate(incident_id)
        return

    if not is_within_valid_range(parsed.latitude, parsed.longitude):
        await extraction_repo.mark_invalid(
            extraction_id, ocr_result.text, f"Toạ độ ngoài phạm vi hợp lệ: {parsed.latitude}, {parsed.longitude}"
        )
        await coordinate_service.recompute_final_coordinate(incident_id)
        return

    if not is_within_vietnam_bounds(parsed.latitude, parsed.longitude):
        await extraction_repo.mark_invalid(
            extraction_id, ocr_result.text, f"Toạ độ ngoài lãnh thổ VN: {parsed.latitude}, {parsed.longitude}"
        )
        await coordinate_service.recompute_final_coordinate(incident_id)
        return

    await extraction_repo.mark_success(
        extraction_id, ocr_result.text, parsed.latitude, parsed.longitude, ocr_result.confidence
    )
    await coordinate_service.recompute_final_coordinate(incident_id)
    logger.info(
        "OCR thành công extraction=%s incident=%s source=%s provider=%s -> (%.6f, %.6f)",
        extraction_id, incident_id, row["source"], ocr_result.provider, parsed.latitude, parsed.longitude,
    )


async def run_forever() -> None:
    pool = await init_pool()
    extraction_repo = CoordinateExtractionRepository(pool)
    coordinate_service = CoordinateService(pool)
    ocr_service = OCRService()

    logger.info(
        "OCR worker khởi động. providers=%s poll=%ss batch=%s",
        settings.ocr_provider_order, settings.ocr_worker_poll_interval_seconds, settings.ocr_worker_batch_size,
    )

    try:
        while not _shutdown_event.is_set():
            rows = await extraction_repo.claim_pending_batch(settings.ocr_worker_batch_size)
            if not rows:
                try:
                    await asyncio.wait_for(_shutdown_event.wait(), timeout=settings.ocr_worker_poll_interval_seconds)
                except asyncio.TimeoutError:
                    pass
                continue

            for row in rows:
                try:
                    await _process_one(row, extraction_repo, ocr_service, coordinate_service)
                except Exception:  # noqa: BLE001 - 1 job lỗi không được làm chết cả worker
                    logger.exception("Lỗi xử lý extraction=%s", row["coordinate_extraction_id"])
                    await extraction_repo.mark_failed_or_retry(
                        row["coordinate_extraction_id"], row["retry_count"], "Lỗi worker nội bộ",
                        settings.ocr_worker_max_retries,
                    )
    finally:
        await close_pool()
        logger.info("OCR worker đã dừng.")


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            pass  # Windows
    loop.run_until_complete(run_forever())


if __name__ == "__main__":
    main()
