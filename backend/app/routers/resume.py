from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
import os
import re
from app.core.database import get_db
from app.core.config import settings
from app.models.models import Resume, User
from app.schemas.schemas import ResumeUploadResponse, ResumeSummary, ResumeUpdate
from app.services.parser import parse_resume
from app.core.security import get_current_user
from app.services.vector_store import index_resume, delete_resume_vectors

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _safe_filename(name: str) -> str:
    base = os.path.basename(name).replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9._-]", "", base)[:120] or "resume.pdf"


def _summary(r: Resume) -> ResumeSummary:
    # Never expose server filesystem paths to the client
    return ResumeSummary(
        id=r.id,
        title=r.title or "Resume",
        is_primary=bool(r.is_primary),
        created_at=r.created_at.isoformat() if r.created_at else None,
        preview=(r.original_text or "")[:200],
        file_path=None,
    )


@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    set_primary: bool = Form(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Per-user upload isolation
    user_dir = os.path.join(UPLOAD_DIR, str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)
    safe_name = _safe_filename(file.filename)
    file_path = os.path.join(user_dir, safe_name)

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400, detail=f"File too large (max {settings.MAX_UPLOAD_MB}MB)"
        )
    # PDF magic bytes
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Invalid PDF file")

    with open(file_path, "wb") as f:
        f.write(content)

    text, parsed_data = parse_resume(file_path)
    if not text or len(text.strip()) < 20:
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from PDF. Please upload a text-based (not scanned) resume.",
        )

    resume_title = (title or safe_name.replace(".pdf", "").replace("_", " ")).strip() or "Resume"
    existing_count = db.query(Resume).filter(Resume.user_id == current_user.id).count()
    make_primary = set_primary or existing_count == 0

    if make_primary:
        db.query(Resume).filter(Resume.user_id == current_user.id).update({"is_primary": False})

    new_resume = Resume(
        user_id=current_user.id,
        title=resume_title,
        original_text=text,
        parsed_data=parsed_data,
        file_path=file_path,
        is_primary=make_primary,
    )
    db.add(new_resume)
    db.commit()
    db.refresh(new_resume)

    # Hybrid store: index chunks in Chroma (SQL still owns the record)
    ns = index_resume(current_user.id, new_resume.id, text)
    if ns:
        new_resume.vector_namespace = ns
        db.commit()

    return {
        "resume_id": new_resume.id,
        "message": "Resume uploaded and parsed successfully",
        "preview": text[:300],
        "title": new_resume.title,
        "is_primary": bool(new_resume.is_primary),
    }


@router.get("/list", response_model=list[ResumeSummary])
def list_resumes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resumes = (
        db.query(Resume)
        .filter(Resume.user_id == current_user.id)
        .order_by(Resume.is_primary.desc(), Resume.created_at.desc())
        .all()
    )
    return [_summary(r) for r in resumes]


@router.patch("/{resume_id}", response_model=ResumeSummary)
def update_resume(
    resume_id: int,
    body: ResumeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.user_id == current_user.id)
        .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    if body.title is not None:
        resume.title = body.title.strip()
    if body.is_primary is True:
        db.query(Resume).filter(Resume.user_id == current_user.id).update({"is_primary": False})
        resume.is_primary = True
    elif body.is_primary is False:
        resume.is_primary = False

    db.commit()
    db.refresh(resume)
    return _summary(resume)


@router.delete("/{resume_id}")
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = (
        db.query(Resume)
        .filter(Resume.id == resume_id, Resume.user_id == current_user.id)
        .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    delete_resume_vectors(resume.id)
    # Best-effort file cleanup (path never exposed to clients)
    if resume.file_path and os.path.isfile(resume.file_path):
        try:
            os.remove(resume.file_path)
        except OSError:
            pass

    # Manually cascade delete to avoid SQLite foreign key constraint failures
    from app.models.models import TailoredResume, Application
    db.query(TailoredResume).filter(TailoredResume.resume_id == resume.id).delete()
    db.query(Application).filter(Application.resume_id == resume.id).update({"resume_id": None})

    db.delete(resume)
    db.commit()
    return {"message": "Resume deleted"}
