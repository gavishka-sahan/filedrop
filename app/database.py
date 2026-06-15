import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from contextlib import contextmanager

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class File(Base):
    __tablename__ = "files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    content_type = Column(String)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

def create_tables():
    Base.metadata.create_all(engine)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
