from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, Base, ping_db, SessionLocal
from app.core.errors import register_exception_handlers
from app.core.logging_config import setup_logging, RequestLoggingMiddleware
from app.core.middleware import SecurityHeadersMiddleware, RateLimitMiddleware
from app.models import models  # noqa: F401
from app.routers import auth, resume, optimize, interview, applications, analytics, skills
from app.services.vector_store import vector_health

setup_logging()

# Dev convenience: create tables if missing. Prefer Alembic for real migrations:
#   cd backend && alembic upgrade head
Base.metadata.create_all(bind=engine)


def _normalize_user_emails() -> None:
    """One-shot heal: store all emails lowercased (fixes legacy login misses)."""
    try:
        from sqlalchemy.orm import Session
        from app.models.models import User

        db: Session = SessionLocal()
        try:
            changed = 0
            for u in db.query(User).all():
                if not u.email:
                    continue
                low = u.email.strip().lower()
                if u.email != low:
                    clash = (
                        db.query(User)
                        .filter(User.email == low, User.id != u.id)
                        .first()
                    )
                    if clash:
                        continue
                    u.email = low
                    changed += 1
            if changed:
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


_normalize_user_emails()

if settings.is_production and settings.SECRET_KEY in {
    "your-super-secret-key-change-in-production",
    "change-me",
    "supersecretkeychangethisinproduction2025",
}:
    raise RuntimeError("Refusing to start: set a strong SECRET_KEY in production")

app = FastAPI(
    title="CareerForge AI",
    description=(
        "AI career platform: hybrid ATS scoring, resume optimization (SQL + Chroma), "
        "cover letters, mock interviews, and application tracking.\n\n"
        "**Migrations:** run `alembic upgrade head` from `backend/`.\n"
        "**Prod DB:** set `DATABASE_URL` to PostgreSQL."
    ),
    version="1.3.0",
)

register_exception_handlers(app)

# Middleware: last added runs first on request
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(resume.router, prefix="/api/resume", tags=["resume"])
app.include_router(optimize.router, prefix="/api", tags=["optimize"])
app.include_router(interview.router, prefix="/api/interview", tags=["interview"])
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(skills.router, prefix="/api/skills", tags=["skills"])


@app.get("/")
def root():
    return {"message": "CareerForge AI Backend is Running Successfully!", "version": "1.3.0"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "db": ping_db(),
        "vector": vector_health(),
        "env": settings.APP_ENV,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
