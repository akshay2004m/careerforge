from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    name = Column(String(255))
    password_hash = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    original_text = Column(Text)
    parsed_data = Column(JSON)
    file_path = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)

class TailoredResume(Base):
    __tablename__ = "tailored_resumes"
    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"))
    job_description = Column(Text)
    tailored_content = Column(JSON)
    ats_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)