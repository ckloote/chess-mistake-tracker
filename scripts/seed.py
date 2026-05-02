"""Seed the single user from configured LICHESS_USERNAME. Idempotent."""
import sys

from sqlalchemy import select

from backend.app.config import get_settings
from backend.app.db import SessionLocal
from backend.app.models import User


def main() -> int:
    settings = get_settings()
    if not settings.lichess_username:
        print("LICHESS_USERNAME is not set; nothing to seed.", file=sys.stderr)
        return 1

    with SessionLocal() as session:
        existing = session.scalar(
            select(User).where(User.lichess_username == settings.lichess_username)
        )
        if existing is not None:
            print(f"User '{settings.lichess_username}' already exists (id={existing.id}).")
            return 0

        user = User(lichess_username=settings.lichess_username)
        session.add(user)
        session.commit()
        print(f"Created user '{settings.lichess_username}' (id={user.id}).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
