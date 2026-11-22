
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    user_data: UserRegister,
    db: Session = Depends(get_db),
):
    try:
        user = AuthService.register(db, user_data)

        return {
            "message": "User registered successfully",
            "user_id": str(user.id),
            "email": user.email,
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.post("/login", response_model=TokenResponse)
def login(
    user_data: UserLogin,
    db: Session = Depends(get_db),
):
    try:
        token = AuthService.login(
            db,
            str(user_data.email),
            user_data.password,
        )

        return {"access_token": token}

    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )
