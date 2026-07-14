from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Resume, TailoredResume, User
from app.schemas.schemas import OptimizeRequest, OptimizeResponse
from app.services.ai_optimizer import optimize_resume
from app.core.security import get_current_user

router = APIRouter()

@router.post("/optimize", response_model=OptimizeResponse)
def optimize(
    request: OptimizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resume = db.query(Resume).filter(
        Resume.id == request.resume_id, 
        Resume.user_id == current_user.id
    ).first()
    
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    result = optimize_resume(resume.original_text, request.job_description)
    
    tailored = TailoredResume(
        resume_id=resume.id,
        job_description=request.job_description,
        tailored_content=result,
        ats_score=result.get("ats_score", 75.0)
    )
    db.add(tailored)
    db.commit()
    
    return {
        "tailored_resume": result.get("tailored_resume"),
        "ats_score": result.get("ats_score", 75.0),
        "cover_letter": result.get("cover_letter", ""),
        "message": "Optimization successful"
    }