"""Surveys & feedback model (Phase AH): survey builder, questions, responses.

Survey is a titled questionnaire with a lifecycle draft -> published ->
closed. Each survey carries ordered questions (text / rating / choice).
SurveyResponse captures one submission: an optional respondent label and
a JSON map of question_id -> answer. Analytics (response count, average
rating) are computed at read time.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Survey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "surveys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # draft | published | closed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class SurveyQuestion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "survey_questions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    survey_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    # text | rating | choice
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    # for choice questions: list of option labels
    options: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # 1-based display order
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    required: Mapped[bool] = mapped_column(default=False)


class SurveyResponse(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "survey_responses"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    survey_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # optional respondent label (name / email / anonymous)
    respondent: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # map of question_id (str) -> answer (str or number)
    answers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
