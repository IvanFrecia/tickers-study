"""Market-calendar helpers for forecast horizon and weekly close targeting."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
from pandas.tseries.offsets import BDay

DEFAULT_EXCHANGE = "NYSE"
MARKET_TIMEZONE = "America/New_York"
REGULAR_MARKET_OPEN = time(9, 30)
REGULAR_MARKET_CLOSE = time(16, 0)


def _coerce_date(value: date | datetime | pd.Timestamp | str) -> date:
    """Coerce multiple input shapes to a pure date."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, pd.Timestamp):
        return value.date()
    return pd.Timestamp(value).date()


def _next_monday(day: date) -> date:
    """Move weekend values to the next Monday; keep weekdays unchanged."""
    if day.weekday() == 5:
        return day + timedelta(days=2)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _market_schedule(start_date: date, end_date: date, exchange: str = DEFAULT_EXCHANGE) -> list[date]:
    """Return trading sessions for the date span, falling back to weekdays."""
    if end_date < start_date:
        return []
    try:
        import pandas_market_calendars as mcal  # type: ignore

        calendar = mcal.get_calendar(exchange)
        schedule = calendar.schedule(start_date=start_date.isoformat(), end_date=end_date.isoformat())
        sessions = [ts.date() for ts in schedule.index]
        if sessions:
            return sessions
    except Exception:
        pass
    return [ts.date() for ts in pd.bdate_range(start=start_date, end=end_date)]


def _regular_holidays_between(start_date: date, end_date: date, exchange: str = DEFAULT_EXCHANGE) -> dict[date, str]:
    """Return named exchange holidays for a date window when the calendar exposes them."""
    try:
        import pandas_market_calendars as mcal  # type: ignore

        calendar = mcal.get_calendar(exchange)
        holidays = calendar.regular_holidays.holidays(
            start_date.isoformat(),
            end_date.isoformat(),
            return_name=True,
        )
    except Exception:
        return {}

    named: dict[date, str] = {}
    for raw_date, raw_name in holidays.items():
        parsed = _coerce_date(raw_date)
        named[parsed] = _friendly_holiday_name(str(raw_name))
    return named


def _calendar_source(exchange: str = DEFAULT_EXCHANGE) -> str:
    """Return the active calendar backend name for operator-facing diagnostics."""
    try:
        import pandas_market_calendars as mcal  # type: ignore

        mcal.get_calendar(exchange)
    except Exception:
        return "weekday_fallback"
    return "pandas_market_calendars"


def _friendly_holiday_name(name: str) -> str:
    """Normalize exchange-calendar holiday rule names for operator-facing payloads."""
    if "Juneteenth" in name:
        return "Juneteenth National Independence Day"
    if "New Years" in name or "New Year's" in name:
        return "New Year's Day"
    if "Martin Luther King" in name:
        return "Martin Luther King, Jr. Day"
    if "Presidents" in name or "Washingtons" in name:
        return "Washington's Birthday"
    if "July 4" in name:
        return "Independence Day"
    return name


def _market_schedule_details(
    start_date: date,
    end_date: date,
    exchange: str = DEFAULT_EXCHANGE,
    timezone_name: str = MARKET_TIMEZONE,
) -> list[dict[str, Any]]:
    """Return session dates with open/close timestamps, falling back to regular hours."""
    if end_date < start_date:
        return []
    try:
        import pandas_market_calendars as mcal  # type: ignore

        calendar = mcal.get_calendar(exchange)
        schedule = calendar.schedule(start_date=start_date.isoformat(), end_date=end_date.isoformat())
        details = []
        for index, row in schedule.iterrows():
            session_date = _coerce_date(index)
            market_open = pd.Timestamp(row["market_open"]).to_pydatetime()
            market_close = pd.Timestamp(row["market_close"]).to_pydatetime()
            if market_open.tzinfo is None:
                market_open = market_open.replace(tzinfo=timezone.utc)
            if market_close.tzinfo is None:
                market_close = market_close.replace(tzinfo=timezone.utc)
            details.append(
                {
                    "date": session_date,
                    "market_open": market_open.astimezone(timezone.utc),
                    "market_close": market_close.astimezone(timezone.utc),
                }
            )
        if details:
            return details
    except Exception:
        pass

    local_tz = ZoneInfo(timezone_name)
    details = []
    for session_date in _market_schedule(start_date, end_date, exchange=exchange):
        details.append(
            {
                "date": session_date,
                "market_open": datetime.combine(session_date, REGULAR_MARKET_OPEN, tzinfo=local_tz).astimezone(
                    timezone.utc
                ),
                "market_close": datetime.combine(session_date, REGULAR_MARKET_CLOSE, tzinfo=local_tz).astimezone(
                    timezone.utc
                ),
            }
        )
    return details


