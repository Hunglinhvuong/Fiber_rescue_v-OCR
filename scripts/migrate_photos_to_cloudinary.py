"""
Script MỘT LẦN: cập nhật cột incident_photo.file_path từ đường dẫn local
(storage/photos/...) sang URL Cloudinary.

Cách xử lý cho từng ảnh còn lưu đường dẫn local:
    1. Thử khớp theo tên file với ảnh đã có sẵn trên Cloudinary (phòng trường
       hợp đã upload thủ công trước đó).
    2. Nếu không khớp được nhưng file VẪN CÒN TRÊN ĐĨA server -> tự động
       upload thẳng file đó lên Cloudinary (đọc trực tiếp từ đĩa, không cần
       đoán tên nữa).
    3. Nếu không khớp và file cũng không còn trên đĩa -> báo là ảnh đã mất,
       hỏi xác nhận để XOÁ dòng đó khỏi incident_photo (không thể khôi phục).

Cách dùng:
    python scripts/migrate_photos_to_cloudinary.py --dry-run   # xem trước, KHÔNG sửa gì
    python scripts/migrate_photos_to_cloudinary.py             # thực sự cập nhật (có xác nhận)
    python scripts/migrate_photos_to_cloudinary.py --prefix fiber_rescue/photos

Yêu cầu .env đã có đủ CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY /
CLOUDINARY_API_SECRET và các biến DB_* như bình thường. Nếu chạy trên máy chủ
gốc (nơi các file storage/photos/ cũ còn tồn tại) thì bước 2 (tự upload) mới
hoạt động được.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras

from config.settings import settings
from utils.cloudinary_client import list_all_resources, upload_image_bytes


def _find_cloud_match(local_basename: str, cloud_map: dict):
    """Thử khớp theo nhiều chiến lược, từ chặt tới lỏng."""
    if local_basename in cloud_map:
        return cloud_map[local_basename]
    for cloud_basename, url in cloud_map.items():
        if cloud_basename.startswith(local_basename):
            return url
    local_lower = local_basename.lower()
    for cloud_basename, url in cloud_map.items():
        if cloud_basename.lower() == local_lower:
            return url
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Chỉ xem trước, không cập nhật DB")
    parser.add_argument("--prefix", default="", help="Prefix folder trên Cloudinary (nếu có)")
    parser.add_argument(
        "--no-upload", action="store_true",
        help="Chỉ thử khớp theo tên, KHÔNG tự upload file local còn sót",
    )
    args = parser.parse_args()

    if not settings.cloudinary_cloud_name:
        print("❌ Chưa cấu hình CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET trong .env")
        sys.exit(1)

    if settings.cloudinary_proxy:
        print(f"▶ Dùng proxy: {settings.cloudinary_proxy}")
    else:
        print("▶ Không cấu hình proxy (kết nối trực tiếp).")

    print("▶ Đang tải danh sách ảnh từ Cloudinary...")
    cloud_map = list_all_resources(args.prefix)
    print(f"  -> Tìm thấy {len(cloud_map)} ảnh trên Cloudinary.")

    conn = psycopg2.connect(
        host=settings.db_host, port=settings.db_port, dbname=settings.db_name,
        user=settings.db_user, password=settings.db_password,
    )
    read_cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    read_cur.execute(
        "SELECT photo_id, file_path FROM incident_photo WHERE file_path NOT LIKE 'http%'"
    )
    rows = read_cur.fetchall()
    print(f"▶ Có {len(rows)} ảnh trong DB đang lưu đường dẫn local (chưa migrate).")

    matched_by_name = []      # (photo_id, local_path, cloud_url)
    to_upload = []            # (photo_id, local_path)  - còn trên đĩa, cần tự upload
    lost = []                 # (photo_id, local_path)  - không khớp và cũng không còn trên đĩa

    for row in rows:
        local_path = row["file_path"]
        basename_no_ext = os.path.splitext(os.path.basename(local_path))[0]
        cloud_url = _find_cloud_match(basename_no_ext, cloud_map)

        if cloud_url:
            matched_by_name.append((row["photo_id"], local_path, cloud_url))
        elif not args.no_upload and os.path.exists(local_path):
            to_upload.append((row["photo_id"], local_path))
        else:
            lost.append((row["photo_id"], local_path))

    print(f"▶ Khớp theo tên có sẵn trên Cloudinary: {len(matched_by_name)}")
    print(f"▶ Còn trên đĩa, sẽ tự upload: {len(to_upload)}")
    print(f"▶ Không khớp và cũng KHÔNG còn trên đĩa (mất ảnh): {len(lost)}")
    if lost:
        for photo_id, p in lost[:20]:
            print(f"   ⚠️ MẤT: [id={photo_id}] {p}")
        if len(lost) > 20:
            print(f"   ... và {len(lost) - 20} ảnh khác")

    if args.dry_run:
        print("\n(--dry-run) Không thay đổi gì. Chạy lại không kèm --dry-run để áp dụng.")
        read_cur.close()
        conn.close()
        return

    if not matched_by_name and not to_upload and not lost:
        print("Không có gì để cập nhật.")
        read_cur.close()
        conn.close()
        return

    write_cur = conn.cursor()

    if matched_by_name or to_upload:
        total_changes = len(matched_by_name) + len(to_upload)
        confirm = input(
            f"\nCập nhật {len(matched_by_name)} dòng (khớp có sẵn) + "
            f"upload mới {len(to_upload)} ảnh từ đĩa = {total_changes} dòng. Gõ 'yes' để tiếp tục: "
        )
        if confirm.strip().lower() != "yes":
            print("Đã huỷ phần cập nhật/upload, không thay đổi gì.")
        else:
            for photo_id, _, cloud_url in matched_by_name:
                write_cur.execute(
                    "UPDATE incident_photo SET file_path = %s WHERE photo_id = %s",
                    (cloud_url, photo_id),
                )

            upload_errors = []
            for i, (photo_id, local_path) in enumerate(to_upload, start=1):
                print(f"  Upload {i}/{len(to_upload)}: {local_path}")
                try:
                    with open(local_path, "rb") as f:
                        file_bytes = f.read()
                    public_id = os.path.splitext(os.path.basename(local_path))[0]
                    session_dir_name = os.path.basename(os.path.dirname(local_path))
                    folder = f"{settings.cloudinary_folder}/{session_dir_name}"
                    result = upload_image_bytes(file_bytes, public_id, folder)
                    write_cur.execute(
                        "UPDATE incident_photo SET file_path = %s WHERE photo_id = %s",
                        (result["secure_url"], photo_id),
                    )
                except Exception as exc:
                    upload_errors.append((local_path, str(exc)))
                    print(f"    ❌ Lỗi: {exc}")

            conn.commit()
            print(f"\n✅ Đã cập nhật {len(matched_by_name)} dòng (khớp có sẵn) "
                  f"+ {len(to_upload) - len(upload_errors)} dòng (upload mới).")
            if upload_errors:
                print(f"⚠️  {len(upload_errors)} ảnh upload lỗi, chưa được cập nhật:")
                for p, err in upload_errors:
                    print(f"   - {p}: {err}")

    if lost:
        confirm_delete = input(
            f"\nXOÁ VĨNH VIỄN {len(lost)} dòng 'MẤT' khỏi incident_photo "
            "(không khớp Cloudinary, không còn trên đĩa, không thể khôi phục)? "
            "Gõ 'yes' để xác nhận: "
        )
        if confirm_delete.strip().lower() == "yes":
            for photo_id, _ in lost:
                write_cur.execute("DELETE FROM incident_photo WHERE photo_id = %s", (photo_id,))
            conn.commit()
            print(f"✅ Đã xoá {len(lost)} dòng ảnh bị mất.")
        else:
            print("Giữ nguyên các dòng ảnh bị mất (CHƯA xoá) — script migrate_incident_photo_schema.py "
                  "sẽ vẫn báo lỗi cho tới khi các dòng này được xử lý.")

    read_cur.close()
    write_cur.close()
    conn.close()


if __name__ == "__main__":
    main()
