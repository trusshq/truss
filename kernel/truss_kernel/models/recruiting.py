"""Recruiting / ATS model (Phase AJ): jobs, candidates, applications.

Job is an open role (title, department, location, employment type,
description, status open/closed/filled). Candidate is a person in the
talent pool (name, email, phone, source, skills). Application ties a
candidate to a job and moves through a hiring pipeline:
applied -> screening -> interview -> offer -> hired | rejected.
"""
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Job(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "recruiting_jobs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    department: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True)
    location: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # full_time | part_time | contract | intern
    employment_type: Mapped[str] = mapped_column(String(40), nullable=False, default="full_time")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # open | closed | filled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class Candidate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "recruiting_candidates"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="", index=True)
    phone: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    # where they came from: referral, job_board, website, agency, other
    source: Mapped[str] = mapped_column(String(60), nullable=False, default="other")
    # comma-separated skills
    skills: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class Application(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "recruiting_applications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recruiting_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recruiting_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # applied -> screening -> interview -> offer -> hired | rejected
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default="applied", index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
