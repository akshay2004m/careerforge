from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Application, Resume, User
from app.schemas.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
)
from app.services.skills import extract_skills

router = APIRouter()

VALID_STATUSES = {"wishlist", "applied", "interview", "offer", "rejected"}


def _to_response(app: Application) -> ApplicationResponse:
    return ApplicationResponse(
        id=app.id,
        company=app.company or "",
        role=app.role or "",
        status=app.status or "applied",
        job_description=app.job_description,
        notes=app.notes,
        resume_id=app.resume_id,
        tailored_resume_id=app.tailored_resume_id,
        ats_score=app.ats_score,
        skills=app.skills if isinstance(app.skills, list) else None,
        created_at=app.created_at.isoformat() if app.created_at else None,
        updated_at=app.updated_at.isoformat() if app.updated_at else None,
    )


@router.get("", response_model=list[ApplicationResponse])
def list_applications(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Application).filter(Application.user_id == current_user.id)
    if status and status in VALID_STATUSES:
        q = q.filter(Application.status == status)
    rows = q.order_by(Application.updated_at.desc(), Application.created_at.desc()).all()
    return [_to_response(r) for r in rows]


@router.post("", response_model=ApplicationResponse)
def create_application(
    body: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    status = (body.status or "applied").lower()
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"Invalid status. Use one of {sorted(VALID_STATUSES)}"
        )

    if body.resume_id:
        resume = (
            db.query(Resume)
            .filter(Resume.id == body.resume_id, Resume.user_id == current_user.id)
            .first()
        )
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

    skills = body.skills
    if not skills and body.job_description and len(body.job_description) >= 20:
        skills = extract_skills(body.job_description, use_llm=False).get("skills")

    app = Application(
        user_id=current_user.id,
        company=body.company.strip(),
        role=body.role.strip(),
        status=status,
        job_description=body.job_description,
        notes=body.notes,
        resume_id=body.resume_id,
        tailored_resume_id=body.tailored_resume_id,
        ats_score=body.ats_score,
        skills=skills,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return _to_response(app)


@router.patch("/{app_id}", response_model=ApplicationResponse)
def update_application(
    app_id: int,
    body: ApplicationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = (
        db.query(Application)
        .filter(Application.id == app_id, Application.user_id == current_user.id)
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"]:
        st = data["status"].lower()
        if st not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        data["status"] = st

    for k, v in data.items():
        setattr(app, k, v)
    app.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(app)
    return _to_response(app)


@router.delete("/{app_id}")
def delete_application(
    app_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = (
        db.query(Application)
        .filter(Application.id == app_id, Application.user_id == current_user.id)
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete(app)
    db.commit()
    return {"message": "Deleted"}
