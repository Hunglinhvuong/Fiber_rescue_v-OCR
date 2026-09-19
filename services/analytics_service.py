from datetime import date
from typing import Optional

import pandas as pd

from database.connection_sync import get_sync_connection, get_sync_engine, release_sync_connection

GRANULARITY_TRUNC = {
    "day": "day",
    "week": "week",
    "month": "month",
}


class AnalyticsService:
    """Truy vấn phục vụ trang Phân tích — dùng kết nối đồng bộ (psycopg2),
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
    # 1.1 Tổng quan sự cố
    # ------------------------------------------------------------------

    def get_incident_trend(self, date_from: date, date_to: date, granularity: str = "day") -> pd.DataFrame:
        trunc = GRANULARITY_TRUNC.get(granularity, "day")
        sql = f"""
            SELECT DATE_TRUNC('{trunc}', reported_at)::date AS ky, COUNT(*) AS so_su_co
            FROM incident
            WHERE reported_at::date BETWEEN %s AND %s
            GROUP BY ky
            ORDER BY ky
        """
        return self._query_df(sql, (date_from, date_to))

    def get_by_cause(self, date_from: date, date_to: date) -> pd.DataFrame:
        sql = """
            SELECT COALESCE(ic.cause_name, 'Chưa xác định') AS nguyen_nhan, COUNT(*) AS so_luong
            FROM incident i
            LEFT JOIN incident_cause ic ON ic.cause_id = i.cause_id
            WHERE i.reported_at::date BETWEEN %s AND %s
            GROUP BY nguyen_nhan
            ORDER BY so_luong DESC
        """
        return self._query_df(sql, (date_from, date_to))

    def get_by_route_type(self, date_from: date, date_to: date) -> pd.DataFrame:
        sql = """
            SELECT COALESCE(r.route_type, 'Chưa xác định') AS loai_tuyen, COUNT(*) AS so_su_co
            FROM incident i
            JOIN fiber_route r ON r.route_id = i.route_id
            WHERE i.reported_at::date BETWEEN %s AND %s
            GROUP BY loai_tuyen
            ORDER BY so_su_co DESC
        """
        return self._query_df(sql, (date_from, date_to))

    def get_trend_with_moving_avg(self, date_from: date, date_to: date, window: int = 7) -> pd.DataFrame:
        df = self.get_incident_trend(date_from, date_to, granularity="day")
        if df.empty:
            return df
        df["trung_binh_dong"] = df["so_su_co"].rolling(window=window, min_periods=1).mean()
        return df

    # ------------------------------------------------------------------
    # 1.2 Phân tích nguyên nhân
    # ------------------------------------------------------------------

    def get_cause_share(self, date_from: date, date_to: date) -> pd.DataFrame:
        df = self.get_by_cause(date_from, date_to)
        if df.empty:
            return df
        df["ty_trong"] = (df["so_luong"] / df["so_luong"].sum() * 100).round(1)
        return df

    def get_cause_trend_monthly(self, date_from: date, date_to: date) -> pd.DataFrame:
        sql = """
            SELECT
                DATE_TRUNC('month', i.reported_at)::date AS thang,
                COALESCE(ic.cause_name, 'Chưa xác định') AS nguyen_nhan,
                COUNT(*) AS so_luong
            FROM incident i
            LEFT JOIN incident_cause ic ON ic.cause_id = i.cause_id
            WHERE i.reported_at::date BETWEEN %s AND %s
            GROUP BY thang, nguyen_nhan
            ORDER BY thang
        """
        return self._query_df(sql, (date_from, date_to))

    def get_causes(self) -> pd.DataFrame:
        return self._query_df(
            "SELECT cause_id, cause_name FROM incident_cause WHERE is_active ORDER BY cause_name"
        )

    def get_routes_for_cause(self, cause_id: int, date_from: date, date_to: date) -> pd.DataFrame:
        sql = """
            SELECT r.route_id, r.route_name, COUNT(*) AS so_su_co
            FROM incident i
            JOIN fiber_route r ON r.route_id = i.route_id
            WHERE i.cause_id = %s AND i.reported_at::date BETWEEN %s AND %s
            GROUP BY r.route_id, r.route_name
            ORDER BY so_su_co DESC
        """
        return self._query_df(sql, (cause_id, date_from, date_to))

    def get_locations_for_cause_route(
        self, cause_id: int, route_id: int, date_from: date, date_to: date
    ) -> pd.DataFrame:
        sql = """
            SELECT
                i.incident_id, i.incident_code, i.latitude, i.longitude,
                i.reported_at, rst.span_name AS doan_khac_phuc
            FROM incident i
            JOIN repair_span_type rst ON rst.repair_span_type_id = i.repair_span_type_id
            WHERE i.cause_id = %s AND i.route_id = %s
              AND i.reported_at::date BETWEEN %s AND %s
            ORDER BY i.reported_at DESC
        """
        return self._query_df(sql, (cause_id, route_id, date_from, date_to))

    # ------------------------------------------------------------------
    # 1.3 Phân tích xu hướng / phát hiện bất thường
    #
    # Cách tiếp cận: so sánh số liệu N ngày gần đây với bình quân "nền"
    # (những ngày trước đó trong cửa sổ baseline, quy đổi về cùng độ dài N
    # ngày). Đối tượng được coi là bất thường nếu tỷ lệ tăng vượt ngưỡng
    # VÀ có đủ số lượng tối thiểu để tránh nhiễu do mẫu quá nhỏ.
    # ------------------------------------------------------------------

    def _anomaly_ratio(self, df: pd.DataFrame, recent_days: int, baseline_days: int) -> pd.DataFrame:
        baseline_span = baseline_days - recent_days
        if baseline_span <= 0:
            df["binh_quan_nen_quy_doi"] = 0
        else:
            df["binh_quan_nen_quy_doi"] = (df["nen_truoc"] / baseline_span * recent_days).round(2)
        df["binh_quan_nen_quy_doi"] = df["binh_quan_nen_quy_doi"].replace(0, pd.NA)
        df["ty_le_tang"] = (df["gan_day"] / df["binh_quan_nen_quy_doi"]).round(2)
        return df

    def detect_route_anomalies(
        self, recent_days: int = 30, baseline_days: int = 90, min_incidents: int = 3
    ) -> pd.DataFrame:
        sql = """
            SELECT
                r.route_id,
                r.route_name,
                COUNT(*) FILTER (
                    WHERE i.reported_at >= CURRENT_DATE - (%(recent)s || ' days')::interval
                ) AS gan_day,
                COUNT(*) FILTER (
                    WHERE i.reported_at >= CURRENT_DATE - (%(baseline)s || ' days')::interval
                      AND i.reported_at < CURRENT_DATE - (%(recent)s || ' days')::interval
                ) AS nen_truoc
            FROM incident i
            JOIN fiber_route r ON r.route_id = i.route_id
            WHERE i.reported_at >= CURRENT_DATE - (%(baseline)s || ' days')::interval
            GROUP BY r.route_id, r.route_name
        """
        df = self._query_df(sql, {"recent": recent_days, "baseline": baseline_days})
        if df.empty:
            return df
        df = self._anomaly_ratio(df, recent_days, baseline_days)
        result = df[(df["gan_day"] >= min_incidents) & (df["ty_le_tang"].notna())]
        return result.sort_values("ty_le_tang", ascending=False).reset_index(drop=True)

    def detect_cause_anomalies(
        self, recent_days: int = 30, baseline_days: int = 90, min_incidents: int = 3
    ) -> pd.DataFrame:
        sql = """
            SELECT
                COALESCE(ic.cause_name, 'Chưa xác định') AS nguyen_nhan,
                COUNT(*) FILTER (
                    WHERE i.reported_at >= CURRENT_DATE - (%(recent)s || ' days')::interval
                ) AS gan_day,
                COUNT(*) FILTER (
                    WHERE i.reported_at >= CURRENT_DATE - (%(baseline)s || ' days')::interval
                      AND i.reported_at < CURRENT_DATE - (%(recent)s || ' days')::interval
                ) AS nen_truoc
            FROM incident i
            LEFT JOIN incident_cause ic ON ic.cause_id = i.cause_id
            WHERE i.reported_at >= CURRENT_DATE - (%(baseline)s || ' days')::interval
            GROUP BY nguyen_nhan
        """
        df = self._query_df(sql, {"recent": recent_days, "baseline": baseline_days})
        if df.empty:
            return df
        df = self._anomaly_ratio(df, recent_days, baseline_days)
        result = df[(df["gan_day"] >= min_incidents) & (df["ty_le_tang"].notna())]
        return result.sort_values("ty_le_tang", ascending=False).reset_index(drop=True)

    def detect_material_anomalies(
        self, recent_days: int = 30, baseline_days: int = 90, min_qty: float = 1.0
    ) -> pd.DataFrame:
        sql = """
            SELECT
                m.material_id,
                m.material_name,
                m.unit,
                COALESCE(SUM(im.quantity) FILTER (
                    WHERE i.reported_at >= CURRENT_DATE - (%(recent)s || ' days')::interval
                ), 0) AS gan_day,
                COALESCE(SUM(im.quantity) FILTER (
                    WHERE i.reported_at >= CURRENT_DATE - (%(baseline)s || ' days')::interval
                      AND i.reported_at < CURRENT_DATE - (%(recent)s || ' days')::interval
                ), 0) AS nen_truoc
            FROM incident_material im
            JOIN incident i ON i.incident_id = im.incident_id
            JOIN material m ON m.material_id = im.material_id
            WHERE i.reported_at >= CURRENT_DATE - (%(baseline)s || ' days')::interval
            GROUP BY m.material_id, m.material_name, m.unit
        """
        df = self._query_df(sql, {"recent": recent_days, "baseline": baseline_days})
        if df.empty:
            return df
        df = self._anomaly_ratio(df, recent_days, baseline_days)
        result = df[(df["gan_day"] >= min_qty) & (df["ty_le_tang"].notna())]
        return result.sort_values("ty_le_tang", ascending=False).reset_index(drop=True)
