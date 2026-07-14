"""HTTP layer for skill extraction — business logic lives in app.services.skills."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.models.models import User
from app.schemas.schemas import SkillExtractRequest, SkillExtractResponse
from app.services.skills import extract_skills

router = APIRouter()


@router.post("/extract", response_model=SkillExtractResponse)
def extract_job_skills(
    body: SkillExtractRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        # Fast rules first; LLM only if few hits
        rules = extract_skills(body.job_description, use_llm=False)
        if len(rules.get("skills") or []) >= 6:
            return SkillExtractResponse(**rules)
        return SkillExtractResponse(**extract_skills(body.job_description, use_llm=True))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Skill extraction failed: {str(e)[:120]}")
