import asyncio
import psycopg
import uuid
import logging
from app.memory.chat_history import ChatHistoryTracker
from app.utils.db import get_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_session_meta")

def test_session_metadata():
    print("--- KIỂM TRA BẢNG SESSION_METADATA ---")
    
    test_session_id = str(uuid.uuid4())
    test_user_id = "test_user_123"
    
    conn_str = "postgresql://admin:admin@localhost:5432/smartsales"
    
    try:
        with psycopg.connect(conn_str) as conn:
            with conn.cursor() as cur:
                # Kiểm tra bảng có tồn tại không
                cur.execute("SELECT to_regclass('public.session_metadata')")
                exists = cur.fetchone()
                if not exists[0]:
                    print("❌ LỖI: Bảng 'session_metadata' không tồn tại trong database!")
                    return

                print(f"1. Đang thử chèn session mới: {test_session_id} cho user: {test_user_id}")
                cur.execute(
                    "INSERT INTO session_metadata (session_id, user_id) VALUES (%s, %s)",
                    (test_session_id, test_user_id)
                )
                conn.commit()
                print("✅ Đã chèn thành công.")

                # 2. Truy vấn lại để kiểm tra
                print("2. Kiểm tra lại dữ liệu vừa chèn...")
                cur.execute("SELECT * FROM session_metadata WHERE session_id = %s", (test_session_id,))
                row = cur.fetchone()
                if row:
                    print(f"✅ DỮ LIỆU TÌM THẤY: session_id={row[0]}, user_id={row[1]}, created_at={row[2]}")
                else:
                    print("❌ LỖI: Không tìm thấy dữ liệu sau khi chèn!")

                # 3. Thống kê tổng số session
                cur.execute("SELECT COUNT(*) FROM session_metadata")
                total = cur.fetchone()[0]
                print(f"3. Tổng số bản ghi hiện có trong session_metadata: {total}")

                # 4. Check dữ liệu thực tế (nếu có)
                if total > 0:
                    print("\n--- 5 BẢN GHI MỚI NHẤT ---")
                    cur.execute("SELECT * FROM session_metadata ORDER BY created_at DESC LIMIT 5")
                    rows = cur.fetchall()
                    for r in rows:
                        print(f"Session: {r[0]} | User: {r[1]} | Time: {r[2]}")
                else:
                    print("\n⚠️ CẢNH BÁO: Bảng hiện tại đang trống. Điều này có nghĩa là API '/new-session' chưa bao giờ được gọi từ Frontend.")

    except Exception as e:
        print(f"❌ LỖI KHI KẾT NỐI DB: {e}")

if __name__ == "__main__":
    test_session_metadata()
