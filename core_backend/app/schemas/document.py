from sqlalchemy import Column, String
import sqlalchemy as sa
from app.schemas.base import Base
from pgvector.sqlalchemy import Vector

class Document(Base):
    """
    RAG Documents table with pgvector support.
    """
    __tablename__ = "documents"

    id = Column(sa.Integer, primary_key=True, autoincrement=True)
    content = Column(String, nullable=False)
    embedding = Column(Vector(768), nullable=True) 
