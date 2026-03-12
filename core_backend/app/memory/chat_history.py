import logging
from typing import Dict, Any, Optional
from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.orm import declarative_base
import datetime

logger = logging.getLogger("chat_history_db")
Base = declarative_base()

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

class ChatHistoryTracker:
    """
    Service for saving flat chat history events to PostgreSQL.
    """
    def __init__(self, pool=None):
        self.pool = pool
        
    async def log_interaction(self, session_id: str, role: str, content: str, user_id: str = None, socket_id: str = None) -> Optional[int]:
        """
        Logs a single chat message (user or assistant) into the database.
        Returns the inserted ID string for potential rating updates later.
        """
        if not self.pool:
            return None
            
        try:
            async with self.pool.connection() as conn:
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
        """
        Updates an existing interaction with a Good/Not Good rating.
        Expects rating in ('good', 'bad', etc.)
        """
        if not self.pool:
            return
            
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    query = "UPDATE chat_interactions SET rating = %s WHERE id = %s"
                    await cur.execute(query, (rating, interaction_id))
        except Exception as e:
            logger.error(f"Failed to rate interaction {interaction_id}: {str(e)}")
