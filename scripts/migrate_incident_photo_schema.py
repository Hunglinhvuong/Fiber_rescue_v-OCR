"""
Script MỘT LẦN: nâng cấp cấu trúc bảng incident_photo sang lưu trực tiếp
metadata Cloudinary (cloudinary_public_id, cloudinary_asset_id, cloudinary_url)
thay vì cột file_path dùng chung như trước, đổi tên photo_id -> incident_photo_id
và uploaded_at -> created_at.

YÊU CẦU: đã chạy xong scripts/migrate_photos_to_cloudinary.py trước (toàn bộ
file_path trong DB phải là URL Cloudinary, không còn đường dẫn local).

Cách dùng:
    python scripts/migrate_incident_photo_schema.py --dry-run   # xem trước, KHÔNG sửa DB
    python scripts/migrate_incident_photo_schema.py             # thực sự áp dụng (có xác nhận)
"""
import argparse
import os
import re
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras

from config.settings import settings

# VD URL: https://res.cloudinary.com/<cloud>/image/upload/v169.../fiber_rescue/photos/<session>/<file>.jpg
# -> public_id = fiber_rescue/photos/<session>/<file>
PUBLIC_ID_RE = re.compile(r"/upload/(?:v\d+/)?(.+)\.[A-Za-z0-9]+(?:\?.*)?$")


def extract_public_id(url: str) -> Optional[str]:
    match = PUBLIC_ID_RE.search(url)
    return match.group(1) if match else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Chỉ xem trước, không thay đổi DB")
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=settings.db_host, port=settings.db_port, dbname=settings.db_name,
        user=settings.db_user, password=settings.db_password,
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 0. Chặn nếu còn ảnh chưa migrate sang Cloudinary (còn đường dẫn local)
    cur.execute("SELECT COUNT(*) AS cnt FROM incident_photo WHERE file_path NOT LIKE 'http%'")
    remaining_local = cur.fetchone()["cnt"]
    if remaining_local > 0:
        print(f"❌ Còn {remaining_local} ảnh chưa migrate sang Cloudinary.")
        print("   Chạy scripts/migrate_photos_to_cloudinary.py trước rồi chạy lại script này.")
        conn.close()
        return

    # 1. Thêm cột mới (an toàn nếu chạy lại nhiều lần nhờ IF NOT EXISTS)
    cur.execute("""
        ALTER TABLE incident_photo
            ADD COLUMN IF NOT EXISTS cloudinary_public_id TEXT,
            ADD COLUMN IF NOT EXISTS cloudinary_asset_id TEXT,
            ADD COLUMN IF NOT EXISTS cloudinary_url TEXT
    """)

    # 2. Backfill cloudinary_url (= file_path cũ) + cloudinary_public_id (suy ra từ URL)
    cur.execute("SELECT photo_id, file_path FROM incident_photo WHERE cloudinary_url IS NULL")
    rows = cur.fetchall()
    print(f"▶ Cần backfill {len(rows)} dòng.")

    updates = []
    unmatched = []
    for row in rows:
        public_id = extract_public_id(row["file_path"])
        if public_id is None:
            unmatched.append(row["file_path"])
        updates.append((row["file_path"], public_id, row["photo_id"]))

    if unmatched:
        print(f"⚠️  {len(unmatched)} URL không tách được public_id (vẫn backfill cloudinary_url, "
              f"để trống cloudinary_public_id) - không ảnh hưởng hiển thị ảnh:")
        for u in unmatched[:10]:
            print(f"   - {u}")

    print("\nCác bước sẽ thực hiện:")
    print(f"  - Backfill cloudinary_url/cloudinary_public_id cho {len(updates)} dòng")
    print("  - Bắt buộc NOT NULL cho cloudinary_url")
    print("  - Thêm UNIQUE constraint cho cloudinary_public_id")
    print("  - Xoá cột file_path")
    print("  - Đổi tên photo_id -> incident_photo_id")
    print("  - Đổi tên uploaded_at -> created_at")

    if args.dry_run:
        print("\n(--dry-run) Không thay đổi gì. Chạy lại không kèm --dry-run để áp dụng.")
        conn.rollback()
        conn.close()
        return

    confirm = input("\nÁp dụng các thay đổi trên? Gõ 'yes' để tiếp tục: ")
    if confirm.strip().lower() != "yes":
        print("Đã huỷ, không thay đổi gì.")
        conn.rollback()
        conn.close()
        return

    for file_path, public_id, photo_id in updates:
        cur.execute(
            "UPDATE incident_photo SET cloudinary_url = %s, cloudinary_public_id = %s WHERE photo_id = %s",
            (file_path, public_id, photo_id),
        )

    cur.execute("ALTER TABLE incident_photo ALTER COLUMN cloudinary_url SET NOT NULL")
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_incident_photo_cloudinary_public_id'
            ) THEN
                ALTER TABLE incident_photo
                    ADD CONSTRAINT uq_incident_photo_cloudinary_public_id UNIQUE (cloudinary_public_id);
            END IF;
        END $$;
    """)
    cur.execute("ALTER TABLE incident_photo DROP COLUMN file_path")
    cur.execute("ALTER TABLE incident_photo RENAME COLUMN photo_id TO incident_photo_id")
    cur.execute("ALTER TABLE incident_photo RENAME COLUMN uploaded_at TO created_at")

    conn.commit()
    print(f"\n✅ Đã nâng cấp cấu trúc incident_photo (backfill {len(updates)} dòng).")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
