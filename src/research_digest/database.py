"""Database connection and session management."""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from research_digest.config import Config
from research_digest.models import Base


class Database:
    def __init__(self, config: Config):
        self.config = config
        db_path = Path(config.app.db_path)
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)
        
    def get_session(self) -> Session:
        """Get a database session."""
        return self.SessionLocal()
            
    @contextmanager
    def get_session_context(self) -> Generator[Session, None, None]:
        """Get a database session with context management."""
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()
            
    def get_active_topics(self, session: Session):
        """Get all active topics."""
        from research_digest.models import Topic
        return session.query(Topic).filter(Topic.active == True).all()
        
    def add_topic(self, session: Session, name: str, description: str, raw_query: str):
        """Add a new topic."""
        from research_digest.models import Topic
        topic = Topic(name=name, description=description, raw_query=raw_query)
        session.add(topic)
        session.commit()
        return topic