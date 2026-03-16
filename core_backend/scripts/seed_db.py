import asyncio
import logging
from sqlalchemy import create_engine, text
from app.config.settings import settings
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_db")

async def seed():
    """
    Seeds the database with initial mock data for RAG and authentication.
    """
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            # Clean start (Optional based on how you want seed to behave)
            conn.execute(text("TRUNCATE TABLE documents, users RESTART IDENTITY CASCADE;"))
            
            # 1. Seed Users
            logger.info("Seeding users...")
            # Pre-calculated bcrypt hash for 'admin123'
            admin_password_hash = "$2b$12$e63a8oaoD.V6L9n./ueBXudGO8AadNLy5nOjmpsJ2Er2uO/0sKcbe"
            
            conn.execute(text("""
                INSERT INTO users (user_id, password_hash, role, is_active, created_at)
                VALUES (:u, :p, :r, :a, now())
            """), {
                "u": "admin",
                "p": admin_password_hash,
                "r": "admin",
                "a": True
            })
            logger.info("User 'admin' seeded.")

            # 2. Seed Documents for RAG
            logger.info("Seeding RAG documents...")
            sample_docs = [
                ("Hệ thống Smart-Bot hỗ trợ trả lời tự động khách hàng qua Zalo và Facebook.", [0.1] * settings.EMBEDDING_DIM),
                ("Chính sách bảo hành sản phẩm Smart-Bot là 12 tháng kể từ ngày kích hoạt.", [0.2] * settings.EMBEDDING_DIM),
                ("Để cài đặt Smart-Bot, bạn cần truy cập vào trang quản trị và nhập mã API Key.", [0.3] * settings.EMBEDDING_DIM),
                ("Smart-Bot có khả năng nhận diện hình ảnh và giọng nói của khách hàng.", [0.4] * settings.EMBEDDING_DIM),
                ("Thủ đô của Việt Nam là Hà Nội, một thành phố ngàn năm văn hiến.", [0.5] * settings.EMBEDDING_DIM)
            ]
            
            for content, embedding in sample_docs:
                conn.execute(
                    text("INSERT INTO documents (content, embedding) VALUES (:c, :e)"),
                    {"c": content, "e": str(embedding)}
                )
            
            conn.commit()
            logger.info("Database seeding completed successfully.")
    except Exception as e:
        logger.error(f"Critical seeding error: {e}")

if __name__ == "__main__":
    asyncio.run(seed())
