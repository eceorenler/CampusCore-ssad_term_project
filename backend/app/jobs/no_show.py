"""No-show job (spec R7 and section 8).

Every minute: CONFIRMED reservations with now > start_time + 15 min become NO_SHOW,
which releases their remaining time (the GiST overlap guard ignores NO_SHOW rows).

Runs as a background thread inside the API process (started in app.main). If several
API processes run, a PostgreSQL advisory lock makes sure only one does the work per tick.
Can also be run once by hand:  python -m app.jobs.no_show
"""

import logging
import threading

from sqlalchemy import text

from app.core import clock
from app.db.session import SessionLocal
from app.modules.reservations.rules import mark_no_shows

log = logging.getLogger("campuscore.jobs.no_show")

_ADVISORY_LOCK_KEY = 307_001  # arbitrary constant, unique to this job


def run_once() -> list[int]:
    """One pass in one transaction. Returns the IDs marked NO_SHOW."""
    with SessionLocal() as db:
        got_lock = db.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
        if not got_lock:
            db.rollback()
            return []
        ids = mark_no_shows(db, clock.utcnow())
        db.commit()
    if ids:
        log.info("marked NO_SHOW: %s", ids)
    return ids


class NoShowWorker:
    def __init__(self, interval_seconds: int):
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="no-show-job", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                run_once()
            except Exception:  # keep the worker alive; failures are logged (UC-05 A5)
                log.exception("no-show job failed")
            self._stop.wait(self.interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    marked = run_once()
    print(f"Marked {len(marked)} reservation(s) as NO_SHOW: {marked}")
