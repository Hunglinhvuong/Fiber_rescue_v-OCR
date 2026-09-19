from typing import List, Optional, Sequence

import asyncpg


class MaterialRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_config_materials(
        self,
        cable_type: str,
        fiber_count: int,
        repair_span_type_id: int,
    ) -> Sequence[asyncpg.Record]:
        """Vật tư được cấu hình sẵn theo cable_type + fiber_count + repair_span_type
        (material_rule cho phép NULL = wildcard, khớp mọi giá trị)."""
        query = """
            SELECT DISTINCT m.material_id, m.material_code, m.material_name,
                   m.material_group, m.unit
            FROM material_rule mr
            JOIN material m ON m.material_id = mr.material_id
            WHERE (mr.cable_type IS NULL OR mr.cable_type = $1)
              AND (mr.fiber_count IS NULL OR mr.fiber_count = $2)
              AND (mr.repair_span_type_id IS NULL OR mr.repair_span_type_id = $3)
              AND m.is_active = TRUE
            ORDER BY m.material_group, m.material_name
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, cable_type, fiber_count, repair_span_type_id)

    async def get_additional_materials(
        self, exclude_ids: Optional[List[int]] = None
    ) -> Sequence[asyncpg.Record]:
        """Vật tư bổ sung (CLAMP, PIPE, POLE_BAND, OTHERS) không tự động phân loại."""
        ids = exclude_ids or []
        query = """
            SELECT material_id, material_code, material_name, material_group, unit
            FROM material
            WHERE is_active = TRUE
              AND material_id != ALL($1::bigint[])
              AND material_group IN ('CLAMP', 'PIPE', 'POLE_BAND', 'OTHERS')
            ORDER BY material_group, material_name
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, ids)

    async def get_by_id(self, material_id: int) -> Optional[asyncpg.Record]:
        query = """
            SELECT material_id, material_code, material_name, material_group, unit
            FROM material
            WHERE material_id = $1
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, material_id)
