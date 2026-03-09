import asyncio
import logging
from sqlalchemy import create_engine, text
from app.config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_db")

async def seed():
    """
    Seeds the database with initial mock data for RAG and persistent sessions.
    """
    engine = create_engine(settings.DATABASE_URL.replace("postgresql+psycopg", "postgresql"))
    
    with engine.connect() as conn:
        logger.info("Initializing pgvector extension...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        
        logger.info("Creating mock RAG documents...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                embedding vector(1536)
            );
        """))
        
        # Insert some sample product data
        sample_docs = [
            ("Sản phẩm Smart-Watch X1: Chống nước IP68, pin 10 ngày, giá 2.000.000 VNĐ.", [0.1] * 1536),
            ("Chính sách bảo hành: 1 đổi 1 trong 30 ngày nếu có lỗi nhà sản xuất.", [0.2] * 1536),
            ("Hướng dẫn sử dụng: Kết nối với app Smart-Bot trên cả iOS và Android.", [0.3] * 1536)
        ]
        
        for content, embedding in sample_docs:
            conn.execute(
                text("INSERT INTO documents (content, embedding) VALUES (:c, :e) ON CONFLICT DO NOTHING"),
                {"c": content, "e": str(embedding)}
            )
        
        conn.commit()
        logger.info("Database seeding completed successfully.")

if __name__ == "__main__":
    asyncio.run(seed())
