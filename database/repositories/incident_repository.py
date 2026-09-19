from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

import asyncpg


class IncidentRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(
        self,
        conn: asyncpg.Connection,
        route_id: int,
        reported_by: int,
        incident_type_id: int,
        cause_id: Optional[int],
        repair_span_type_id: int,
        latitude: float,
        longitude: float,
        location_accuracy_m: Optional[float],
        description: Optional[str],
        status: str = "DRAFT",
    ) -> asyncpg.Record:
        # latitude/longitude = GPS Telegram lúc tạo (toạ độ "cuối cùng" tạm thời).
        # gps_latitude/gps_longitude lưu lại y nguyên để audit/đối soát với OCR sau này.
        # coordinate_status = PENDING vì OCR job chạy nền, chưa có kết quả tại thời điểm này.
        query = """
            INSERT INTO incident (
                incident_code, route_id, reported_by, incident_type_id, cause_id,
                repair_span_type_id, latitude, longitude, location_accuracy_m,
                description, status, gps_latitude, gps_longitude,
                coordinate_source, coordinate_status
            )
            VALUES ('', $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $6, $7, 'GPS', 'PENDING')
            RETURNING incident_id, incident_code, status
        """
        return await conn.fetchrow(
            query,
            route_id,
            reported_by,
            incident_type_id,
            cause_id,
            repair_span_type_id,
            latitude,
            longitude,
            location_accuracy_m,
            description,
            status,
        )

    async def update_final_coordinate(
        self,
        incident_id: int,
        latitude: float,
        longitude: float,
        coordinate_source: str,
        coordinate_status: str,
        coordinate_distance_m: Optional[float],
        ocr_latitude: Optional[float],
        ocr_longitude: Optional[float],
    ) -> None:
        """Gọi bởi CoordinateService sau khi OCR xử lý xong -> cập nhật toạ độ
        cuối cùng dùng cho dashboard/bản đồ. KHÔNG được gọi trực tiếp từ worker
        (worker chỉ ghi coordinate_extraction, coordinate_service mới quyết định)."""
        query = """
            UPDATE incident
            SET latitude = $2, longitude = $3, coordinate_source = $4,
                coordinate_status = $5, coordinate_distance_m = $6,
                ocr_latitude = $7, ocr_longitude = $8
            WHERE incident_id = $1
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                query, incident_id, latitude, longitude, coordinate_source,
                coordinate_status, coordinate_distance_m, ocr_latitude, ocr_longitude,
            )

    async def get_coordinates(self, incident_id: int) -> Optional[asyncpg.Record]:
        query = """
            SELECT incident_id, gps_latitude, gps_longitude, ocr_latitude, ocr_longitude,
                   latitude, longitude, coordinate_source, coordinate_status, coordinate_distance_m
            FROM incident
            WHERE incident_id = $1
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, incident_id)

    async def update_status(
        self,
        conn: asyncpg.Connection,
        incident_id: int,
        new_status: str,
        completed_at: Optional[datetime] = None,
    ) -> None:
        if completed_at is not None:
            query = "UPDATE incident SET status = $2, completed_at = $3 WHERE incident_id = $1"
            await conn.execute(query, incident_id, new_status, completed_at)
        else:
            query = "UPDATE incident SET status = $2 WHERE incident_id = $1"
            await conn.execute(query, incident_id, new_status)

    async def get_full(self, incident_id: int) -> Optional[asyncpg.Record]:
        query = """
            SELECT i.incident_id, i.incident_code, i.status, i.latitude, i.longitude,
                   i.description, i.reported_at, i.completed_at,
                   r.route_name, r.route_code, r.cable_type, r.fiber_count,
                   u.full_name AS reporter_name,
                   it.type_name, ic.cause_name, rst.span_name
            FROM incident i
            JOIN fiber_route r ON r.route_id = i.route_id
            JOIN app_user u ON u.user_id = i.reported_by
            JOIN incident_type it ON it.incident_type_id = i.incident_type_id
            LEFT JOIN incident_cause ic ON ic.cause_id = i.cause_id
            JOIN repair_span_type rst ON rst.repair_span_type_id = i.repair_span_type_id
            WHERE i.incident_id = $1
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, incident_id)

    async def list_recent_by_user(self, user_id: int, limit: int = 5) -> Sequence[asyncpg.Record]:
        query = """
            SELECT i.incident_id, i.incident_code, i.status, i.reported_at,
                   r.route_name, it.type_name
            FROM incident i
            JOIN fiber_route r ON r.route_id = i.route_id
            JOIN incident_type it ON it.incident_type_id = i.incident_type_id
            WHERE i.reported_by = $1
            ORDER BY i.reported_at DESC
            LIMIT $2
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, user_id, limit)

    async def list_report_dates(
        self, reported_by: Optional[int] = None, limit: int = 14
    ) -> Sequence[asyncpg.Record]:
        """Danh sách các ngày có sự cố (kèm số lượng), mới nhất trước.
        reported_by=None -> lấy tất cả người dùng (dùng cho MANAGER/ADMIN/VIEWER)."""
        query = """
            SELECT i.reported_at::date AS report_date, COUNT(*) AS total
            FROM incident i
            WHERE ($1::bigint IS NULL OR i.reported_by = $1)
            GROUP BY i.reported_at::date
            ORDER BY report_date DESC
            LIMIT $2
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, reported_by, limit)

    async def list_by_date(
        self, report_date, reported_by: Optional[int] = None
    ) -> Sequence[asyncpg.Record]:
        query = """
            SELECT i.incident_id, i.incident_code, i.status, i.reported_at,
                   r.route_name, it.type_name
            FROM incident i
            JOIN fiber_route r ON r.route_id = i.route_id
            JOIN incident_type it ON it.incident_type_id = i.incident_type_id
            WHERE i.reported_at::date = $1
              AND ($2::bigint IS NULL OR i.reported_by = $2)
            ORDER BY i.reported_at DESC
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, report_date, reported_by)


class IncidentMaterialRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add_many(
        self,
        conn: asyncpg.Connection,
        incident_id: int,
        items: List[Tuple[int, Decimal, Optional[str]]],
    ) -> None:
        query = """
            INSERT INTO incident_material (incident_id, material_id, quantity, note)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (incident_id, material_id)
            DO UPDATE SET quantity = EXCLUDED.quantity, note = EXCLUDED.note
        """
        for material_id, quantity, note in items:
            await conn.execute(query, incident_id, material_id, quantity, note)

    async def list_by_incident(self, incident_id: int) -> Sequence[asyncpg.Record]:
        query = """
            SELECT m.material_name, m.unit, im.quantity
            FROM incident_material im
            JOIN material m ON m.material_id = im.material_id
            WHERE im.incident_id = $1
            ORDER BY m.material_group, m.material_name
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, incident_id)


class IncidentPhotoRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add(
        self,
        conn: asyncpg.Connection,
        incident_id: int,
        photo_type: str,
        telegram_file_id: Optional[str],
        telegram_file_unique_id: Optional[str],
        cloudinary_public_id: Optional[str],
        cloudinary_asset_id: Optional[str],
        cloudinary_url: str,
        caption: Optional[str] = None,
    ) -> asyncpg.Record:
        query = """
            INSERT INTO incident_photo (
                incident_id, photo_type, telegram_file_id, telegram_file_unique_id,
                cloudinary_public_id, cloudinary_asset_id, cloudinary_url, caption
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING incident_photo_id
        """
        return await conn.fetchrow(
            query, incident_id, photo_type, telegram_file_id, telegram_file_unique_id,
            cloudinary_public_id, cloudinary_asset_id, cloudinary_url, caption,
        )

    async def list_by_incident(self, incident_id: int) -> Sequence[asyncpg.Record]:
        query = """
            SELECT photo_type, telegram_file_id, caption
            FROM incident_photo
            WHERE incident_id = $1
            ORDER BY incident_photo_id
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, incident_id)


class IncidentStatusHistoryRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def add(
        self,
        conn: asyncpg.Connection,
        incident_id: int,
        old_status: Optional[str],
        new_status: str,
        changed_by: int,
        note: Optional[str] = None,
    ) -> None:
        query = """
            INSERT INTO incident_status_history (
                incident_id, old_status, new_status, changed_by, note
            )
            VALUES ($1, $2, $3, $4, $5)
        """
        await conn.execute(query, incident_id, old_status, new_status, changed_by, note)
