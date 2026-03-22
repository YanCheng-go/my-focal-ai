"""Tests for shared ingestion utilities — utc_today(), rank_to_score()."""

from datetime import datetime, timezone

from ainews.ingest import rank_to_score, utc_today

# --- utc_today ---


def test_utc_today_returns_midnight():
    result = utc_today()
    assert result.hour == 0
    assert result.minute == 0
    assert result.second == 0
    assert result.microsecond == 0


def test_utc_today_is_utc():
    result = utc_today()
    assert result.tzinfo == timezone.utc


def test_utc_today_is_today():
    result = utc_today()
    now = datetime.now(timezone.utc)
    assert result.date() == now.date()


# --- rank_to_score ---


def test_rank_to_score_first_place():
    assert rank_to_score(1, 10) == 1.0


def test_rank_to_score_last_place():
    assert rank_to_score(10, 10) == 0.1


def test_rank_to_score_middle():
    # rank 5 of 10 => 1.0 - 4/10 = 0.6
    assert rank_to_score(5, 10) == 0.6


def test_rank_to_score_single_item():
    assert rank_to_score(1, 1) == 1.0


def test_rank_to_score_total_zero_no_crash():
    # total=0 should not ZeroDivisionError; max(total,1) protects
    result = rank_to_score(1, 0)
    assert result == 1.0


def test_rank_to_score_rounds_to_four_decimals():
    # rank 2 of 3 => 1.0 - 1/3 = 0.6667 (rounded)
    result = rank_to_score(2, 3)
    assert result == 0.6667
