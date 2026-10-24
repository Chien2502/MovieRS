"""Thời gian của prototype không được âm thầm diễn giải theo timezone server."""

from src.data.migrate_runtime import legacy_time


def test_naive_legacy_uses_declared_project_timezone():
    value=legacy_time('2026-10-16 07:00:00')
    assert value.utcoffset().total_seconds()==7*3600
    assert int(value.timestamp())==int(legacy_time('2026-10-16T00:00:00Z').timestamp())


def test_explicit_timezone_is_preserved():
    assert legacy_time('2026-10-16T00:00:00+00:00').utcoffset().total_seconds()==0
