from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import asyncpg

from database.repositories.coordinate_repository import CoordinateExtractionRepository
from database.repositories.incident_repository import (
    IncidentMaterialRepository,
    IncidentPhotoRepository,
    IncidentRepository,
    IncidentStatusHistoryRepository,
)

# photo_type hợp lệ để trích toạ độ OCR (OTHER là ảnh phụ, không dùng cho OCR toạ độ)
_OCR_ELIGIBLE_PHOTO_TYPES = {"BEFORE", "AFTER"}


class IncidentService:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.incident_repo = IncidentRepository(pool)
        self.material_repo = IncidentMaterialRepository(pool)
        self.photo_repo = IncidentPhotoRepository(pool)
        self.history_repo = IncidentStatusHistoryRepository(pool)
        self.coordinate_extraction_repo = CoordinateExtractionRepository(pool)

    async def submit_incident(
        self,
        route_id: int,
        reported_by: int,
        incident_type_id: int,
        cause_id: Optional[int],
        repair_span_type_id: int,
        latitude: float,
        longitude: float,
        location_accuracy_m: Optional[float],
        description: Optional[str],
        materials: List[Tuple[int, Decimal, Optional[str]]],
        photos: List[Dict],
    ) -> Dict:
        """Lưu toàn bộ báo cáo sự cố trong 1 transaction: incident -> materials ->
        photos -> status history (DRAFT -> COMPLETED)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                incident_row = await self.incident_repo.create(
                    conn,
                    route_id=route_id,
                    reported_by=reported_by,
                    incident_type_id=incident_type_id,
                    cause_id=cause_id,
                    repair_span_type_id=repair_span_type_id,
                    latitude=latitude,
                    longitude=longitude,
                    location_accuracy_m=location_accuracy_m,
                    description=description,
                    status="DRAFT",
                )
                incident_id = incident_row["incident_id"]

                await self.history_repo.add(
                    conn, incident_id, None, "DRAFT", reported_by,
                    "Tạo báo cáo từ Telegram bot",
                )

                if materials:
                    await self.material_repo.add_many(conn, incident_id, materials)

                for photo in photos:
                    photo_row = await self.photo_repo.add(
                        conn,
                        incident_id,
                        photo["photo_type"],
                        photo.get("telegram_file_id"),
                        photo.get("telegram_file_unique_id"),
                        photo.get("cloudinary_public_id"),
                        photo.get("cloudinary_asset_id"),
                        photo["cloudinary_url"],
                        photo.get("caption"),
                    )

                    # Enqueue OCR job (bảng coordinate_extraction, status=PENDING).
                    # ocr_worker.py chạy nền sẽ nhặt job này -> KHÔNG làm bot chờ.
                    if photo["photo_type"] in _OCR_ELIGIBLE_PHOTO_TYPES:
                        await self.coordinate_extraction_repo.create_pending(
                            conn, incident_id, photo_row["incident_photo_id"], photo["photo_type"]
                        )

                completed_at = datetime.now(timezone.utc)
                await self.incident_repo.update_status(conn, incident_id, "COMPLETED", completed_at)
                await self.history_repo.add(
                    conn, incident_id, "DRAFT", "COMPLETED", reported_by, "Hoàn tất ứng cứu"
                )

                return {
                    "incident_id": incident_id,
                    "incident_code": incident_row["incident_code"],
                }

    async def get_incident_summary(self, incident_id: int):
        return await self.incident_repo.get_full(incident_id)

    async def list_recent(self, user_id: int, limit: int = 5):
        return await self.incident_repo.list_recent_by_user(user_id, limit)

    async def list_report_dates(self, reported_by: Optional[int], limit: int = 14):
        return await self.incident_repo.list_report_dates(reported_by, limit)

    async def list_by_date(self, report_date, reported_by: Optional[int]):
        return await self.incident_repo.list_by_date(report_date, reported_by)

    async def get_incident_detail(self, incident_id: int) -> Optional[Dict]:
        incident = await self.incident_repo.get_full(incident_id)
        if incident is None:
            return None
        materials = await self.material_repo.list_by_incident(incident_id)
        photos = await self.photo_repo.list_by_incident(incident_id)
        return {
            "incident": incident,
            "materials": materials,
            "photos": photos,
        }

    async def list_recent(self, user_id: int, limit: int = 5):
        return await self.incident_repo.list_recent_by_user(user_id, limit)
