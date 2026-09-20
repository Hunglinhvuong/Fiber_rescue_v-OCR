#!/usr/bin/env bash
# ============================================================
# Chạy riêng dashboard Streamlit. Dùng venv chung tại gốc dự án.
# Được gọi bởi systemd service "Fiber_rescue-dashboard".
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"
export PYTHONPATH="$SCRIPT_DIR"

VENV_BIN="$SCRIPT_DIR/venv/bin"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"

if [[ ! -x "$VENV_BIN/streamlit" ]]; then
    echo "❌ Không thấy $VENV_BIN/streamlit — chạy sudo ./deploy/install.sh trước." >&2
    exit 1
fi

exec "$VENV_BIN/streamlit" run dashboard/app.py \
    --server.port "$DASHBOARD_PORT" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
