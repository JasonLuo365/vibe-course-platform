from datetime import datetime, timezone


def utcnow() -> datetime:
    """全项目唯一时间源：naive UTC（spec 约束）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
