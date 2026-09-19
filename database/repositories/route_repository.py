from typing import Optional, Sequence

import asyncpg


class RouteRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def list_active(
        self,
        limit: int = 6,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> Sequence[asyncpg.Record]:
        if search:
            query = """
                SELECT route_id, route_code, route_name, cable_type, fiber_count, province
                FROM fiber_route
                WHERE status = 'ACTIVE' AND route_name ILIKE $1
                ORDER BY route_name
                LIMIT $2 OFFSET $3
            """
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, f"%{search}%", limit, offset)

        query = """
            SELECT route_id, route_code, route_name, cable_type, fiber_count, province
            FROM fiber_route
            WHERE status = 'ACTIVE'
            ORDER BY route_name
            LIMIT $1 OFFSET $2
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, limit, offset)

    async def count_active(self, search: Optional[str] = None) -> int:
        if search:
            query = "SELECT COUNT(*) FROM fiber_route WHERE status = 'ACTIVE' AND route_name ILIKE $1"
            async with self.pool.acquire() as conn:
                return await conn.fetchval(query, f"%{search}%")

        query = "SELECT COUNT(*) FROM fiber_route WHERE status = 'ACTIVE'"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query)

    async def get_by_id(self, route_id: int) -> Optional[asyncpg.Record]:
        query = """
            SELECT route_id, route_code, route_name, cable_type, fiber_count, province
            FROM fiber_route
            WHERE route_id = $1
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, route_id)
