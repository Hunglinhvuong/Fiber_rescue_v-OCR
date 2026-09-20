from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from database.connection_sync import get_sync_connection, query_df, release_sync_connection


class ReportService:
    """Lớp truy vấn dữ liệu cho dashboard Streamlit — dùng kết nối đồng bộ
    (psycopg2), tách biệt hoàn toàn với pool asyncpg của bot Telegram."""

    def _query_df(self, sql: str, params: Optional[tuple] = None) -> pd.DataFrame:
        return query_df(sql, params)

    def _query_one(self, sql: str, params: Optional[tuple] = None) -> Optional[dict]:
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
    # Tổng quan
    # ------------------------------------------------------------------

    def get_summary_kpis(self) -> Dict:
        sql = """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'DRAFT') AS draft,
                COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed,
                COUNT(*) FILTER (WHERE reported_at::date = CURRENT_DATE) AS today,
                COUNT(*) FILTER (WHERE reported_at >= CURRENT_DATE - INTERVAL '7 days') AS last_7_days
            FROM incident
        """
        row = self._query_one(sql)
        return row or {"total": 0, "draft": 0, "completed": 0, "today": 0, "last_7_days": 0}

    def get_daily_counts(self, days: int = 30) -> pd.DataFrame:
        sql = """
            SELECT reported_at::date AS ngay, COUNT(*) AS so_su_co
            FROM incident
            WHERE reported_at >= CURRENT_DATE - (%s || ' days')::interval
            GROUP BY reported_at::date
            ORDER BY ngay
        """
        return self._query_df(sql, (days,))

    def get_cause_stats(self) -> pd.DataFrame:
        sql = """
            SELECT COALESCE(ic.cause_name, 'Chưa xác định') AS nguyen_nhan, COUNT(*) AS so_luong
            FROM incident i
            LEFT JOIN incident_cause ic ON ic.cause_id = i.cause_id
            GROUP BY nguyen_nhan
            ORDER BY so_luong DESC
        """
        return self._query_df(sql)

    def get_top_routes(self, limit: int = 10) -> pd.DataFrame:
        sql = """
            SELECT r.route_name AS tuyen, COUNT(*) AS so_su_co
            FROM incident i
            JOIN fiber_route r ON r.route_id = i.route_id
            GROUP BY r.route_name
            ORDER BY so_su_co DESC
            LIMIT %s
        """
        return self._query_df(sql, (limit,))

    # ------------------------------------------------------------------
    # Danh sách / lọc sự cố
    # ------------------------------------------------------------------

    def get_filter_options(self) -> Dict[str, pd.DataFrame]:
        return {
            "routes": self._query_df(
                "SELECT route_id, route_name FROM fiber_route ORDER BY route_name"
            ),
            "types": self._query_df(
                "SELECT incident_type_id, type_name FROM incident_type ORDER BY type_name"
            ),
            "causes": self._query_df(
                "SELECT cause_id, cause_name FROM incident_cause ORDER BY cause_name"
            ),
        }

    def search_incidents(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        status: Optional[str] = None,
        route_id: Optional[int] = None,
        incident_type_id: Optional[int] = None,
        cause_id: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> pd.DataFrame:
        conditions = ["1=1"]
        params: List = []

        if date_from:
            conditions.append("i.reported_at::date >= %s")
            params.append(date_from)
        if date_to:
            conditions.append("i.reported_at::date <= %s")
            params.append(date_to)
        if status:
            conditions.append("i.status = %s")
            params.append(status)
        if route_id:
            conditions.append("i.route_id = %s")
            params.append(route_id)
        if incident_type_id:
            conditions.append("i.incident_type_id = %s")
            params.append(incident_type_id)
        if cause_id:
            conditions.append("i.cause_id = %s")
            params.append(cause_id)
        if keyword:
            conditions.append("(i.incident_code ILIKE %s OR r.route_name ILIKE %s)")
            like = f"%{keyword}%"
            params.extend([like, like])

        sql = f"""
            SELECT
                i.incident_id,
                i.incident_code AS ma_su_co,
                i.status AS trang_thai,
                r.route_name AS tuyen,
                it.type_name AS loai_su_co,
                ic.cause_name AS nguyen_nhan,
                rst.span_name AS doan_khac_phuc,
                u.full_name AS nguoi_bao_cao,
                i.reported_at AS thoi_gian_bao_cao,
                i.completed_at AS thoi_gian_hoan_tat,
                i.latitude,
                i.longitude
            FROM incident i
            JOIN fiber_route r ON r.route_id = i.route_id
            JOIN incident_type it ON it.incident_type_id = i.incident_type_id
            LEFT JOIN incident_cause ic ON ic.cause_id = i.cause_id
            JOIN repair_span_type rst ON rst.repair_span_type_id = i.repair_span_type_id
            JOIN app_user u ON u.user_id = i.reported_by
            WHERE {' AND '.join(conditions)}
            ORDER BY i.reported_at DESC
        """
        return self._query_df(sql, tuple(params))

    def get_incidents_with_coords(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        status: Optional[str] = None,
    ) -> pd.DataFrame:
        return self.search_incidents(date_from=date_from, date_to=date_to, status=status)

    # ------------------------------------------------------------------
    # Chi tiết 1 sự cố
    # ------------------------------------------------------------------

    def get_incident_detail(self, incident_id: int) -> Optional[Dict]:
        sql = """
            SELECT
                i.incident_id, i.incident_code, i.status, i.description,
                i.latitude, i.longitude, i.location_accuracy_m,
                i.reported_at, i.completed_at,
                r.route_name, r.route_code, r.cable_type, r.fiber_count,
                u.full_name AS reporter_name, u.team_name,
                it.type_name, ic.cause_name, rst.span_name
            FROM incident i
            JOIN fiber_route r ON r.route_id = i.route_id
            JOIN app_user u ON u.user_id = i.reported_by
            JOIN incident_type it ON it.incident_type_id = i.incident_type_id
            LEFT JOIN incident_cause ic ON ic.cause_id = i.cause_id
            JOIN repair_span_type rst ON rst.repair_span_type_id = i.repair_span_type_id
            WHERE i.incident_id = %s
        """
        return self._query_one(sql, (incident_id,))

    def get_incident_materials(self, incident_id: int) -> pd.DataFrame:
        sql = """
            SELECT m.material_name AS vat_tu, m.unit AS don_vi, im.quantity AS so_luong
            FROM incident_material im
            JOIN material m ON m.material_id = im.material_id
            WHERE im.incident_id = %s
            ORDER BY m.material_group, m.material_name
        """
        return self._query_df(sql, (incident_id,))

    def get_incident_photos(self, incident_id: int) -> List[Dict]:
        sql = """
            SELECT photo_type, cloudinary_url, caption, created_at
            FROM incident_photo
            WHERE incident_id = %s
            ORDER BY incident_photo_id
        """
        return self._query_df(sql, (incident_id,)).to_dict("records")
