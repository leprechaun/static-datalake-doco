from datetime import UTC, datetime, timedelta

from datalake_doco.freshness import freshness
from datalake_doco.models import HistoryEntry

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def _entry(hours_ago: float, operation: str = "WRITE") -> HistoryEntry:
    ts = (NOW - timedelta(hours=hours_ago)).isoformat()
    return HistoryEntry(version=0, timestamp=ts, operation=operation, parameters={}, description=None, engine_info=None)


def test_hourly_writes():
    f = freshness([_entry(3), _entry(4), _entry(5), _entry(6)], NOW)
    assert f["lastWrite"] == (NOW - timedelta(hours=3)).isoformat()
    assert f["secondsSinceLastWrite"] == 3 * 3600
    assert f["typicalIntervalSeconds"] == 3600
    assert f["ratio"] == 3.0
    assert f["dataCommits"] == 4


def test_metadata_and_compaction_commits_are_ignored():
    f = freshness([_entry(0.1, "OPTIMIZE"), _entry(0.2, "UPDATE TABLE METADATA"), _entry(2), _entry(4)], NOW)
    assert f["secondsSinceLastWrite"] == 2 * 3600
    assert f["typicalIntervalSeconds"] == 2 * 3600
    assert f["dataCommits"] == 2


def test_single_write_has_no_interval():
    f = freshness([_entry(48)], NOW)
    assert f["typicalIntervalSeconds"] is None
    assert f["ratio"] is None
    assert f["secondsSinceLastWrite"] == 48 * 3600


def test_no_data_writes():
    assert freshness([_entry(1, "OPTIMIZE")], NOW) is None


def test_interval_uses_only_recent_commits():
    # 60 hourly writes, then 50 more that are a day apart: only the newest 50 count.
    history = [_entry(24 * i) for i in range(50)] + [_entry(24 * 50 + i) for i in range(60)]
    assert freshness(history, NOW)["typicalIntervalSeconds"] == 24 * 3600


def test_sub_second_interval_keeps_a_decimal():
    f = freshness([_entry(1), _entry(1 - 0.4 / 3600), _entry(1 - 0.8 / 3600)], NOW)
    assert f["typicalIntervalSeconds"] == 0.4


def test_backfill_burst_counts_as_one_write():
    # Like owntracks.bronze.location_records: 15-minute writes, with a backfill of 85 commits
    # 0.4 s apart in the middle of the history that's read.
    quarter = 0.25
    newest = [_entry(quarter * i) for i in range(1, 5)]
    burst = [_entry(1.25 + i * 0.4 / 3600) for i in range(85)]
    oldest = [_entry(2 + quarter * i) for i in range(11)]
    f = freshness(newest + burst + oldest, NOW)
    assert f["typicalIntervalSeconds"] == 900
    assert f["burstGapSeconds"] == 60
    assert f["ratio"] == 1.0


def test_table_writing_every_few_seconds_keeps_its_cadence():
    # Every gap is under the burst threshold, apart from one pause: that's the cadence, not a burst.
    history = [_entry(i * 10 / 3600) for i in range(60)] + [_entry(2)]
    f = freshness(history, NOW)
    assert f["typicalIntervalSeconds"] == 10
    assert f["burstGapSeconds"] is None


def test_interval_window_counts_gaps_between_bursts():
    # 49 hourly gaps are found even though bursts of 3 commits fill most of the history read.
    history = [_entry(h + i / 3600) for h in range(60) for i in range(3)]
    f = freshness(history, NOW)
    assert f["typicalIntervalSeconds"] == 3600 - 2
    assert f["intervalGaps"] == 49


def test_naive_history_timestamps_are_utc():
    entry = HistoryEntry(version=0, timestamp="2026-11-06T11:00:00", operation="WRITE", parameters={}, description=None, engine_info=None)
    assert freshness([entry], NOW)["secondsSinceLastWrite"] == 3600
