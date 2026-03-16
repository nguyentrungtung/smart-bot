import argparse
import logging
from sqlalchemy import create_engine, text
from app.config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clear_memory")

# Map command line flags to database tables
MEMORY_TARGETS = {
    "long_term": ["user_profiles"],
    "short_term": ["checkpoints", "checkpoint_writes", "checkpoint_blobs", "checkpoint_migrations"],
    "analytics": ["chat_interactions", "session_metadata"]
}

def clear_tables(tables: list, engine) -> None:
    """
    Truncates a list of tables and cascades their dependencies.
    """
    if not tables:
        return

    joined_tables = ", ".join(tables)
    truncate_query = text(f"TRUNCATE TABLE {joined_tables} RESTART IDENTITY CASCADE;")
    
    try:
        with engine.connect() as conn:
            # Postgres TRUNCATE works on all named tables simultaneously
            conn.execute(truncate_query)
            conn.commit()
            logger.info(f"✅ Successfully CLEARED: {joined_tables}")
    except Exception as e:
        logger.error(f"❌ Failed to clear tables {joined_tables}: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="Tool để clear (truncate) các bảng lưu trữ bộ nhớ của Smart-Bot.")
    parser.add_argument("--long-term", action="store_true", help="Xóa Long-Term Memory (sở thích, thông tin cá nhân trong bảng user_profiles)")
    parser.add_argument("--short-term", action="store_true", help="Xóa Short-Term Memory (ngữ cảnh chat tức thời trong các bảng checkpoints của LangGraph)")
    parser.add_argument("--analytics", action="store_true", help="Xóa Chat Analytics & Session (bảng chat_interactions, session_metadata)")
    parser.add_argument("--all", action="store_true", help="Xóa toàn bộ các bảng trên (long-term, short-term, analytics)")
    
    args = parser.parse_args()
    
    # Check if no arguments were provided
    if not (args.long_term or args.short_term or args.analytics or args.all):
        parser.print_help()
        logger.warning("\n⚠️ Vui lòng cung cấp ít nhất một tham số để quyết định phần bộ nhớ nào sẽ bị xóa!")
        return

    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        
    engine = create_engine(db_url)
    
    tables_to_clear = []
    
    if args.all or args.long_term:
        tables_to_clear.extend(MEMORY_TARGETS["long_term"])
        logger.info("[MODE] Đã chọn dọn dẹp Long-Term Memory")
        
    if args.all or args.short_term:
        tables_to_clear.extend(MEMORY_TARGETS["short_term"])
        logger.info("[MODE] Đã chọn dọn dẹp Short-Term Memory (LangGraph Checkpoints)")
        
    if args.all or args.analytics:
        tables_to_clear.extend(MEMORY_TARGETS["analytics"])
        logger.info("[MODE] Đã chọn dọn dẹp Analytics & Sessions")

    if tables_to_clear:
        logger.warning("Bắt đầu xóa dữ liệu...")
        clear_tables(tables_to_clear, engine)
        logger.info("Hoàn thành quá trình dọn dẹp database! 🚀")

if __name__ == "__main__":
    main()
