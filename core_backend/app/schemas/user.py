from sqlalchemy import Column, String, Boolean, DateTime
from app.schemas.base import Base
import datetime

class User(Base):
    """
    Internal user table for authentication.
    """
    __tablename__ = "users"

    user_id = Column(String, primary_key=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
