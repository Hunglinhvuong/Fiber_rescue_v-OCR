#!/usr/bin/env bash
# ============================================================
# Chạy riêng bot Telegram. Dùng venv chung tại gốc dự án.
# Được gọi bởi systemd service "Fiber_rescue-teleBot".
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"
export PYTHONPATH="$SCRIPT_DIR"

VENV_BIN="$SCRIPT_DIR/venv/bin"
if [[ ! -x "$VENV_BIN/python" ]]; then
    echo "❌ Không thấy $VENV_BIN/python — chạy sudo ./deploy/install.sh trước." >&2
    exit 1
fi

exec "$VENV_BIN/python" app.py
