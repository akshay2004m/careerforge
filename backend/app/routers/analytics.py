from collections import Counter
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User, Application, Resume, TailoredResume
from app.schemas.schemas import AnalyticsResponse

router = APIRouter()


@router.get("/summary", response_model=AnalyticsResponse)
def analytics_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    apps = (
        db.query(Application)
        .filter(Application.user_id == current_user.id)
        .order_by(Application.updated_at.desc())
        .all()
    )
    resumes = db.query(Resume).filter(Resume.user_id == current_user.id).count()
    opts = (
        db.query(TailoredResume)
        .join(Resume, TailoredResume.resume_id == Resume.id)
        .filter(Resume.user_id == current_user.id)
        .all()
    )

    by_status: dict[str, int] = {
        "wishlist": 0,
        "applied": 0,
        "interview": 0,
        "offer": 0,
        "rejected": 0,
    }
    for a in apps:
        st = (a.status or "applied").lower()
        by_status[st] = by_status.get(st, 0) + 1

    scores = [o.ats_score for o in opts if o.ats_score is not None]
    avg = sum(scores) / len(scores) if scores else 0.0
    best = max(scores) if scores else 0.0

    decided = by_status.get("offer", 0) + by_status.get("rejected", 0) + by_status.get("interview", 0)
    success_rate = (
        (by_status.get("offer", 0) / decided) * 100 if decided else 0.0
    )

    company_counts = Counter((a.company or "Unknown").strip() or "Unknown" for a in apps)
    top_companies = [
        {"company": name, "count": count}
        for name, count in company_counts.most_common(5)
    ]

    recent = []
    for a in apps[:8]:
        recent.append(
            {
                "type": "application",
                "id": a.id,
                "title": f"{a.role} @ {a.company}",
                "status": a.status,
                "at": a.updated_at.isoformat() if a.updated_at else None,
            }
        )
    for o in sorted(opts, key=lambda x: x.created_at or x.id, reverse=True)[:5]:
        recent.append(
            {
                "type": "optimization",
                "id": o.id,
                "title": (o.job_description or "")[:80],
                "status": f"ATS {int(o.ats_score or 0)}%",
                "at": o.created_at.isoformat() if o.created_at else None,
            }
        )
    recent.sort(key=lambda x: x.get("at") or "", reverse=True)

    return AnalyticsResponse(
        total_applications=len(apps),
        by_status=by_status,
        total_resumes=resumes,
        total_optimizations=len(opts),
        average_ats=round(avg, 1),
        best_ats=round(best, 1),
        success_rate=round(success_rate, 1),
        top_companies=top_companies,
        recent_activity=recent[:10],
    )
