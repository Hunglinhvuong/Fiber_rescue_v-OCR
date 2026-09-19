from typing import List, Optional, Sequence

import asyncpg


class CoordinateExtractionRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create_pending(
        self, conn: asyncpg.Connection, incident_id: int, photo_id: int, source: str
    ) -> int:
        query = """
            INSERT INTO coordinate_extraction (incident_id, photo_id, source, status)
            VALUES ($1, $2, $3, 'PENDING')
            ON CONFLICT (photo_id) DO NOTHING
            RETURNING coordinate_extraction_id
        """
        row = await conn.fetchrow(query, incident_id, photo_id, source)
        return row["coordinate_extraction_id"] if row else None

    async def claim_pending_batch(self, batch_size: int) -> List[asyncpg.Record]:
        """Lấy 1 lô job PENDING (kể cả job vừa bị requeue sau lỗi tạm thời) và
        chuyển sang PROCESSING trong cùng transaction (FOR UPDATE SKIP LOCKED)
        -> hàng đợi nằm trong PostgreSQL, không cần Redis/Celery, an toàn nếu
        chạy nhiều worker song song."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    SELECT ce.coordinate_extraction_id, ce.incident_id, ce.photo_id, ce.source,
                           ce.retry_count, p.cloudinary_url
                    FROM coordinate_extraction ce
                    JOIN incident_photo p ON p.incident_photo_id = ce.photo_id
                    WHERE ce.status = 'PENDING'
                    ORDER BY ce.created_at
                    LIMIT $1
                    FOR UPDATE OF ce SKIP LOCKED
                    """,
                    batch_size,
                )
                if rows:
                    ids = [r["coordinate_extraction_id"] for r in rows]
                    await conn.execute(
                        "UPDATE coordinate_extraction SET status = 'PROCESSING' WHERE coordinate_extraction_id = ANY($1::bigint[])",
                        ids,
                    )
                return rows

    async def mark_success(
        self, extraction_id: int, raw_text: str, latitude: float, longitude: float, confidence: float
    ) -> None:
        query = """
            UPDATE coordinate_extraction
            SET status = 'SUCCESS', raw_text = $2, latitude = $3, longitude = $4,
                confidence = $5, error_message = NULL
            WHERE coordinate_extraction_id = $1
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, extraction_id, raw_text, latitude, longitude, confidence)

    async def mark_invalid(self, extraction_id: int, raw_text: str, error_message: str) -> None:
        query = """
            UPDATE coordinate_extraction
            SET status = 'INVALID', raw_text = $2, error_message = $3
            WHERE coordinate_extraction_id = $1
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, extraction_id, raw_text, error_message)

    async def mark_failed_or_retry(
        self, extraction_id: int, retry_count: int, error_message: str, max_retries: int
    ) -> bool:
        """Lỗi TẠM THỜI (mạng, timeout, OCR server chưa sẵn sàng...): nếu còn
        lượt retry thì requeue về PENDING (tăng retry_count), ngược lại mới
        chuyển hẳn sang FAILED. Trả True nếu sẽ được retry."""
        if retry_count < max_retries:
            query = """
                UPDATE coordinate_extraction
                SET status = 'PENDING', retry_count = retry_count + 1, error_message = $2
                WHERE coordinate_extraction_id = $1
            """
            will_retry = True
        else:
            query = """
                UPDATE coordinate_extraction
                SET status = 'FAILED', error_message = $2
                WHERE coordinate_extraction_id = $1
            """
            will_retry = False

        async with self.pool.acquire() as conn:
            await conn.execute(query, extraction_id, error_message)
        return will_retry

    async def mark_failed(self, extraction_id: int, error_message: str) -> None:
        query = """
            UPDATE coordinate_extraction
            SET status = 'FAILED', error_message = $2
            WHERE coordinate_extraction_id = $1
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, extraction_id, error_message)

    async def get_latest_success_by_source(self, incident_id: int, source: str) -> Optional[asyncpg.Record]:
        query = """
            SELECT latitude, longitude, confidence
            FROM coordinate_extraction
            WHERE incident_id = $1 AND source = $2 AND status = 'SUCCESS'
            ORDER BY updated_at DESC
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, incident_id, source)

    async def list_by_incident(self, incident_id: int) -> Sequence[asyncpg.Record]:
        query = """
            SELECT coordinate_extraction_id, photo_id, source, status, raw_text,
                   latitude, longitude, confidence, error_message, created_at
            FROM coordinate_extraction
            WHERE incident_id = $1
            ORDER BY created_at
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, incident_id)
