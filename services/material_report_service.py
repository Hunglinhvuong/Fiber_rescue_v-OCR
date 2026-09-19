from datetime import date
from typing import List, Optional

import pandas as pd

from database.connection_sync import get_sync_connection, get_sync_engine, release_sync_connection

MATERIAL_GROUP_LABELS = {
    "CABLE": "Cáp",
    "HANGER": "Treo",
    "ANCHOR": "Néo",
    "SPLICE_CLOSURE": "Hộp nối",
    "CLAMP": "Kẹp",
    "PIPE": "Ống",
    "POLE_BAND": "Đai cột",
    "OTHERS": "Khác",
}


class MaterialReportService:
    """Truy vấn phục vụ trang Vật tư — dùng kết nối đồng bộ (psycopg2),
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
    # 2.1 Danh mục vật tư
    # ------------------------------------------------------------------

    def get_material_catalog(
        self, group: Optional[str] = None, active_only: bool = False, keyword: Optional[str] = None
    ) -> pd.DataFrame:
        conditions = ["1=1"]
        params: List = []
        if group:
            conditions.append("material_group = %s")
            params.append(group)
        if active_only:
            conditions.append("is_active = TRUE")
        if keyword:
            conditions.append("(material_code ILIKE %s OR material_name ILIKE %s)")
            like = f"%{keyword}%"
            params.extend([like, like])
        sql = f"""
            SELECT
                material_code AS ma_vat_tu,
                material_name AS ten_vat_tu,
                material_group AS nhom_vat_tu,
                unit AS don_vi_tinh,
                CASE WHEN is_active THEN 'Đang dùng' ELSE 'Ngừng dùng' END AS trang_thai
            FROM material
            WHERE {' AND '.join(conditions)}
            ORDER BY material_group, material_name
        """
        df = self._query_df(sql, tuple(params))
        if not df.empty:
            df["nhom_vat_tu"] = df["nhom_vat_tu"].map(lambda g: MATERIAL_GROUP_LABELS.get(g, g))
        return df

    def get_material_groups(self) -> List[str]:
        df = self._query_df("SELECT DISTINCT material_group FROM material ORDER BY material_group")
        return df["material_group"].tolist()

    # ------------------------------------------------------------------
    # 2.2 Phân tích tiêu hao
    # ------------------------------------------------------------------

    def get_material_per_incident(self, date_from: date, date_to: date) -> pd.DataFrame:
        sql = """
            SELECT
                m.material_name AS vat_tu,
                m.unit AS don_vi,
                COUNT(DISTINCT im.incident_id) AS so_su_co_dung,
                SUM(im.quantity) AS tong_so_luong,
                ROUND(SUM(im.quantity) / NULLIF(COUNT(DISTINCT im.incident_id), 0), 2) AS binh_quan_moi_su_co
            FROM incident_material im
            JOIN incident i ON i.incident_id = im.incident_id
            JOIN material m ON m.material_id = im.material_id
            WHERE i.reported_at::date BETWEEN %s AND %s
            GROUP BY m.material_name, m.unit
            ORDER BY tong_so_luong DESC
        """
        return self._query_df(sql, (date_from, date_to))

    def get_cable_per_incident(self, date_from: date, date_to: date) -> dict:
        sql = """
            SELECT
                COUNT(DISTINCT i.incident_id) AS so_su_co,
                COALESCE(SUM(im.quantity), 0) AS tong_met_cap,
                ROUND(SUM(im.quantity) / NULLIF(COUNT(DISTINCT i.incident_id), 0), 2) AS binh_quan_met_moi_su_co
            FROM incident_material im
            JOIN incident i ON i.incident_id = im.incident_id
            JOIN material m ON m.material_id = im.material_id
            WHERE m.material_group = 'CABLE'
              AND i.reported_at::date BETWEEN %s AND %s
        """
        row = self._query_one(sql, (date_from, date_to))
        return row or {"so_su_co": 0, "tong_met_cap": 0, "binh_quan_met_moi_su_co": 0}

    def compare_routes_consumption(
        self, date_from: date, date_to: date, material_group: Optional[str] = None
    ) -> pd.DataFrame:
        conditions = ["i.reported_at::date BETWEEN %s AND %s"]
        params: List = [date_from, date_to]
        if material_group:
            conditions.append("m.material_group = %s")
            params.append(material_group)
        sql = f"""
            SELECT
                r.route_name AS tuyen,
                SUM(im.quantity) AS tong_tieu_hao,
                COUNT(DISTINCT i.incident_id) AS so_su_co
            FROM incident_material im
            JOIN incident i ON i.incident_id = im.incident_id
            JOIN fiber_route r ON r.route_id = i.route_id
            JOIN material m ON m.material_id = im.material_id
            WHERE {' AND '.join(conditions)}
            GROUP BY r.route_name
            ORDER BY tong_tieu_hao DESC
        """
        return self._query_df(sql, tuple(params))

    # ------------------------------------------------------------------
    # 2.3 Thống kê sử dụng vật tư
    # ------------------------------------------------------------------

    def get_material_usage_summary(
        self,
        date_from: date,
        date_to: date,
        route_id: Optional[int] = None,
        cable_type: Optional[str] = None,
        cause_id: Optional[int] = None,
    ) -> pd.DataFrame:
        conditions = ["i.reported_at::date BETWEEN %s AND %s"]
        params: List = [date_from, date_to]
        if route_id:
            conditions.append("i.route_id = %s")
            params.append(route_id)
        if cable_type:
            conditions.append("r.cable_type = %s")
            params.append(cable_type)
        if cause_id:
            conditions.append("i.cause_id = %s")
            params.append(cause_id)
        sql = f"""
            SELECT
                m.material_code AS ma_vat_tu,
                m.material_name AS ten_vat_tu,
                m.unit AS don_vi,
                SUM(im.quantity) AS tong_su_dung,
                COUNT(DISTINCT im.incident_id) AS so_su_co
            FROM incident_material im
            JOIN incident i ON i.incident_id = im.incident_id
            JOIN fiber_route r ON r.route_id = i.route_id
            JOIN material m ON m.material_id = im.material_id
            WHERE {' AND '.join(conditions)}
            GROUP BY m.material_code, m.material_name, m.unit
            ORDER BY tong_su_dung DESC
        """
        return self._query_df(sql, tuple(params))
