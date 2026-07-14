from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any, List, Union


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    headline: Optional[str] = None
    location: Optional[str] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    headline: Optional[str] = Field(default=None, max_length=500)
    location: Optional[str] = Field(default=None, max_length=255)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ResumeUploadResponse(BaseModel):
    resume_id: int
    message: str
    preview: Optional[str] = None
    title: Optional[str] = None
    is_primary: bool = False


class ResumeSummary(BaseModel):
    id: int
    title: Optional[str] = None
    is_primary: bool = False
    created_at: Optional[str] = None
    preview: Optional[str] = None
    file_path: Optional[str] = None


class ResumeUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_primary: Optional[bool] = None


class OptimizeRequest(BaseModel):
    resume_id: int
    job_description: str = Field(min_length=20)
    create_application: bool = False
    company: Optional[str] = None
    role: Optional[str] = None


class OptimizeResponse(BaseModel):
    tailored_resume: Union[str, Dict[str, Any]]
    ats_score: float
    cover_letter: str
    key_improvements: List[str] = []
    missing_keywords: List[str] = []
    matched_keywords: List[str] = []
    message: str
    tailored_resume_id: Optional[int] = None
    skills: List[str] = []
    application_id: Optional[int] = None
    # Explainable 3-layer hybrid ATS
    ats_breakdown: Dict[str, Any] = {}
    ats_summary: List[str] = []
    ats_method: str = "hybrid-3layer-v2"
    score_before: Optional[float] = None
    score_delta: Optional[float] = None
    layer_scores: Dict[str, Any] = {}
    # Interview-friendly cards: overall + keyword/structure/relevance %
    display_scores: Dict[str, Any] = {}
    suggestions: List[str] = []
    qualitative_summary: str = ""
    strengths: List[str] = []
    rubric_scores: Dict[str, Any] = {}


class TailoredSummary(BaseModel):
    id: int
    resume_id: int
    ats_score: Optional[float] = None
    job_preview: Optional[str] = None
    created_at: Optional[str] = None


class InterviewQuestionsRequest(BaseModel):
    job_description: str = Field(min_length=20)
    count: int = Field(default=5, ge=1, le=15)
    include_common: bool = True


class InterviewFeedbackRequest(BaseModel):
    job_description: str = Field(min_length=10)
    transcript: str = Field(min_length=5)


class InterviewFeedbackResponse(BaseModel):
    feedback: str
    score: float = 7
    strengths: List[str] = []
    improvements: List[str] = []


class SkillExtractRequest(BaseModel):
    job_description: str = Field(min_length=20)


class SkillExtractResponse(BaseModel):
    skills: List[str]
    must_have: List[str] = []
    nice_to_have: List[str] = []


class ApplicationCreate(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)
    status: str = Field(default="applied")
    job_description: Optional[str] = None
    notes: Optional[str] = None
    resume_id: Optional[int] = None
    tailored_resume_id: Optional[int] = None
    ats_score: Optional[float] = None
    skills: Optional[List[str]] = None


class ApplicationUpdate(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    job_description: Optional[str] = None
    notes: Optional[str] = None
    resume_id: Optional[int] = None
    ats_score: Optional[float] = None
    skills: Optional[List[str]] = None


class ApplicationResponse(BaseModel):
    id: int
    company: str
    role: str
    status: str
    job_description: Optional[str] = None
    notes: Optional[str] = None
    resume_id: Optional[int] = None
    tailored_resume_id: Optional[int] = None
    ats_score: Optional[float] = None
    skills: Optional[List[str]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AnalyticsResponse(BaseModel):
    total_applications: int
    by_status: Dict[str, int]
    total_resumes: int
    total_optimizations: int
    average_ats: float
    best_ats: float
    success_rate: float  # offer / (applied-ish total) * 100
    top_companies: List[Dict[str, Any]]
    recent_activity: List[Dict[str, Any]]
