"""When a table's data was last written, and how that compares to how often it's written."""

from datetime import UTC, datetime
from itertools import pairwise
from statistics import median

from datalake_doco.config import (
    BURST_GAP_SECONDS,
    DATA_OPERATIONS,
    FRESHNESS_GAPS,
    MIN_INTERVAL_GAPS,
)
from datalake_doco.models import HistoryEntry


def freshness(history: list[HistoryEntry], now: datetime) -> dict | None:
    """Facts from the data-changing commits in `history`, measured up to `now`.

    The typical interval is the median of the last FRESHNESS_GAPS gaps between data commits,
    leaving out gaps under BURST_GAP_SECONDS so a burst of commits (a backfill) counts as one
    write; with fewer than MIN_INTERVAL_GAPS such gaps, the table writes that often and every
    gap counts. `ratio` is the time since the last write divided by the typical interval. Both
    are None with fewer than two data commits. Returns None when there are no data commits.
    """
    writes = sorted(
        (_parse(h.timestamp) for h in history if h.operation in DATA_OPERATIONS and h.timestamp),
        reverse=True,
    )
    if not writes:
        return None
    since = (now - writes[0]).total_seconds()
    gaps = [(a - b).total_seconds() for a, b in pairwise(writes)]
    spaced = [g for g in gaps if g >= BURST_GAP_SECONDS][:FRESHNESS_GAPS]
    burst_gap = BURST_GAP_SECONDS if len(spaced) >= MIN_INTERVAL_GAPS else None
    used = spaced if burst_gap else gaps[:FRESHNESS_GAPS]
    interval = median(used) if used else None
    return {
        "lastWrite": writes[0].isoformat(),
        "secondsSinceLastWrite": round(since),
        "typicalIntervalSeconds": round(interval, 1) if interval is not None else None,
        "intervalGaps": len(used),
        "burstGapSeconds": burst_gap,
        "dataCommits": len(writes),
        "ratio": round(since / interval, 2) if interval else None,
    }


def _parse(ts: str) -> datetime:
    parsed = datetime.fromisoformat(ts)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
