"""Economic-news blackout filter for live trade entries.

This module checks the upcoming economic calendar and blocks entries when a
configured high-impact release is near the symbol's time window. It caches the
calendar data briefly to reduce network usage.
"""

import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

_cached_events = []
_cache_expires_at = datetime.min.replace(tzinfo=timezone.utc)
_last_fetch_warning = None


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _load_events(cache_minutes):
    global _cached_events, _cache_expires_at, _last_fetch_warning

    now = datetime.now(timezone.utc)
    if now < _cache_expires_at:
        return _cached_events

    request = Request(
        CALENDAR_URL,
        headers={"User-Agent": "Mozilla/5.0 MT5-news-filter"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
        events = []
        for event in payload:
            event_time = datetime.fromisoformat(
                event["date"].replace("Z", "+00:00")
            )
            events.append({
                "time": _as_utc(event_time),
                "currency": str(event.get("country", "")).upper(),
                "impact": str(event.get("impact", "")).lower(),
                "title": event.get("title", "Unknown event"),
            })
        _cached_events = events
        _cache_expires_at = now + timedelta(minutes=cache_minutes)
        _last_fetch_warning = None
        return _cached_events
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        warning = f"News calendar unavailable: {error}"
        if warning != _last_fetch_warning:
            print(warning)
            _last_fetch_warning = warning
        _cache_expires_at = now + timedelta(minutes=cache_minutes)
        return _cached_events


def news_blackout_active(
    at_time,
    currencies=("USD",),
    minimum_impact="high",
    minutes_before=30,
    minutes_after=30,
    cache_minutes=15,
):
    """Return an event when a configured high-impact release is near, else None."""
    check_time = _as_utc(at_time)
    allowed_currencies = {currency.upper() for currency in currencies}
    allowed_impacts = {"high"} if minimum_impact.lower() == "high" else {"high", "medium"}

    for event in _load_events(cache_minutes):
        if event["currency"] not in allowed_currencies:
            continue
        if event["impact"] not in allowed_impacts:
            continue

        window_start = event["time"] - timedelta(minutes=minutes_before)
        window_end = event["time"] + timedelta(minutes=minutes_after)
        if window_start <= check_time <= window_end:
            return event

    return None
