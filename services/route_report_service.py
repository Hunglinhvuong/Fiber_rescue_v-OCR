from typing import Dict, List, Optional

import pandas as pd

from database.connection_sync import get_sync_connection, get_sync_engine, release_sync_connection


class RouteReportService:
    """Truy vấn phục vụ trang Tuyến cáp — dùng kết nối đồng bộ (psycopg2),
    tách biệt hoàn toàn với pool asyncpg của bot Telegram."""

    def _query_df(self, sql: str, params=None) -> pd.DataFrame:
        return pd.read_sql_query(sql, get_sync_engine(), params=params)

    def _query_one(self, sql: str, params=None) -> Optional[dict]:
        conn = get_sync_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                if row is None:
                    return None
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, row))
        finally:
            release_sync_connection(conn)

    # ------------------------------------------------------------------
    # 3.1 Danh sách tuyến
    # ------------------------------------------------------------------

    def get_route_list(self, keyword: Optional[str] = None, status: Optional[str] = None) -> pd.DataFrame:
        conditions = ["1=1"]
        params: List = []
        if keyword:
            conditions.append("(r.route_code ILIKE %s OR r.route_name ILIKE %s)")
            like = f"%{keyword}%"
            params.extend([like, like])
        if status:
            conditions.append("r.status = %s")
            params.append(status)
        sql = f"""
            SELECT
                r.route_id,
                r.route_code AS ma_tuyen,
                r.route_name AS ten_tuyen,
                COALESCE(r.route_type, 'Chưa xác định') AS loai_tuyen,
                r.length_km AS chieu_dai_km,
                r.cable_type AS loai_cap,
                r.fiber_count AS so_fo,
                r.province,
                r.status AS trang_thai,
                COUNT(i.incident_id) AS so_su_co
            FROM fiber_route r
            LEFT JOIN incident i ON i.route_id = r.route_id
            WHERE {' AND '.join(conditions)}
            GROUP BY r.route_id
            ORDER BY r.route_name
        """
        return self._query_df(sql, tuple(params))

    # ------------------------------------------------------------------
    # 3.2 Chi tiết tuyến
    # ------------------------------------------------------------------

    def get_route_detail(self, route_id: int) -> Optional[Dict]:
        sql = """
            SELECT
                r.route_id, r.route_code, r.route_name, r.route_type,
                r.length_km, r.cable_type, r.fiber_count, r.province,
                r.status, r.description,
                COUNT(i.incident_id) AS total_incidents
            FROM fiber_route r
            LEFT JOIN incident i ON i.route_id = r.route_id
            WHERE r.route_id = %s
            GROUP BY r.route_id
        """
        return self._query_one(sql, (route_id,))

    def get_route_incident_history(self, route_id: int) -> pd.DataFrame:
        sql = """
            SELECT
                i.incident_code AS ma_su_co,
                i.status AS trang_thai,
                it.type_name AS loai_su_co,
                COALESCE(ic.cause_name, 'Chưa xác định') AS nguyen_nhan,
                rst.span_name AS doan_khac_phuc,
                i.reported_at AS thoi_gian_bao_cao
            FROM incident i
            JOIN incident_type it ON it.incident_type_id = i.incident_type_id
            LEFT JOIN incident_cause ic ON ic.cause_id = i.cause_id
            JOIN repair_span_type rst ON rst.repair_span_type_id = i.repair_span_type_id
            WHERE i.route_id = %s
            ORDER BY i.reported_at DESC
        """
        return self._query_df(sql, (route_id,))

    def get_route_cause_breakdown(self, route_id: int) -> pd.DataFrame:
        sql = """
            SELECT COALESCE(ic.cause_name, 'Chưa xác định') AS nguyen_nhan, COUNT(*) AS so_luong
            FROM incident i
            LEFT JOIN incident_cause ic ON ic.cause_id = i.cause_id
            WHERE i.route_id = %s
            GROUP BY nguyen_nhan
            ORDER BY so_luong DESC
        """
        return self._query_df(sql, (route_id,))

    def get_route_materials_used(self, route_id: int) -> pd.DataFrame:
        sql = """
            SELECT
                m.material_name AS vat_tu,
                m.unit AS don_vi,
                SUM(im.quantity) AS tong_su_dung
            FROM incident_material im
            JOIN incident i ON i.incident_id = im.incident_id
            JOIN material m ON m.material_id = im.material_id
            WHERE i.route_id = %s
            GROUP BY m.material_name, m.unit
            ORDER BY tong_su_dung DESC
        """
        return self._query_df(sql, (route_id,))

    # ------------------------------------------------------------------
    # 3.3 Bản đồ tuyến
    # ------------------------------------------------------------------

    def get_route_incidents_with_coords(self, route_id: int) -> pd.DataFrame:
        sql = """
            SELECT
                i.incident_id, i.incident_code AS ma_su_co, i.status AS trang_thai,
                i.latitude, i.longitude, i.reported_at
            FROM incident i
            WHERE i.route_id = %s
            ORDER BY i.reported_at DESC
        """
        return self._query_df(sql, (route_id,))
