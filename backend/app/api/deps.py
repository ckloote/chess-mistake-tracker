"""Small helpers shared across API routers."""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.models import User


def get_configured_user(db: Session, settings: Settings) -> User:
    if not settings.lichess_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LICHESS_USERNAME is not configured.",
        )
    user = db.scalar(select(User).where(User.lichess_username == settings.lichess_username))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configured user not found in DB. Run `make seed` first.",
        )
    return user