def _is_date_only_string(value: str) -> bool:
    """Return True when a string carries a date without an explicit time."""
    cleaned = value.strip()
    return bool(cleaned) and "T" not in cleaned and ":" not in cleaned and len(cleaned) <= 10


def _utc_now(value: date | datetime | pd.Timestamp | str | None, timezone_name: str = MARKET_TIMEZONE) -> datetime:
    """Coerce an optional value to an aware UTC datetime.

    Date-only anchors represent the market close for that date. This keeps persisted
    forecast artifacts from labeling a target-date context as a live intraday clock.
    """
    if value is None:
        return datetime.now(timezone.utc)
    local_tz = ZoneInfo(timezone_name)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, REGULAR_MARKET_CLOSE, tzinfo=local_tz)
    elif isinstance(value, pd.Timestamp):
        parsed = value.to_pydatetime()
    elif isinstance(value, str) and _is_date_only_string(value):
        parsed = datetime.combine(pd.Timestamp(value).date(), REGULAR_MARKET_CLOSE, tzinfo=local_tz)
    else:
        parsed = pd.Timestamp(value).to_pydatetime()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(timezone.utc)


def _iso_datetime(value: datetime, timezone_name: str | None = None) -> str:
    """Serialize a datetime in UTC or a requested timezone."""
    if timezone_name:
        value = value.astimezone(ZoneInfo(timezone_name))
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def trading_sessions_between(
    start_date: date | datetime | pd.Timestamp | str,
    end_date: date | datetime | pd.Timestamp | str,
    exchange: str = DEFAULT_EXCHANGE,
) -> list[date]:
    """List market sessions between start and end (inclusive)."""
    return _market_schedule(_coerce_date(start_date), _coerce_date(end_date), exchange=exchange)


def latest_market_session_on_or_before(
    anchor: date | datetime | pd.Timestamp | str,
    exchange: str = DEFAULT_EXCHANGE,
) -> date:
    """Return the most recent actual market session on or before the anchor date."""
    anchor_day = _coerce_date(anchor)
    lookback_start = anchor_day - timedelta(days=14)
    sessions = trading_sessions_between(lookback_start, anchor_day, exchange=exchange)
    if sessions:
        return sessions[-1]
    fallback = pd.Timestamp(anchor_day)
    if fallback.weekday() >= 5:
        fallback = fallback - BDay(1)
    return fallback.date()


def forecast_dates_after(
    last_observation: date | datetime | pd.Timestamp | str,
    horizon: int,
    exchange: str = DEFAULT_EXCHANGE,
) -> list[str]:
    """Return next `horizon` market session dates after the last observation."""
    if horizon <= 0:
        return []
    last_day = _coerce_date(last_observation)
    start = last_day + timedelta(days=1)
    sessions: list[date] = []
    span_days = max(14, horizon * 4)
    while len(sessions) < horizon:
        end = start + timedelta(days=span_days)
        sessions = _market_schedule(start, end, exchange=exchange)
        span_days *= 2
        if span_days > 730:
            break
    if len(sessions) >= horizon:
        return [d.isoformat() for d in sessions[:horizon]]
    fallback = [pd.Timestamp(last_day) + BDay(step) for step in range(1, horizon + 1)]
    return [ts.strftime("%Y-%m-%d") for ts in fallback]


