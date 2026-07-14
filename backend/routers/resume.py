from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
import os
from app.core.database import get_db
from app.models.models import Resume, User
from app.schemas.schemas import ResumeUploadResponse
from app.services.parser import parse_resume
from app.core.security import get_current_user  # We'll add this below

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    file_path = f"{UPLOAD_DIR}/{current_user.id}_{file.filename}"
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    text, parsed_data = parse_resume(file_path)
    
    new_resume = Resume(
        user_id=current_user.id,
        original_text=text,
        parsed_data=parsed_data,
        file_path=file_path
    )
    db.add(new_resume)
    db.commit()
    db.refresh(new_resume)
    
    return {"resume_id": new_resume.id, "message": "Resume uploaded successfully"}