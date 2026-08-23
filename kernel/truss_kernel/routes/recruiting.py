"""Recruiting routes (Phase AJ): jobs, candidates, applications, pipeline."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.recruiting import Application, Candidate, Job

router = APIRouter(prefix="/api/recruiting", tags=["recruiting"])

VALID_JOB_STATUS = {"open", "closed", "filled"}
VALID_EMPLOYMENT_TYPES = {"full_time", "part_time", "contract", "intern"}
VALID_SOURCES = {"referral", "job_board", "website", "agency", "other"}
VALID_STAGES = {"applied", "screening", "interview", "offer", "hired", "rejected"}
# allowed forward pipeline transitions
STAGE_TRANSITIONS = {
    "applied": {"screening", "rejected"},
    "screening": {"interview", "rejected"},
    "interview": {"offer", "rejected"},
    "offer": {"hired", "rejected"},
}
TERMINAL_STAGES = {"hired", "rejected"}


class JobIn(BaseModel):
    title: str
    department: str = ""
    location: str = ""
    employment_type: str = "full_time"
    description: str = ""


class JobPatch(BaseModel):
    title: str | None = None
    department: str | None = None
    location: str | None = None
    employment_type: str | None = None
    description: str | None = None
    status: str | None = None


class CandidateIn(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    source: str = "other"
    skills: str = ""


class CandidatePatch(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    skills: str | None = None


class ApplicationIn(BaseModel):
    job_id: str
    candidate_id: str
    notes: str = ""


class StageIn(BaseModel):
    stage: str
    notes: str | None = None


def _serialize_job(j: Job) -> dict:
    return {
        "id": str(j.id),
        "title": j.title,
        "department": j.department,
        "location": j.location,
        "employment_type": j.employment_type,
        "description": j.description,
        "status": j.status,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }


def _serialize_candidate(c: Candidate) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "source": c.source,
        "skills": c.skills,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _serialize_application(a: Application) -> dict:
    return {
        "id": str(a.id),
        "job_id": str(a.job_id),
        "candidate_id": str(a.candidate_id),
        "stage": a.stage,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


async def _get_job(db: AsyncSession, tenant_id, jid: uuid.UUID) -> Job:
    j = (await db.execute(select(Job).where(
        Job.tenant_id == tenant_id, Job.id == jid))).scalar_one_or_none()
    if not j:
        raise HTTPException(404, "Job not found")
    return j


async def _get_candidate(db: AsyncSession, tenant_id, cid: uuid.UUID) -> Candidate:
    c = (await db.execute(select(Candidate).where(
        Candidate.tenant_id == tenant_id, Candidate.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")
    return c


async def _get_application(db: AsyncSession, tenant_id, aid: uuid.UUID) -> Application:
    a = (await db.execute(select(Application).where(
        Application.tenant_id == tenant_id, Application.id == aid))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Application not found")
    return a


def _parse_uuid(raw: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError):
        raise HTTPException(400, f"{label} must be a UUID")


# ---- jobs ----

@router.post("/jobs", status_code=201)
async def create_job(body: JobIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if body.employment_type not in VALID_EMPLOYMENT_TYPES:
        raise HTTPException(400, f"Invalid employment_type. Valid: {', '.join(sorted(VALID_EMPLOYMENT_TYPES))}")
    j = Job(
        tenant_id=auth.tenant_id, title=body.title, department=body.department,
        location=body.location, employment_type=body.employment_type,
        description=body.description, status="open", created_by=auth.user_id,
    )
    db.add(j)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="recruiting.job_created",
                   payload={"job_id": str(j.id), "title": j.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(j)
    return _serialize_job(j)


@router.get("/jobs")
async def list_jobs(status: str | None = None, department: str | None = None,
                    auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Job).where(Job.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_JOB_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_JOB_STATUS))}")
        stmt = stmt.where(Job.status == status)
    if department:
        stmt = stmt.where(Job.department == department)
    rows = (await db.execute(stmt.order_by(Job.created_at.desc()))).scalars().all()
    return {"items": [_serialize_job(j) for j in rows], "total": len(rows)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    j = await _get_job(db, auth.tenant_id, job_id)
    return _serialize_job(j)


@router.patch("/jobs/{job_id}")
async def update_job(job_id: uuid.UUID, body: JobPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    j = await _get_job(db, auth.tenant_id, job_id)
    if body.title is not None:
        j.title = body.title
    if body.department is not None:
        j.department = body.department
    if body.location is not None:
        j.location = body.location
    if body.employment_type is not None:
        if body.employment_type not in VALID_EMPLOYMENT_TYPES:
            raise HTTPException(400, f"Invalid employment_type. Valid: {', '.join(sorted(VALID_EMPLOYMENT_TYPES))}")
        j.employment_type = body.employment_type
    if body.description is not None:
        j.description = body.description
    if body.status is not None:
        if body.status not in VALID_JOB_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_JOB_STATUS))}")
        j.status = body.status
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="recruiting.job_updated",
                   payload={"job_id": str(j.id), "title": j.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(j)
    return _serialize_job(j)


@router.delete("/jobs/{job_id}", status_code=200)
async def delete_job(job_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    j = await _get_job(db, auth.tenant_id, job_id)
    refs = (await db.execute(select(Application).where(
        Application.tenant_id == auth.tenant_id, Application.job_id == job_id))).scalars().all()
    if refs:
        raise HTTPException(409, "Job has applications; cannot delete")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="recruiting.job_deleted",
                   payload={"job_id": str(j.id), "title": j.title}, actor_id=auth.user_id)
    await db.delete(j)
    await db.commit()
    return {"deleted": True}


# ---- candidates ----

@router.post("/candidates", status_code=201)
async def create_candidate(body: CandidateIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if body.source not in VALID_SOURCES:
        raise HTTPException(400, f"Invalid source. Valid: {', '.join(sorted(VALID_SOURCES))}")
    c = Candidate(
        tenant_id=auth.tenant_id, name=body.name, email=body.email, phone=body.phone,
        source=body.source, skills=body.skills, created_by=auth.user_id,
    )
    db.add(c)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="recruiting.candidate_created",
                   payload={"candidate_id": str(c.id), "name": c.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize_candidate(c)


@router.get("/candidates")
async def list_candidates(source: str | None = None, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Candidate).where(Candidate.tenant_id == auth.tenant_id)
    if source:
        if source not in VALID_SOURCES:
            raise HTTPException(400, f"Invalid source. Valid: {', '.join(sorted(VALID_SOURCES))}")
        stmt = stmt.where(Candidate.source == source)
    rows = (await db.execute(stmt.order_by(Candidate.created_at.desc()))).scalars().all()
    return {"items": [_serialize_candidate(c) for c in rows], "total": len(rows)}


@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    c = await _get_candidate(db, auth.tenant_id, candidate_id)
    return _serialize_candidate(c)


@router.patch("/candidates/{candidate_id}")
async def update_candidate(candidate_id: uuid.UUID, body: CandidatePatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_candidate(db, auth.tenant_id, candidate_id)
    if body.name is not None:
        c.name = body.name
    if body.email is not None:
        c.email = body.email
    if body.phone is not None:
        c.phone = body.phone
    if body.source is not None:
        if body.source not in VALID_SOURCES:
            raise HTTPException(400, f"Invalid source. Valid: {', '.join(sorted(VALID_SOURCES))}")
        c.source = body.source
    if body.skills is not None:
        c.skills = body.skills
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="recruiting.candidate_updated",
                   payload={"candidate_id": str(c.id), "name": c.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize_candidate(c)


@router.delete("/candidates/{candidate_id}", status_code=200)
async def delete_candidate(candidate_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    c = await _get_candidate(db, auth.tenant_id, candidate_id)
    refs = (await db.execute(select(Application).where(
        Application.tenant_id == auth.tenant_id, Application.candidate_id == candidate_id))).scalars().all()
    if refs:
        raise HTTPException(409, "Candidate has applications; cannot delete")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="recruiting.candidate_deleted",
                   payload={"candidate_id": str(c.id), "name": c.name}, actor_id=auth.user_id)
    await db.delete(c)
    await db.commit()
    return {"deleted": True}


# ---- applications ----

@router.post("/applications", status_code=201)
async def create_application(body: ApplicationIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    jid = _parse_uuid(body.job_id, "job_id")
    cid = _parse_uuid(body.candidate_id, "candidate_id")
    j = await _get_job(db, auth.tenant_id, jid)
    await _get_candidate(db, auth.tenant_id, cid)
    if j.status != "open":
        raise HTTPException(409, f"Job is {j.status}; only open jobs accept applications")
    # prevent duplicate application of same candidate to same job
    dup = (await db.execute(select(Application).where(
        Application.tenant_id == auth.tenant_id, Application.job_id == jid,
        Application.candidate_id == cid))).scalar_one_or_none()
    if dup:
        raise HTTPException(409, "Candidate already applied to this job")
    a = Application(
        tenant_id=auth.tenant_id, job_id=jid, candidate_id=cid,
        stage="applied", notes=body.notes,
    )
    db.add(a)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="recruiting.application_created",
                   payload={"application_id": str(a.id), "job_id": str(jid), "candidate_id": str(cid)},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize_application(a)


@router.get("/applications")
async def list_applications(stage: str | None = None, job_id: str | None = None,
                            candidate_id: str | None = None,
                            auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Application).where(Application.tenant_id == auth.tenant_id)
    if stage:
        if stage not in VALID_STAGES:
            raise HTTPException(400, f"Invalid stage. Valid: {', '.join(sorted(VALID_STAGES))}")
        stmt = stmt.where(Application.stage == stage)
    if job_id:
        stmt = stmt.where(Application.job_id == _parse_uuid(job_id, "job_id"))
    if candidate_id:
        stmt = stmt.where(Application.candidate_id == _parse_uuid(candidate_id, "candidate_id"))
    rows = (await db.execute(stmt.order_by(Application.created_at.desc()))).scalars().all()
    return {"items": [_serialize_application(a) for a in rows], "total": len(rows)}


@router.get("/applications/{application_id}")
async def get_application(application_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    a = await _get_application(db, auth.tenant_id, application_id)
    return _serialize_application(a)


@router.post("/applications/{application_id}/stage")
async def move_stage(application_id: uuid.UUID, body: StageIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    a = await _get_application(db, auth.tenant_id, application_id)
    if body.stage not in VALID_STAGES:
        raise HTTPException(400, f"Invalid stage. Valid: {', '.join(sorted(VALID_STAGES))}")
    if a.stage in TERMINAL_STAGES:
        raise HTTPException(409, f"Application is {a.stage}; terminal stages cannot move")
    allowed = STAGE_TRANSITIONS.get(a.stage, set())
    if body.stage not in allowed:
        raise HTTPException(409, f"Cannot move from {a.stage} to {body.stage}. Allowed: {', '.join(sorted(allowed))}")
    a.stage = body.stage
    if body.notes is not None:
        a.notes = body.notes
    # if hired, mark the job filled
    if body.stage == "hired":
        j = await _get_job(db, auth.tenant_id, a.job_id)
        j.status = "filled"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="recruiting.stage_changed",
                   payload={"application_id": str(a.id), "stage": a.stage}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize_application(a)


@router.delete("/applications/{application_id}", status_code=200)
async def delete_application(application_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = await _get_application(db, auth.tenant_id, application_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="recruiting.application_deleted",
                   payload={"application_id": str(a.id)}, actor_id=auth.user_id)
    await db.delete(a)
    await db.commit()
    return {"deleted": True}
