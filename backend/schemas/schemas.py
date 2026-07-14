from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Dict, Any

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ResumeUploadResponse(BaseModel):
    resume_id: int
    message: str

class OptimizeRequest(BaseModel):
    resume_id: int
    job_description: str

class OptimizeResponse(BaseModel):
    tailored_resume: Dict[str, Any]
    ats_score: float
    cover_letter: str
    message: str