"""Tests for the paginated news ingestion window logic.

The bug these guard against: requesting a wide date range in one call returns
only the most recent ~250 headlines, leaving the rest of the timeline empty
while still producing a healthy-looking row count. Chunking the range fixes
it, so the chunking itself needs to be exactly right -- no gaps (which lose
news) and no overlaps (which waste rate-limited calls).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.ingest_news import date_chunks


def test_single_chunk_when_range_fits():
    chunks = date_chunks(date(2027, 1, 1), date(2027, 1, 10), chunk_days=30)
    assert chunks == [(date(2027, 1, 1), date(2027, 1, 10))]


def test_splits_into_expected_number_of_windows():
    chunks = date_chunks(date(2027, 1, 1), date(2027, 1, 30), chunk_days=10)
    assert len(chunks) == 3
    assert chunks[0] == (date(2027, 1, 1), date(2027, 1, 10))
    assert chunks[-1][1] == date(2027, 1, 30)


def test_windows_are_contiguous_with_no_gaps():
    chunks = date_chunks(date(2027, 1, 1), date(2027, 3, 15), chunk_days=14)
    for earlier, later in zip(chunks, chunks[1:]):
        # The next window must start the very next day.
        assert later[0] == earlier[1] + timedelta(days=1)


def test_windows_do_not_overlap():
    chunks = date_chunks(date(2027, 1, 1), date(2027, 3, 15), chunk_days=14)
    for earlier, later in zip(chunks, chunks[1:]):
        assert earlier[1] < later[0]


def test_full_range_is_covered():
    start, end = date(2026, 8, 1), date(2027, 7, 31)
    chunks = date_chunks(start, end, chunk_days=14)
    assert chunks[0][0] == start
    assert chunks[-1][1] == end
    # Every day in the range belongs to exactly one window.
    covered = sum((c[1] - c[0]).days + 1 for c in chunks)
    assert covered == (end - start).days + 1


def test_year_of_history_produces_many_windows():
    chunks = date_chunks(date(2026, 7, 28), date(2027, 7, 28), chunk_days=14)
    # ~26 fortnightly windows, each with its own 250-item budget.
    assert 24 <= len(chunks) <= 28


def test_reversed_range_is_empty():
    assert date_chunks(date(2027, 5, 1), date(2027, 1, 1), chunk_days=7) == []


def test_same_day_range():
    d = date(2027, 4, 4)
    assert date_chunks(d, d, chunk_days=7) == [(d, d)]


def test_invalid_chunk_size_rejected():
    with pytest.raises(ValueError):
        date_chunks(date(2027, 1, 1), date(2027, 2, 1), chunk_days=0)