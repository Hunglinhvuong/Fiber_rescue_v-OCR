import logging
import os
from typing import Optional

import pandas as pd
from psycopg2 import pool as pg_pool

from config.settings import settings

logger = logging.getLogger(__name__)

_pool: Optional[pg_pool.SimpleConnectionPool] = None

# Supabase (và nhiều DB cloud khác) bắt buộc kết nối qua SSL.
# Đặt DB_SSLMODE=disable trong .env nếu chạy Postgres local không có SSL.
_SSLMODE = os.getenv("DB_SSLMODE", "require")


def get_sync_pool() -> pg_pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = pg_pool.SimpleConnectionPool(
            1,
            settings.db_max_pool,
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            sslmode=_SSLMODE,
        )
        logger.info("Sync DB pool (dashboard) initialized (sslmode=%s)", _SSLMODE)
    return _pool


def get_sync_connection():
    return get_sync_pool().getconn()


def release_sync_connection(conn) -> None:
    get_sync_pool().putconn(conn)


def query_df(sql: str, params: Optional[object] = None) -> pd.DataFrame:
    """Chạy SQL trả về pandas DataFrame — dùng THẲNG connection psycopg2 từ
    pool (cursor.fetchall() + pd.DataFrame(...)), KHÔNG qua SQLAlchemy Engine
    và KHÔNG dùng pd.read_sql_query trực tiếp trên Engine.

    Lý do: pd.read_sql_query cần tự nhận diện đúng SQLAlchemy Engine để biết
    cách thực thi; khi phiên bản SQLAlchemy/pandas/Python lệch nhau (ví dụ
    SQLAlchemy chưa hỗ trợ bản Python rất mới), việc nhận diện này có thể vỡ
    và pandas rơi vào nhánh DBAPI2 cũ rồi gọi thẳng .cursor() lên Engine ->
    AttributeError: 'Engine' object has no attribute 'cursor'. Tự fetch bằng
    cursor rồi build DataFrame tay loại bỏ hoàn toàn phụ thuộc đó, đồng thời
    tương thích cả params dạng tuple (%s) lẫn dict (%(name)s) vì psycopg2 tự
    xử lý cả hai kiểu.
    """
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()
        # coerce_float=True: giữ đúng hành vi cũ của pd.read_sql_query — tự
        # convert decimal.Decimal (cột NUMERIC/DECIMAL của Postgres) sang
        # float, tránh cột bị lên dtype "object" làm vỡ plotly/tính toán.
        return pd.DataFrame.from_records(rows, columns=columns, coerce_float=True)
    finally:
        release_sync_connection(conn)
