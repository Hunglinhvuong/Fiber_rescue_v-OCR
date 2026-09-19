#!/usr/bin/env bash
# ============================================================
# Chạy đồng thời bot Telegram + dashboard Streamlit, dùng chung 1
# virtualenv (venv/) ngay tại thư mục gốc dự án. Được gọi bởi
# systemd service "fiber_rescue" (xem fiber_rescue.service.template).
#
# Nếu 1 trong 2 tiến trình chết, script dừng luôn tiến trình còn lại
# và thoát với mã lỗi -> systemd (Restart=always) sẽ khởi động lại
# toàn bộ service.
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"
export PYTHONPATH="$SCRIPT_DIR"

VENV_BIN="$SCRIPT_DIR/venv/bin"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"

if [[ ! -x "$VENV_BIN/python" ]]; then
    echo "❌ Không thấy $VENV_BIN/python — chạy sudo ./deploy/install.sh trước." >&2
    exit 1
fi

pids=()

cleanup() {
    trap - TERM INT
    echo "▶ Đang dừng bot + dashboard ..."
    for pid in "${pids[@]:-}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup TERM INT

echo "▶ Khởi động bot Telegram ..."
"$VENV_BIN/python" app.py &
pids+=("$!")

echo "▶ Khởi động dashboard Streamlit (cổng $DASHBOARD_PORT) ..."
"$VENV_BIN/streamlit" run dashboard/app.py \
    --server.port "$DASHBOARD_PORT" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false &
pids+=("$!")

# Dừng cả 2 ngay khi 1 tiến trình bất kỳ thoát (crash hoặc bị kill)
set +e
wait -n "${pids[@]}"
EXIT_CODE=$?
set -e

echo "⚠ Một tiến trình đã dừng (exit code $EXIT_CODE) — dừng toàn bộ service."
cleanup
exit "$EXIT_CODE"
