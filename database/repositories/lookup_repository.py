from typing import Optional, Sequence

import asyncpg


class LookupRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def list_incident_types(self) -> Sequence[asyncpg.Record]:
        query = """
            SELECT incident_type_id, type_code, type_name
            FROM incident_type
            WHERE is_active = TRUE
            ORDER BY incident_type_id
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query)

    async def list_incident_causes(self) -> Sequence[asyncpg.Record]:
        query = """
            SELECT cause_id, cause_code, cause_name
            FROM incident_cause
            WHERE is_active = TRUE
            ORDER BY cause_id
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query)

    async def list_repair_span_types(self) -> Sequence[asyncpg.Record]:
        query = """
            SELECT repair_span_type_id, span_code, span_name
            FROM repair_span_type
            WHERE is_active = TRUE
            ORDER BY sort_order
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query)

    async def get_repair_span_type(self, repair_span_type_id: int) -> Optional[asyncpg.Record]:
        query = """
            SELECT repair_span_type_id, span_code, span_name
            FROM repair_span_type
            WHERE repair_span_type_id = $1
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, repair_span_type_id)
