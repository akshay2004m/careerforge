"""
Relational schema for CareerForge AI.

Design notes (interview-ready):
- Normalized ownership: User → Resumes / Applications; Resume → TailoredResumes
- Explicit ForeignKeys with ON DELETE cascade / set-null
- Composite + single-column indexes for common query paths
  (list by user, filter applications by status, history by resume)
- CheckConstraint for application status enum-like values
- ORM relationships for clean navigation and cascade semantics
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    headline = Column(String(500), nullable=True)
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    resumes = relationship(
        "Resume",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    applications = relationship(
        "Application",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (
        Index("ix_resumes_user_id", "user_id"),
        Index("ix_resumes_user_primary", "user_id", "is_primary"),
        Index("ix_resumes_user_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(255), nullable=False, default="Resume")
    original_text = Column(Text, nullable=False)
    parsed_data = Column(JSON, nullable=True)
    file_path = Column(String(500), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    # Optional chroma collection document id / namespace key for hybrid search
    vector_namespace = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="resumes")
    tailored_versions = relationship(
        "TailoredResume",
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    applications = relationship("Application", back_populates="resume")


class TailoredResume(Base):
    __tablename__ = "tailored_resumes"
    __table_args__ = (
        Index("ix_tailored_resume_id", "resume_id"),
        Index("ix_tailored_created_at", "created_at"),
        Index("ix_tailored_resume_created", "resume_id", "created_at"),
        CheckConstraint(
            "ats_score IS NULL OR (ats_score >= 0 AND ats_score <= 100)",
            name="ck_tailored_ats_score_range",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    resume_id = Column(
        Integer,
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_description = Column(Text, nullable=False)
    tailored_content = Column(JSON, nullable=True)
    ats_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    resume = relationship("Resume", back_populates="tailored_versions")
    applications = relationship("Application", back_populates="tailored_resume")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_applications_user_id", "user_id"),
        Index("ix_applications_user_status", "user_id", "status"),
        Index("ix_applications_user_updated", "user_id", "updated_at"),
        Index("ix_applications_company", "company"),
        CheckConstraint(
            "status IN ('wishlist','applied','interview','offer','rejected')",
            name="ck_application_status",
        ),
        CheckConstraint(
            "ats_score IS NULL OR (ats_score >= 0 AND ats_score <= 100)",
            name="ck_application_ats_score_range",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    company = Column(String(255), nullable=False, default="")
    role = Column(String(255), nullable=False, default="")
    status = Column(String(50), nullable=False, default="applied")
    job_description = Column(Text, nullable=True)
    skills = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    resume_id = Column(
        Integer,
        ForeignKey("resumes.id", ondelete="SET NULL"),
        nullable=True,
    )
    tailored_resume_id = Column(
        Integer,
        ForeignKey("tailored_resumes.id", ondelete="SET NULL"),
        nullable=True,
    )
    ats_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="applications")
    resume = relationship("Resume", back_populates="applications")
    tailored_resume = relationship("TailoredResume", back_populates="applications")
