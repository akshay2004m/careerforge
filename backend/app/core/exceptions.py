from fastapi import HTTPException, status

class CareerForgeException(Exception):
    """Base exception for all CareerForge custom errors."""
    pass

class ResumeParseError(CareerForgeException):
    """Raised when PDF parsing fails or results in empty text."""
    pass

class ATSError(CareerForgeException):
    """Raised when ATS analysis fails (e.g. LLM timeout, bad payload)."""
    pass

class STTError(CareerForgeException):
    """Raised when Speech-to-Text streaming or processing fails."""
    pass

def handle_careerforge_exception(e: CareerForgeException) -> HTTPException:
    """Helper to convert custom domain exceptions to FastAPI HTTPExceptions."""
    if isinstance(e, ResumeParseError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    elif isinstance(e, ATSError):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"ATS Analysis failed: {str(e)}")
    elif isinstance(e, STTError):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Voice processing failed: {str(e)}")
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")
