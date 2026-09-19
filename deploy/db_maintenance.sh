#!/usr/bin/env bash
# ============================================================
# Kiểm tra & tối ưu dung lượng cho Fiber Rescue Bot — đặc biệt hữu ích
# trên máy ảo ổ cứng nhỏ (VD 15GB).
#
# Dùng:
#   ./deploy/db_maintenance.sh [thư_mục_cài_đặt]   (mặc định /opt/fiber_rescue)
#
# Yêu cầu: đã cài postgresql-client (lệnh psql), file .env có sẵn trong
# thư mục cài đặt.
#
# Script này CHỈ làm các việc AN TOÀN (đọc thông tin + VACUUM ANALYZE bình
# thường) — không xoá dữ liệu, không xoá ảnh, không đổi cấu hình Postgres.
# ============================================================
set -euo pipefail

INSTALL_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="$INSTALL_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ Không thấy $ENV_FILE"
    exit 1
fi

command -v psql >/dev/null 2>&1 || {
    echo "❌ Chưa cài psql. Cài bằng: sudo apt install postgresql-client"
    exit 1
}

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export PGPASSWORD="${DB_PASSWORD:-}"
PSQL=(psql -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}" -d "${DB_NAME:-fiber_rescue}")

echo "======================================================"
echo "1. DUNG LƯỢNG Ổ ĐĨA TỔNG QUAN"
echo "======================================================"
df -h /

echo ""
echo "======================================================"
echo "2. DUNG LƯỢNG ẢNH ĐÃ LƯU (thường là nguồn phình ổ đĩa lớn nhất)"
echo "======================================================"
PHOTO_DIR="$INSTALL_DIR/${PHOTO_STORAGE_DIR:-storage/photos}"
if [[ -d "$PHOTO_DIR" ]]; then
    du -sh "$PHOTO_DIR" 2>/dev/null || true
    echo "Số lượng file ảnh: $(find "$PHOTO_DIR" -type f 2>/dev/null | wc -l)"
else
    echo "(không tìm thấy $PHOTO_DIR)"
fi

echo ""
echo "======================================================"
echo "3. DUNG LƯỢNG DATABASE + TOP 10 BẢNG LỚN NHẤT"
echo "======================================================"
"${PSQL[@]}" -c "SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size;"
"${PSQL[@]}" -c "
SELECT relname AS table_name,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
       n_live_tup AS live_rows,
       n_dead_tup AS dead_rows
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;
"

echo ""
echo "======================================================"
echo "4. VACUUM + ANALYZE (dọn dead tuple, cập nhật thống kê cho query planner)"
echo "======================================================"
"${PSQL[@]}" -c "VACUUM (VERBOSE, ANALYZE);" 2>&1 | tail -30

echo ""
echo "======================================================"
echo "5. DUNG LƯỢNG JOURNAL LOG (systemd) — thường bị bỏ quên"
echo "======================================================"
if command -v journalctl >/dev/null 2>&1; then
    journalctl --disk-usage 2>/dev/null || echo "(cần sudo để xem đầy đủ: sudo journalctl --disk-usage)"
else
    echo "(không có journalctl)"
fi

echo ""
echo "✅ Hoàn tất kiểm tra. Nếu dung lượng ảnh đang lớn, xem gợi ý dọn/di dời"
echo "   trong README (mục 'Bảo trì & tối ưu dung lượng')."
