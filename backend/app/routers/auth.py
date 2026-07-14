from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_user,
    get_password_hash,
    get_user_by_email,
    validate_password_strength,
    verify_password,
)
from app.models.models import User
from app.schemas.schemas import (
    PasswordChange,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)

router = APIRouter()


@router.post("/signup", response_model=Token)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    email = user.email.strip().lower()
    name = user.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    db_user = get_user_by_email(db, email)
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered. Try logging in instead.",
        )

    strength_err = validate_password_strength(user.password)
    if strength_err:
        raise HTTPException(status_code=400, detail=strength_err)

    hashed_password = get_password_hash(user.password)
    new_user = User(email=email, name=name, password_hash=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token({"sub": email})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    email = user.email.strip().lower()
    db_user = get_user_by_email(db, email)
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    # Heal legacy mixed-case emails so future logins are exact-match fast
    if db_user.email != email:
        db_user.email = email
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

    token = create_access_token({"sub": email})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(current_user, k, v)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password")
def change_password(
    body: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    strength_err = validate_password_strength(body.new_password)
    if strength_err:
        raise HTTPException(status_code=400, detail=strength_err)
    current_user.password_hash = get_password_hash(body.new_password)
    db.add(current_user)
    db.commit()
    return {"message": "Password updated successfully"}