def week_window(anchor: date | datetime | pd.Timestamp | str) -> tuple[date, date]:
    """Return Monday-Friday window for the provided anchor date."""
    anchor_day = _next_monday(_coerce_date(anchor))
    monday = anchor_day - timedelta(days=anchor_day.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def market_week_end(anchor: date | datetime | pd.Timestamp | str, exchange: str = DEFAULT_EXCHANGE) -> date:
    """Return last market session in the anchor week (or Friday fallback)."""
    monday, friday = week_window(anchor)
    sessions = _market_schedule(monday, friday, exchange=exchange)
    return sessions[-1] if sessions else friday


def next_market_week_end(
    last_observation: date | datetime | pd.Timestamp | str,
    exchange: str = DEFAULT_EXCHANGE,
) -> date:
    """Return the next market week-end close after a given observation date."""
    last_day = _coerce_date(last_observation)
    anchor = _next_monday(last_day + timedelta(days=1))
    return market_week_end(anchor, exchange=exchange)


def following_market_week_end(
    last_observation: date | datetime | pd.Timestamp | str,
    exchange: str = DEFAULT_EXCHANGE,
) -> date:
    """Return the target week-end for a publish run anchored on the observation date.

    Mid-week observations still target the current market week-end. Observations that already
    land on that week's final session roll forward to the following market week-end, which is
    the behavior required for Friday/holiday-close weekly retrains and Saturday rollover runs.
    """
    last_day = _coerce_date(last_observation)
    current_week_end = market_week_end(last_day, exchange=exchange)
    if last_day < current_week_end:
        return current_week_end
    return market_week_end(last_day + timedelta(days=7), exchange=exchange)


def market_week_context(
    anchor: date | datetime | pd.Timestamp | str | None = None,
    exchange: str = DEFAULT_EXCHANGE,
    timezone_name: str = MARKET_TIMEZONE,
) -> dict[str, Any]:
    """Return exchange-calendar and live market-clock context for dashboard and model payloads."""
    anchor_utc = _utc_now(anchor, timezone_name=timezone_name)
    market_now = anchor_utc.astimezone(ZoneInfo(timezone_name))
    market_date = market_now.date()
    week_start, weekday_end = week_window(market_date)
    week_sessions = _market_schedule(week_start, weekday_end, exchange=exchange)
    week_end = week_sessions[-1] if week_sessions else weekday_end
    session_set = set(week_sessions)
    holiday_names = _regular_holidays_between(week_start, weekday_end, exchange=exchange)

    today_details = _market_schedule_details(
        market_date,
        market_date,
        exchange=exchange,
        timezone_name=timezone_name,
    )
    today_session = today_details[0] if today_details else None
    is_market_session = today_session is not None
    is_market_open_now = False
    if today_session is not None:
        is_market_open_now = today_session["market_open"] <= anchor_utc < today_session["market_close"]

    future_sessions = _market_schedule(market_date + timedelta(days=1), market_date + timedelta(days=45), exchange)
    latest_session = latest_market_session_on_or_before(market_date, exchange=exchange)

    closures = []
    for offset in range(5):
        day = week_start + timedelta(days=offset)
        if day in session_set:
            continue
        reason = holiday_names.get(day, "Exchange closed")
        closures.append(
            {
                "date": day.isoformat(),
                "name": reason,
                "status": "closed",
                "observed": "observed" in reason.lower() or reason != "Exchange closed",
            }
        )

    return {
        "exchange": exchange,
        "timezone": timezone_name,
        "server_time_utc": _iso_datetime(anchor_utc),
        "market_time": _iso_datetime(anchor_utc, timezone_name=timezone_name),
        "market_date": market_date.isoformat(),
        "is_market_session": is_market_session,
        "is_market_open_now": is_market_open_now,
        "today_open": (
            _iso_datetime(today_session["market_open"], timezone_name=timezone_name)
            if today_session is not None
            else None
        ),
        "today_close": (
            _iso_datetime(today_session["market_close"], timezone_name=timezone_name)
            if today_session is not None
            else None
        ),
        "current_week_start_date": week_start.isoformat(),
        "current_week_end_date": week_end.isoformat(),
        "calendar_week_end_date": weekday_end.isoformat(),
        "week_sessions": [session.isoformat() for session in week_sessions],
        "week_closures": closures,
        "latest_market_session_date": latest_session.isoformat(),
        "next_market_session_date": future_sessions[0].isoformat() if future_sessions else None,
        "calendar_source": _calendar_source(exchange),
    }
