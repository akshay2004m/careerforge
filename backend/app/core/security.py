import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.models import User

# TokenUrl is documentation-only for OAuth2 password flow swagger
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _password_bytes(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes — hash and verify must match
    return password.encode("utf-8")[:72]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(_password_bytes(plain_password), hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    rounds = max(10, min(int(settings.BCRYPT_ROUNDS or 12), 14))
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def validate_password_strength(password: str) -> Optional[str]:
    """Return error message if weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must include letters and numbers"
    return None


def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    # Use numeric timestamps — most reliable across python-jose versions
    to_encode.update({"exp": int(expire.timestamp()), "iat": int(now.timestamp())})
    # Always store subject email in lowercase
    if "sub" in to_encode and isinstance(to_encode["sub"], str):
        to_encode["sub"] = to_encode["sub"].strip().lower()
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Case-insensitive email lookup."""
    if not email:
        return None
    normalized = email.strip().lower()
    # Prefer exact match (emails are stored lowercased)
    user = db.query(User).filter(User.email == normalized).first()
    if user:
        return user
    # Fallback for legacy mixed-case rows
    from sqlalchemy import func

    return db.query(User).filter(func.lower(User.email) == normalized).first()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require_exp": True, "require_sub": True},
        )
        email = payload.get("sub")
        if not email or not isinstance(email, str):
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_by_email(db, email)
    if user is None:
        raise credentials_exception
    return user


def assert_user_owns(resource_user_id: int, current_user: User) -> None:
    """Hard ownership check — never trust client-supplied user ids."""
    if resource_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
