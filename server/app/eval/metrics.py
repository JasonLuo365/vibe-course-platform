import datetime
import re
from .parser import RolloutTimeline, Turn

_ERROR_KEYWORDS = ("error", "报错", "失败", "traceback")
_CORRECTION_MARKERS = (
    "fix",
    "fixed",
    "fixing",
    "retry",
    "retrying",
    "try again",
    "again",
    "correct",
    "修正",
    "修改",
    "改",
    "修",
    "重新",
    "adjust",
)

# Heuristic regex for file paths inside tool text.
_PATH_RE = re.compile(
    r'(?:[A-Za-z]:\\[^\s"\'`]+)|'           # Windows absolute paths
    r'(?:[~.]?/[^\s"\'`]+)|'                  # Unix absolute/relative paths
    r'(?:[\w\-.]+(?:/[\w\-.]+)+\.?\w*)',      # generic slash-separated paths
    re.UNICODE,
)


def _parse_ts(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        # Python 3.11+ supports the trailing 'Z' natively.
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


def _contains_error(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in _ERROR_KEYWORDS)


def _is_correction(turn: Turn) -> bool:
    if turn.kind != "user":
        return False
    lowered = turn.text.lower()
    return any(marker in lowered for marker in _CORRECTION_MARKERS)


def _extract_paths(text: str) -> set[str]:
    return set(_PATH_RE.findall(text))


def compute_metrics(timelines: list[RolloutTimeline]) -> dict:
    sessions = len(timelines)
    turns = 0
    user_turns = 0
    error_fix_cycles = 0
    files_touched: set[str] = set()

    all_ts: list[datetime.datetime] = []

    for timeline in timelines:
        for i, turn in enumerate(timeline.turns):
            turns += 1
            if turn.kind == "user":
                user_turns += 1

            if turn.ts:
                ts = _parse_ts(turn.ts)
                if ts:
                    all_ts.append(ts)

            # Error-fix cycle detection.
            if turn.kind in ("user", "tool") and _contains_error(turn.text):
                window = timeline.turns[i + 1 : i + 4]
                if any(_is_correction(t) for t in window):
                    error_fix_cycles += 1

            if turn.kind == "tool":
                files_touched.update(_extract_paths(turn.text))

    duration_min = 0
    if len(all_ts) >= 2:
        duration_min = int(round((max(all_ts) - min(all_ts)).total_seconds() / 60.0))

    return {
        "sessions": sessions,
        "turns": turns,
        "user_turns": user_turns,
        "duration_min": duration_min,
        "error_fix_cycles": error_fix_cycles,
        "files_touched": len(files_touched),
    }
