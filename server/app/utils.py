from datetime import datetime, timedelta, timezone


# The teacher-facing web form uses ``datetime-local`` and therefore has no
# timezone offset.  Classes are currently operated in China Standard Time.
TEACHER_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def utcnow() -> datetime:
    """全项目唯一时间源：naive UTC（spec 约束）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def teacher_local_to_naive_utc(value: datetime) -> datetime:
    """Convert a teacher-entered local wall time into the UTC database value."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=TEACHER_TIMEZONE)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def format_teacher_time(value: datetime) -> str:
    """Render the UTC database value as a teacher's local wall time."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TEACHER_TIMEZONE).strftime("%Y-%m-%d %H:%M")
