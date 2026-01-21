"""SQLAlchemy ORM models for Research Digest."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_query: Mapped[str] = mapped_column(String, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    paper_links: Mapped[list["PaperTopicLink"]] = relationship(
        "PaperTopicLink", back_populates="topic", cascade="all, delete-orphan"
    )


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # Base ID without version
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    authors: Mapped[str] = mapped_column(String, nullable=False)  # JSON string
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_url: Mapped[str] = mapped_column(String, nullable=False, default="")
    processed_full_text: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    paper_links: Mapped[list["PaperTopicLink"]] = relationship(
        "PaperTopicLink", back_populates="paper", cascade="all, delete-orphan"
    )


class PaperTopicLink(Base):
    __tablename__ = "paper_topic_links"

    paper_id: Mapped[str] = mapped_column(String, ForeignKey("papers.id"), primary_key=True)
    topic_id: Mapped[int] = mapped_column(Integer, ForeignKey("topics.id"), primary_key=True)
    relevance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_relevant: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    digest: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    paper: Mapped[Paper] = relationship("Paper", back_populates="paper_links")
    topic: Mapped[Topic] = relationship("Topic", back_populates="paper_links")