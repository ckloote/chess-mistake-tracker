"""One-time retune: tighten the "still winning" suppression and prune the
marginal inaccuracies it now covers — WITHOUT re-running detection (which would
drop+recreate rows and wipe classifications).

- Sets suppress_above_before/after = 75/68 on the AppSettings singleton (so
  future imports apply it automatically).
- Deletes existing mistakes that the updated, severity-aware _is_suppressed
  would now suppress — but ONLY those still unclassified. Anything you've
  already classified is preserved even if it now falls in the suppressed band.

Idempotent: re-running deletes nothing once the prune is done.

Run: `uv run python scripts/retune_suppression.py`
"""
from __future__ import annotations

from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.models import Mistake
from backend.app.services.app_settings import get_app_settings
from backend.app.services.mistake_detection import _is_suppressed, _Thresholds

NEW_SUPPRESS_ABOVE_BEFORE = 75.0
NEW_SUPPRESS_ABOVE_AFTER = 68.0


def main() -> int:
    with SessionLocal() as session:
        settings = get_app_settings(session)
        settings.suppress_above_before = NEW_SUPPRESS_ABOVE_BEFORE
        settings.suppress_above_after = NEW_SUPPRESS_ABOVE_AFTER
        session.flush()
        t = _Thresholds.from_app_settings(settings)

        mistakes = session.scalars(select(Mistake)).all()
        to_delete = []
        preserved_classified = 0
        for m in mistakes:
            suppressed = _is_suppressed(
                m.winrate_before, m.winrate_after, m.severity, t
            )
            if not suppressed:
                continue
            if m.classified_at is not None:
                preserved_classified += 1
                continue
            to_delete.append(m)

        for m in to_delete:
            session.delete(m)
        session.commit()

    print(
        f"Suppression set to {NEW_SUPPRESS_ABOVE_BEFORE}/{NEW_SUPPRESS_ABOVE_AFTER} "
        f"(inaccuracy-only). Deleted {len(to_delete)} unclassified marginal "
        f"inaccuracies; preserved {preserved_classified} already-classified "
        f"mistakes that now fall in the suppressed band."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
