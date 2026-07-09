"""Seed the single user from configured LICHESS_USERNAME. Idempotent.

CHESSCOM_USERNAME seeds users.chesscom_username only while the column is
empty — once set (here or via the Settings page), the DB value governs and
the env is never consulted again (same semantics as the AppSettings seed).
"""
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
        user = session.scalar(
            select(User).where(User.lichess_username == settings.lichess_username)
        )
        if user is None:
            user = User(lichess_username=settings.lichess_username)
            session.add(user)
            session.commit()
            print(f"Created user '{settings.lichess_username}' (id={user.id}).")
        else:
            print(f"User '{settings.lichess_username}' already exists (id={user.id}).")

        if settings.chesscom_username and not user.chesscom_username:
            user.chesscom_username = settings.chesscom_username
            session.commit()
            print(f"Seeded chess.com username '{settings.chesscom_username}'.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
