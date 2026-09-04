from datetime import datetime, timezone


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_quarter(dt: datetime | None = None) -> tuple[int, int]:
    """Return a (year, quarter) tuple. quarter is 1-4."""
    dt = dt or datetime.now(timezone.utc)
    return dt.year, (dt.month - 1) // 3 + 1
