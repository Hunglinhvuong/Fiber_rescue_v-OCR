#!/usr/bin/env bash
# ============================================================
# Chạy OCR worker (poll bảng coordinate_extraction, gọi trực tiếp
# OCR provider cloud theo OCR_PROVIDER_ORDER trong .env — mặc định
# OCR.space rồi fallback Google Vision, xem ocr/service.py). Dùng
# venv chung tại gốc dự án.
# Được gọi bởi systemd service "Fiber_rescue-OcrWorker".
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

exec "$VENV_BIN/python" -m workers.ocr_worker
