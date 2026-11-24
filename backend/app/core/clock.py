"""Single source of "now" for business rules.

Services call clock.utcnow() (not datetime.now directly) so tests can move time
forward, e.g. to test the 15-minute check-in window or the no-show rule.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
