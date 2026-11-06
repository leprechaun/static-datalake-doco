"""Tunable constants for time distributions and table freshness, kept in one place."""

# Time zone that tz-aware timestamps are converted to before bucketing into days, weekdays and
# hours. Naive timestamps and dates are always bucketed as stored.
BUCKET_TIMEZONE = "UTC"

# How many gap ranges the Markdown page lists before summarising the rest.
MAX_GAP_RANGES = 5

# Delta operations that change a table's data, as opposed to compaction or metadata commits.
DATA_OPERATIONS = frozenset({"WRITE", "MERGE", "DELETE", "UPDATE"})

# The typical write interval is the median of up to this many of the most recent gaps between
# data commits.
FRESHNESS_GAPS = 49

# Data commits closer together than this are one burst (e.g. a backfill writing hundreds of
# commits a second apart), so the gaps inside it don't count towards the typical interval.
# Tables that genuinely write this often leave fewer than MIN_INTERVAL_GAPS longer gaps, and
# fall back to the median of all gaps.
BURST_GAP_SECONDS = 60
MIN_INTERVAL_GAPS = 3

# History entries read per table unless --history-limit says otherwise. Each entry is a separate
# commit file to fetch, and busy tables keep thousands; 100 still covers FRESHNESS_GAPS gaps
# between data commits when about half the commits are compaction.
DEFAULT_HISTORY_LIMIT = 100

# Soft open-file limit the CLI raises itself to at startup (capped at the hard limit), since
# S3 reads keep many pooled connections open.
OPEN_FILE_LIMIT = 65536
