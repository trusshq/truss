"""Surveys routes (Phase AH): CRUD, questions, lifecycle, responses, analytics."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.surveys import Survey, SurveyQuestion, SurveyResponse

router = APIRouter(prefix="/api/surveys", tags=["surveys"])

VALID_STATUS = {"draft", "published", "closed"}
VALID_KINDS = {"text", "rating", "choice"}


class SurveyIn(BaseModel):
    title: str
    description: str = ""


class SurveyPatch(BaseModel):
    title: str | None = None
    description: str | None = None


class QuestionIn(BaseModel):
    text: str
    kind: str = "text"
    options: list[str] = Field(default_factory=list)
    position: int = Field(default=1, ge=1)
    required: bool = False


class QuestionPatch(BaseModel):
    text: str | None = None
    kind: str | None = None
    options: list[str] | None = None
    position: int | None = Field(default=None, ge=1)
    required: bool | None = None


class ResponseIn(BaseModel):
    respondent: str = ""
    answers: dict = Field(default_factory=dict)


def _serialize_survey(s: Survey, questions: list[SurveyQuestion], response_count: int = 0) -> dict:
    return {
        "id": str(s.id),
        "title": s.title,
        "description": s.description,
        "status": s.status,
        "response_count": response_count,
        "questions": [_serialize_question(q) for q in questions],
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _serialize_question(q: SurveyQuestion) -> dict:
    return {
        "id": str(q.id),
        "survey_id": str(q.survey_id),
        "text": q.text,
        "kind": q.kind,
        "options": q.options or [],
        "position": q.position,
        "required": q.required,
    }


def _serialize_response(r: SurveyResponse) -> dict:
    return {
        "id": str(r.id),
        "survey_id": str(r.survey_id),
        "respondent": r.respondent,
        "answers": r.answers or {},
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _get_survey(db: AsyncSession, tenant_id, sid: uuid.UUID) -> Survey:
    s = (await db.execute(select(Survey).where(
        Survey.tenant_id == tenant_id, Survey.id == sid))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Survey not found")
    return s


async def _get_questions(db: AsyncSession, tenant_id, sid: uuid.UUID) -> list[SurveyQuestion]:
    return list((await db.execute(select(SurveyQuestion).where(
        SurveyQuestion.tenant_id == tenant_id, SurveyQuestion.survey_id == sid,
    ).order_by(SurveyQuestion.position.asc(), SurveyQuestion.created_at.asc()))).scalars().all())


async def _get_question(db: AsyncSession, tenant_id, qid: uuid.UUID) -> SurveyQuestion:
    q = (await db.execute(select(SurveyQuestion).where(
        SurveyQuestion.tenant_id == tenant_id, SurveyQuestion.id == qid))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Question not found")
    return q


async def _response_count(db: AsyncSession, tenant_id, sid: uuid.UUID) -> int:
    rows = (await db.execute(select(SurveyResponse).where(
        SurveyResponse.tenant_id == tenant_id, SurveyResponse.survey_id == sid))).scalars().all()
    return len(rows)


@router.post("", status_code=201)
async def create_survey(body: SurveyIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = Survey(
        tenant_id=auth.tenant_id, title=body.title, description=body.description,
        status="draft", created_by=auth.user_id,
    )
    db.add(s)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="survey.created",
                   payload={"survey_id": str(s.id), "title": s.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    return _serialize_survey(s, [])


@router.get("")
async def list_surveys(status: str | None = None, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Survey).where(Survey.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_STATUS))}")
        stmt = stmt.where(Survey.status == status)
    rows = (await db.execute(stmt.order_by(Survey.created_at.desc()))).scalars().all()
    items = []
    for s in rows:
        qs = await _get_questions(db, auth.tenant_id, s.id)
        cnt = await _response_count(db, auth.tenant_id, s.id)
        items.append(_serialize_survey(s, qs, cnt))
    return {"items": items, "total": len(items)}


@router.get("/{survey_id}")
async def get_survey(survey_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    s = await _get_survey(db, auth.tenant_id, survey_id)
    qs = await _get_questions(db, auth.tenant_id, survey_id)
    cnt = await _response_count(db, auth.tenant_id, survey_id)
    return _serialize_survey(s, qs, cnt)


@router.patch("/{survey_id}")
async def update_survey(survey_id: uuid.UUID, body: SurveyPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = await _get_survey(db, auth.tenant_id, survey_id)
    if s.status != "draft":
        raise HTTPException(409, f"Survey is {s.status}; only draft surveys can be edited")
    if body.title is not None:
        s.title = body.title
    if body.description is not None:
        s.description = body.description
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="survey.updated",
                   payload={"survey_id": str(s.id), "title": s.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    qs = await _get_questions(db, auth.tenant_id, survey_id)
    return _serialize_survey(s, qs)


@router.delete("/{survey_id}", status_code=200)
async def delete_survey(survey_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    s = await _get_survey(db, auth.tenant_id, survey_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="survey.deleted",
                   payload={"survey_id": str(s.id), "title": s.title}, actor_id=auth.user_id)
    await db.delete(s)
    await db.commit()
    return {"deleted": True}


# ---- questions ----

@router.post("/{survey_id}/questions", status_code=201)
async def create_question(survey_id: uuid.UUID, body: QuestionIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = await _get_survey(db, auth.tenant_id, survey_id)
    if s.status != "draft":
        raise HTTPException(409, f"Survey is {s.status}; only draft surveys can take questions")
    if body.kind not in VALID_KINDS:
        raise HTTPException(400, f"Invalid kind. Valid: {', '.join(sorted(VALID_KINDS))}")
    if body.kind == "choice" and len(body.options) < 2:
        raise HTTPException(400, "Choice questions need at least 2 options")
    q = SurveyQuestion(
        tenant_id=auth.tenant_id, survey_id=survey_id, text=body.text, kind=body.kind,
        options=body.options, position=body.position, required=body.required,
    )
    db.add(q)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="survey.question_created",
                   payload={"survey_id": str(survey_id), "question_id": str(q.id), "text": q.text},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(q)
    return _serialize_question(q)


@router.get("/{survey_id}/questions")
async def list_questions(survey_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_survey(db, auth.tenant_id, survey_id)
    qs = await _get_questions(db, auth.tenant_id, survey_id)
    return {"items": [_serialize_question(q) for q in qs], "total": len(qs)}


@router.patch("/questions/{question_id}")
async def update_question(question_id: uuid.UUID, body: QuestionPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    q = await _get_question(db, auth.tenant_id, question_id)
    s = await _get_survey(db, auth.tenant_id, q.survey_id)
    if s.status != "draft":
        raise HTTPException(409, f"Survey is {s.status}; its questions are locked")
    if body.text is not None:
        q.text = body.text
    if body.kind is not None:
        if body.kind not in VALID_KINDS:
            raise HTTPException(400, f"Invalid kind. Valid: {', '.join(sorted(VALID_KINDS))}")
        q.kind = body.kind
    if body.options is not None:
        q.options = body.options
    if body.position is not None:
        q.position = body.position
    if body.required is not None:
        q.required = body.required
    if q.kind == "choice" and len(q.options or []) < 2:
        raise HTTPException(400, "Choice questions need at least 2 options")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="survey.question_updated",
                   payload={"survey_id": str(q.survey_id), "question_id": str(q.id), "text": q.text},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(q)
    return _serialize_question(q)


@router.delete("/questions/{question_id}", status_code=200)
async def delete_question(question_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    q = await _get_question(db, auth.tenant_id, question_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="survey.question_deleted",
                   payload={"survey_id": str(q.survey_id), "question_id": str(q.id), "text": q.text},
                   actor_id=auth.user_id)
    await db.delete(q)
    await db.commit()
    return {"deleted": True}


# ---- lifecycle ----

@router.post("/{survey_id}/publish")
async def publish_survey(survey_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = await _get_survey(db, auth.tenant_id, survey_id)
    if s.status != "draft":
        raise HTTPException(409, f"Survey is {s.status}; only draft surveys can be published")
    qs = await _get_questions(db, auth.tenant_id, survey_id)
    if not qs:
        raise HTTPException(400, "Add at least one question before publishing")
    s.status = "published"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="survey.published",
                   payload={"survey_id": str(s.id), "title": s.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    return _serialize_survey(s, qs)


@router.post("/{survey_id}/close")
async def close_survey(survey_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = await _get_survey(db, auth.tenant_id, survey_id)
    if s.status != "published":
        raise HTTPException(409, f"Survey is {s.status}; only published surveys can be closed")
    s.status = "closed"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="survey.closed",
                   payload={"survey_id": str(s.id), "title": s.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    qs = await _get_questions(db, auth.tenant_id, survey_id)
    return _serialize_survey(s, qs)


# ---- responses ----

@router.post("/{survey_id}/responses", status_code=201)
async def submit_response(survey_id: uuid.UUID, body: ResponseIn, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    s = await _get_survey(db, auth.tenant_id, survey_id)
    if s.status != "published":
        raise HTTPException(409, f"Survey is {s.status}; only published surveys accept responses")
    qs = await _get_questions(db, auth.tenant_id, survey_id)
    qids = {str(q.id) for q in qs}
    # validate required questions answered
    for q in qs:
        if q.required and str(q.id) not in body.answers:
            raise HTTPException(400, f"Question '{q.text}' is required")
    # reject answers for unknown questions
    for key in body.answers:
        if key not in qids:
            raise HTTPException(400, f"Unknown question id: {key}")
    r = SurveyResponse(
        tenant_id=auth.tenant_id, survey_id=survey_id,
        respondent=body.respondent, answers=body.answers,
    )
    db.add(r)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="survey.response_submitted",
                   payload={"survey_id": str(survey_id), "response_id": str(r.id)}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(r)
    return _serialize_response(r)


@router.get("/{survey_id}/responses")
async def list_responses(survey_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_survey(db, auth.tenant_id, survey_id)
    rows = (await db.execute(select(SurveyResponse).where(
        SurveyResponse.tenant_id == auth.tenant_id, SurveyResponse.survey_id == survey_id,
    ).order_by(SurveyResponse.created_at.desc()))).scalars().all()
    return {"items": [_serialize_response(r) for r in rows], "total": len(rows)}


# ---- analytics ----

@router.get("/{survey_id}/analytics")
async def survey_analytics(survey_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_survey(db, auth.tenant_id, survey_id)
    qs = await _get_questions(db, auth.tenant_id, survey_id)
    rows = (await db.execute(select(SurveyResponse).where(
        SurveyResponse.tenant_id == auth.tenant_id, SurveyResponse.survey_id == survey_id,
    ))).scalars().all()
    total = len(rows)
    per_question = []
    for q in qs:
        qid = str(q.id)
        answers = [r.answers.get(qid) for r in rows if r.answers and qid in r.answers]
        entry = {
            "question_id": qid,
            "text": q.text,
            "kind": q.kind,
            "answered": len(answers),
        }
        if q.kind == "rating":
            nums = [float(a) for a in answers if isinstance(a, (int, float))]
            entry["average"] = round(sum(nums) / len(nums), 2) if nums else None
        elif q.kind == "choice":
            counts: dict[str, int] = {}
            for a in answers:
                key = str(a)
                counts[key] = counts.get(key, 0) + 1
            entry["choice_counts"] = counts
        per_question.append(entry)
    return {"survey_id": str(survey_id), "total_responses": total, "questions": per_question}
