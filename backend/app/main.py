import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine, ping_db
from app.core.errors import register_exception_handlers
from app.core.logging_config import RequestLoggingMiddleware, setup_logging
from app.core.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.models import models  # noqa: F401
from app.routers import analytics, applications, auth, interview, optimize, resume, skills
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
                    clash = db.query(User).filter(User.email == low, User.id != u.id).first()
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

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ====================== STARTUP CHECK ======================
    if settings.APP_ENV == "production":
        if settings.DATABASE_URL.startswith("sqlite"):
            error_msg = (
                "❌ Production environment cannot use SQLite database. "
                "Please set a valid PostgreSQL DATABASE_URL "
                "(e.g., from Neon or Supabase)."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)
        if settings.SECRET_KEY in {
            "your-super-secret-key-change-in-production",
            "change-me",
            "supersecretkeychangethisinproduction2025",
        }:
            raise RuntimeError("Refusing to start: set a strong SECRET_KEY in production")

    logger.info(f"✅ Starting in {settings.APP_ENV} mode")
    yield
    # Shutdown code (if needed)
    logger.info("Shutting down application...")


app = FastAPI(
    title="CareerForge AI",
    description="AI-powered career coaching platform",
    version="1.0.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

# Middleware: last added runs first on request
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://benevolent-dodol-c25ae5.netlify.app",
        "https://deploy-preview-1--benevolent-dodol-c25ae5.netlify.app",
        "https://careerforge-ute15mq7y-akshays-projects-48a89927.vercel.app",
        "https://careerforge-9ijp2z0gh-akshays-projects-48a89927.vercel.app",
        "https://careerforge-five-peach.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
