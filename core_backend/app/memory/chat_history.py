import logging
from typing import Dict, Any, Optional
from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.orm import declarative_base
import datetime

logger = logging.getLogger("chat_history_db")
from app.schemas.base import Base

class ChatInteraction(Base):
    """
    Persistent SQLAlchemy model for Chat History / Interactions.
    Used for analytics and answer ratings (good/bad) for RAG improvement.
    """
    __tablename__ = "chat_interactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False) # Thread ID context
    user_id = Column(String, nullable=True) # Long term tracking
    socket_id = Column(String, nullable=True) # Direct sid tracing
    role = Column(String, nullable=False) # 'user' or 'assistant'
    content = Column(Text, nullable=False) # Message content
    rating = Column(String(20), nullable=True) # 'good', 'bad'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class SessionMetadata(Base):
    """
    SQLAlchemy model for linking sessions (threads) to users.
    """
    __tablename__ = "session_metadata"
    
    session_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ChatHistoryTracker:
    """
    Service for saving flat chat history events to PostgreSQL.
    """
    def __init__(self, pool=None):
        self.pool = pool
        
    async def log_interaction(self, session_id: str, role: str, content: str, user_id: str = None, socket_id: str = None) -> Optional[int]:
        if not self.pool:
            return None
            
        try:
            async with self.pool.connection() as conn:
                # Use explicit transaction for reliability
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        query = """
                        INSERT INTO chat_interactions (session_id, user_id, socket_id, role, content, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                        """
                        await cur.execute(query, (
                            session_id,
                            user_id,
                            socket_id,
                            role,
                            content,
                            datetime.datetime.utcnow()
                        ))
                        row = await cur.fetchone()
                        return row[0] if row else None
        except Exception as e:
            logger.error(f"Failed to log chat interaction for session {session_id}: {str(e)}")
            return None
            
    async def rate_interaction(self, interaction_id: int, rating: str):
        if not self.pool:
            return
            
        try:
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        query = "UPDATE chat_interactions SET rating = %s WHERE id = %s"
                        await cur.execute(query, (rating, interaction_id))
        except Exception as e:
            logger.error(f"Failed to rate interaction {interaction_id}: {str(e)}")

    async def create_session(self, session_id: str, user_id: str):
        if not self.pool:
            return
            
        try:
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        query = "INSERT INTO session_metadata (session_id, user_id) VALUES (%s, %s)"
                        await cur.execute(query, (session_id, user_id))
        except Exception as e:
            logger.error(f"Failed to create session metadata for {session_id}: {str(e)}")

    async def cleanup_history(self, days: int = 7):
        """
        Deletes chat history and LangGraph checkpoints older than X days.
        """
        if not self.pool:
            return
            
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
                    
                    # 1. Cleanup Analytics Table
                    await cur.execute("DELETE FROM chat_interactions WHERE created_at < %s", (cutoff,))
                    deleted_interactions = cur.rowcount
                    
                    # 2. Cleanup LangGraph Checkpoints (checkpoint_writes, checkpoints)
                    # Note: LangGraph tables are usually 'checkpoints' and 'checkpoint_writes'
                    # We use raw SQL to avoid dependency issues if tables don't exist yet
                    try:
                        await cur.execute("DELETE FROM checkpoints WHERE checkpoint_id IN (SELECT checkpoint_id FROM checkpoint_writes WHERE created_at < %s)", (cutoff,))
                        await cur.execute("DELETE FROM checkpoint_writes WHERE created_at < %s", (cutoff,))
                    except Exception as checkpoint_err:
                        logger.warning(f"Could not clean up LangGraph tables (maybe they use different names or don't exist): {checkpoint_err}")
                    
                    logger.info(f"Cleanup Job: Deleted {deleted_interactions} old interactions.")
                    return {"deleted_interactions": deleted_interactions}
        except Exception as e:
            logger.error(f"Cleanup Job Failed: {str(e)}")
            raise e

    async def delete_session_checkpoints(self, session_id: str):
        """
        Deletes only the LangGraph checkpoints for a specific thread_id.
        Keeps 'chat_interactions' for analytics.
        """
        if not self.pool:
            return
            
        tables_to_clear = ['checkpoint_writes', 'checkpoint_blobs', 'checkpoints']
        
        for table in tables_to_clear:
            try:
                # Use separate connections/transactions for each table
                # so if one table doesn't exist, it doesn't abort the others.
                async with self.pool.connection() as conn:
                    async with conn.transaction():
                        async with conn.cursor() as cur:
                            # Safely format table name in query (these are known safe strings)
                            query = f"DELETE FROM {table} WHERE thread_id = %s"
                            await cur.execute(query, (session_id,))
            except Exception as e:
                logger.warning(f"Could not delete {table} for {session_id}: {e}")
                
        logger.info(f"Checkpoint Cleanup: Data cleared for finished session {session_id}")


