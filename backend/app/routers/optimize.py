from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Resume, TailoredResume, User, Application
from app.schemas.schemas import OptimizeRequest, OptimizeResponse, TailoredSummary
from app.services.ai_optimizer import optimize_resume
from app.services.skills import extract_skills
from app.services.vector_store import query_relevant_chunks_detailed, index_resume

router = APIRouter()
logger = logging.getLogger("careerforge.optimize")


@router.post("/optimize", response_model=OptimizeResponse)
def optimize_resume_endpoint(
    request: OptimizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        resume = (
            db.query(Resume)
            .filter(Resume.id == request.resume_id, Resume.user_id == current_user.id)
            .first()
        )
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

        if not resume.original_text or len(resume.original_text.strip()) < 20:
            raise HTTPException(
                status_code=400,
                detail="Resume text is too short or could not be parsed. Please re-upload a text-based PDF.",
            )

        # Lazy vector index
        if not resume.vector_namespace:
            try:
                ns = index_resume(current_user.id, resume.id, resume.original_text or "")
                if ns:
                    resume.vector_namespace = ns
                    db.commit()
            except Exception as ve:
                logger.warning("vector_index_failed resume_id=%s err=%s", resume.id, ve)

        try:
            vector_hit = query_relevant_chunks_detailed(
                current_user.id, resume.id, request.job_description, n_results=5
            )
            chunks = vector_hit.get("chunks") or []
            distances = vector_hit.get("distances") or []
        except Exception as ve:
            logger.warning("vector_query_failed resume_id=%s err=%s", resume.id, ve)
            chunks, distances = [], []

        result = optimize_resume(
            resume.original_text,
            request.job_description,
            relevant_chunks=chunks or None,
            semantic_distances=distances or None,
        )
        skills_data = extract_skills(request.job_description, use_llm=False)
        skills = skills_data.get("skills") or result.get("missing_keywords") or []

        tailored_content = {
            "tailored_resume": result["tailored_resume"],
            "key_improvements": result.get("key_improvements", []),
            "missing_keywords": result.get("missing_keywords", []),
            "matched_keywords": result.get("matched_keywords", []),
            "cover_letter": result.get("cover_letter", ""),
            "skills": skills,
            "ats_breakdown": result.get("ats_breakdown", {}),
            "ats_summary": result.get("ats_summary", []),
            "ats_method": result.get("ats_method", "hybrid-3layer-v2"),
            "ats_layers": result.get("ats_layers", {}),
            "layer_scores": result.get("layer_scores", {}),
            "display_scores": result.get("display_scores", {}),
            "suggestions": result.get("suggestions", []),
            "score_before": result.get("score_before"),
            "score_delta": result.get("score_delta"),
            "qualitative_summary": result.get("qualitative_summary", ""),
            "strengths": result.get("strengths", []),
            "rubric_scores": result.get("rubric_scores", {}),
        }

        tailored_resume = TailoredResume(
            resume_id=resume.id,
            job_description=request.job_description,
            tailored_content=tailored_content,
            ats_score=result["ats_score"],
        )
        db.add(tailored_resume)
        db.commit()
        db.refresh(tailored_resume)

        application_id = None
        if request.create_application:
            company = (request.company or "Target company").strip()
            role = (request.role or "Role").strip()
            app = Application(
                user_id=current_user.id,
                company=company,
                role=role,
                status="applied",
                job_description=request.job_description,
                resume_id=resume.id,
                tailored_resume_id=tailored_resume.id,
                ats_score=result["ats_score"],
                skills=skills,
                updated_at=datetime.utcnow(),
            )
            db.add(app)
            db.commit()
            db.refresh(app)
            application_id = app.id

        return OptimizeResponse(
            tailored_resume=result["tailored_resume"],
            ats_score=result["ats_score"],
            cover_letter=result.get("cover_letter", ""),
            key_improvements=result.get("key_improvements", []),
            missing_keywords=result.get("missing_keywords", []),
            matched_keywords=result.get("matched_keywords", []),
            message="Resume optimized successfully",
            tailored_resume_id=tailored_resume.id,
            skills=skills,
            application_id=application_id,
            ats_breakdown=result.get("ats_breakdown") or {},
            ats_summary=result.get("ats_summary") or [],
            ats_method=result.get("ats_method") or "hybrid-3layer-v2",
            score_before=result.get("score_before"),
            score_delta=result.get("score_delta"),
            layer_scores=result.get("layer_scores") or {},
            display_scores=result.get("display_scores") or {},
            suggestions=result.get("suggestions") or [],
            qualitative_summary=result.get("qualitative_summary") or "",
            strengths=result.get("strengths") or [],
            rubric_scores=result.get("rubric_scores") or {},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("optimize_failed user_id=%s err=%s", current_user.id, e)
        raise HTTPException(
            status_code=502,
            detail="Optimization failed due to an internal error. Please try again.",
        )


@router.get("/history", response_model=list[TailoredSummary])
def optimization_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        rows = (
            db.query(TailoredResume)
            .join(Resume, TailoredResume.resume_id == Resume.id)
            .filter(Resume.user_id == current_user.id)
            .order_by(TailoredResume.created_at.desc())
            .limit(50)
            .all()
        )
        return [
            TailoredSummary(
                id=row.id,
                resume_id=row.resume_id,
                ats_score=row.ats_score,
                job_preview=(row.job_description or "")[:160],
                created_at=row.created_at.isoformat() if row.created_at else None,
            )
            for row in rows
        ]
    except Exception as e:
        logger.exception("history_failed user_id=%s err=%s", current_user.id, e)
        raise HTTPException(status_code=500, detail="Could not load optimization history")


@router.delete("/{opt_id}")
def delete_optimization(
    opt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    opt = (
        db.query(TailoredResume)
        .join(Resume, TailoredResume.resume_id == Resume.id)
        .filter(TailoredResume.id == opt_id, Resume.user_id == current_user.id)
        .first()
    )
    if not opt:
        raise HTTPException(status_code=404, detail="Optimization not found")
    
    db.delete(opt)
    db.commit()
    return {"message": "Optimization deleted"}
