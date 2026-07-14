"""initial schema — users, resumes, tailored_resumes, applications

Revision ID: 001_initial
Revises:
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("headline", sa.String(length=500), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_created_at", "users", ["created_at"], unique=False)

    op.create_table(
        "resumes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("parsed_data", sa.JSON(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("vector_namespace", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resumes_user_id", "resumes", ["user_id"], unique=False)
    op.create_index("ix_resumes_user_primary", "resumes", ["user_id", "is_primary"], unique=False)
    op.create_index("ix_resumes_user_created", "resumes", ["user_id", "created_at"], unique=False)

    op.create_table(
        "tailored_resumes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("resume_id", sa.Integer(), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False),
        sa.Column("tailored_content", sa.JSON(), nullable=True),
        sa.Column("ats_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "ats_score IS NULL OR (ats_score >= 0 AND ats_score <= 100)",
            name="ck_tailored_ats_score_range",
        ),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tailored_resume_id", "tailored_resumes", ["resume_id"], unique=False)
    op.create_index("ix_tailored_created_at", "tailored_resumes", ["created_at"], unique=False)
    op.create_index(
        "ix_tailored_resume_created", "tailored_resumes", ["resume_id", "created_at"], unique=False
    )

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("resume_id", sa.Integer(), nullable=True),
        sa.Column("tailored_resume_id", sa.Integer(), nullable=True),
        sa.Column("ats_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('wishlist','applied','interview','offer','rejected')",
            name="ck_application_status",
        ),
        sa.CheckConstraint(
            "ats_score IS NULL OR (ats_score >= 0 AND ats_score <= 100)",
            name="ck_application_ats_score_range",
        ),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tailored_resume_id"], ["tailored_resumes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"], unique=False)
    op.create_index(
        "ix_applications_user_status", "applications", ["user_id", "status"], unique=False
    )
    op.create_index(
        "ix_applications_user_updated", "applications", ["user_id", "updated_at"], unique=False
    )
    op.create_index("ix_applications_company", "applications", ["company"], unique=False)


def downgrade() -> None:
    op.drop_table("applications")
    op.drop_table("tailored_resumes")
    op.drop_table("resumes")
    op.drop_table("users")
