"""YouTube Analytics API integration (OAuth2, read-only).

Fetches per-video retention, watch time and subscriber metrics that the plain
Data API cannot provide. Requires the refresh token to have been granted
``yt-analytics.readonly`` (re-run ``ai-shorts-factory auth`` once). All
functions fail soft: when the scope is missing or the API errors, they return
empty data so the rest of the pipeline keeps working on public stats alone.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _to_int(v: Any) -> int | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return int(f)


def _to_float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f

# Per-video metrics pulled from the Analytics API.
_METRICS = (
    "views,engagedViews,likes,comments,shares,estimatedMinutesWatched,"
    "averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost"
)
_START_DATE = "2020-01-01"
_CHUNK = 200  # video filter limit safety margin


def _metrics_from_data(data: dict[str, Any]) -> dict[str, int | float]:
    """Convert one Analytics API row into the optimizer's metric names."""
    metrics: dict[str, int | float | None] = {
        "views": _to_int(data.get("views")),
        "engaged_views": _to_int(data.get("engagedViews")),
        "likes": _to_int(data.get("likes")),
        "comments": _to_int(data.get("comments")),
        "shares": _to_int(data.get("shares")),
        "watch_minutes": _to_float(data.get("estimatedMinutesWatched")),
        "avg_view_duration": _to_float(data.get("averageViewDuration")),
        "retention_pct": _to_float(data.get("averageViewPercentage")),
        "subs_gained": _to_int(data.get("subscribersGained")),
        "subs_lost": _to_int(data.get("subscribersLost")),
    }
    result = {k: v for k, v in metrics.items() if v is not None}

    gained = result.get("subs_gained")
    lost = result.get("subs_lost")
    if gained is not None or lost is not None:
        result["net_subscribers"] = int(gained or 0) - int(lost or 0)

    views = result.get("views")
    engaged = result.get("engaged_views")
    if views and engaged is not None:
        # Since March 2025, a Shorts view is a start/replay while engagedViews
        # counts playbacks that continue past the initial seconds. This is an
        # early-exit proxy, not Studio's "viewed vs. swiped away" metric.
        engaged_rate = min(1.0, max(0.0, float(engaged) / float(views)))
        result["early_exit_pct"] = round(100.0 * (1.0 - engaged_rate), 2)

    return result


def fetch_video_analytics(
    video_ids: list[str],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Return {video_id: metrics} from the YouTube Analytics API.

    ``start_date`` and ``end_date`` are inclusive ISO dates. Omitting them
    returns lifetime-to-date statistics. Metrics include views, engaged views,
    engagement actions, watch time, retention and subscriber movement.
    """
    if not video_ids:
        return {}
    try:
        from googleapiclient.discovery import build

        from .upload import ALL_SCOPES, _load_credentials

        creds = _load_credentials(ALL_SCOPES)
        analytics = build("youtubeAnalytics", "v2", credentials=creds)
    except Exception as exc:
        logger.warning(
            "YouTube Analytics unavailable (%s). Re-run 'ai-shorts-factory auth' "
            "to grant the yt-analytics.readonly scope.",
            exc,
        )
        return {}

    query_start = start_date or _START_DATE
    query_end = end_date or dt.date.today().isoformat()
    results: dict[str, dict[str, Any]] = {}
    for i in range(0, len(video_ids), _CHUNK):
        chunk = video_ids[i : i + _CHUNK]
        try:
            response = (
                analytics.reports()
                .query(
                    ids="channel==MINE",
                    startDate=query_start,
                    endDate=query_end,
                    metrics=_METRICS,
                    dimensions="video",
                    filters="video==" + ",".join(chunk),
                    maxResults=len(chunk),
                )
                .execute()
            )
        except Exception as exc:
            logger.warning("Analytics query failed: %s", exc)
            return results
        headers = [h["name"] for h in response.get("columnHeaders", [])]
        for row in response.get("rows", []) or []:
            data = dict(zip(headers, row))
            vid = str(data.get("video", ""))
            if not vid:
                continue
            # Drop metrics the API has not processed yet (None/NaN) instead of
            # storing bogus zeros; the rest of the pipeline treats missing keys
            # gracefully.
            results[vid] = _metrics_from_data(data)
    logger.info(
        "Fetched Analytics metrics for %d/%d videos (%s to %s).",
        len(results),
        len(video_ids),
        query_start,
        query_end,
    )
    return results
