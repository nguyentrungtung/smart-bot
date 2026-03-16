import logging
from typing import Dict, Any, Optional
from sqlalchemy import Column, String, JSON, DateTime, select
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config.settings import settings
import datetime

logger = logging.getLogger("long_term_memory")
from app.schemas.base import Base

class UserProfile(Base):
    """
    Persistent SQLAlchemy model for Long-Term User Memory.
    Stores extracted facts, preferences, and behavior.
    """
    __tablename__ = "user_profiles"
    
    user_id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    preferences = Column(JSON, default={}) # e.g. {"tone": "technical", "products": ["CRM"]}
    facts = Column(JSON, default=[]) # e.g. ["User is a developer", "Company size is 50"]
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)

class LongTermMemory:
    """
    Service for managing retrieval and updates of UserProfiles.
    """
    
    def __init__(self, pool=None):
        self.pool = pool # psycopg_pool async pool

    async def get_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Fetches the user's long-term profile from PostgreSQL.
        """
        if not self.pool:
            return {}

        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    query = "SELECT name, preferences, facts FROM user_profiles WHERE user_id = %s"
                    await cur.execute(query, (user_id,))
                    row = await cur.fetchone()
                    
                    if row:
                        return {
                            "name": row[0],
                            "preferences": row[1],
                            "facts": row[2]
                        }
        except Exception as e:
            logger.error(f"LTM: Failed to fetch profile for {user_id}: {str(e)}")
        
        return {}

    async def update_profile(self, user_id: str, updates: Dict[str, Any]):
        """
        Saves new facts or preferences to the user's long-term profile.
        """
        if not self.pool:
            return

        try:
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        # UPSERT logic
                        query = """
                        INSERT INTO user_profiles (user_id, name, preferences, facts, last_updated)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            preferences = EXCLUDED.preferences,
                            facts = EXCLUDED.facts,
                            last_updated = EXCLUDED.last_updated
                        """
                        from psycopg.types.json import Json
                        await cur.execute(query, (
                            user_id, 
                            updates.get("name"),
                            Json(updates.get("preferences", {})),
                            Json(updates.get("facts", [])),
                            datetime.datetime.utcnow()
                        ))
        except Exception as e:
            logger.error(f"LTM: Failed to update profile for {user_id}: {str(e)}")
