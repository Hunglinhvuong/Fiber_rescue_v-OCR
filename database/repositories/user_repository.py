from typing import Optional

import asyncpg


class UserRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_by_telegram_id(self, telegram_user_id: int) -> Optional[asyncpg.Record]:
        query = """
            SELECT user_id, telegram_user_id, telegram_username,
                   full_name, team_name, role, status
            FROM app_user
            WHERE telegram_user_id = $1
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, telegram_user_id)

    async def create_user(
        self,
        telegram_user_id: int,
        telegram_username: Optional[str],
        full_name: str,
        team_name: Optional[str] = None,
        role: str = "FIELD",
    ) -> asyncpg.Record:
        query = """
            INSERT INTO app_user (
                telegram_user_id, telegram_username, full_name, team_name, role
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING user_id, telegram_user_id, telegram_username,
                      full_name, team_name, role, status
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                query, telegram_user_id, telegram_username, full_name, team_name, role
            )

    async def is_active(self, telegram_user_id: int) -> bool:
        row = await self.get_by_telegram_id(telegram_user_id)
        return row is not None and row["status"] == "ACTIVE"

    async def update_role(self, telegram_user_id: int, role: str) -> Optional[asyncpg.Record]:
        query = """
            UPDATE app_user
            SET role = $2, updated_at = CURRENT_TIMESTAMP
            WHERE telegram_user_id = $1
            RETURNING user_id, telegram_user_id, full_name, role, status
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, telegram_user_id, role)
