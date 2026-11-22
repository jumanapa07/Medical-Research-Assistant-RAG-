
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)


class AuthService:

    @staticmethod
    def register(db: Session, user_data):

        existing_user = db.scalar(
            select(User).where(
                User.email == user_data.email
            )
        )

        if existing_user:
            raise ValueError("Email already registered")

        user = User(
            email=str(user_data.email).lower(),
            full_name=user_data.full_name,
            hashed_password=hash_password(user_data.password),
            role="member",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def login(db: Session, email: str, password: str):

        user = db.scalar(
            select(User).where(
                User.email == email.lower()
            )
        )

        if not user or not verify_password(
            password,
            user.hashed_password,
        ):
            raise ValueError("Invalid email or password")

        if not user.is_active:
            raise ValueError("Account is inactive")

        return create_access_token(user.id)
