from sqlalchemy import Column, String
import sqlalchemy as sa
from app.schemas.base import Base

class Document(Base):
    """
    RAG Documents table with pgvector support via SQL-only search.
    Note: We use SQL text for the vector type to avoid extra library overhead if not needed globally.
    """
    __tablename__ = "documents"

    id = Column(sa.Integer, primary_key=True, autoincrement=True)
    content = Column(String, nullable=False)
    # The embedding column is added via raw SQL in migration to handle the vector type
    # but defined here as a placeholder if needed for SQLAlchemy queries
    # embedding = Column(Vector(768)) 
