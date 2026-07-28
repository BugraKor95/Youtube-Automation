"""Self-improvement loop: track published videos, learn winning patterns.

Every generated/uploaded Short is recorded in ``output/performance.json``
together with its content *category* (e.g. attraction, dark-psychology).
``refresh_stats`` pulls public view/like/comment counts via the YouTube Data
API (needs an ordinary API key — no OAuth scope changes) and computes
per-category performance weights. Topic generation then samples categories
proportionally to those weights, so the system automatically doubles down on
what performs (Phase 8) and flags high-view Shorts as long-form candidates
(Phase 9).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import statistics
from collections.abc import Callable
from typing import Any

from .config import OUTPUT_DIR, settings

logger = logging.getLogger(__name__)

PERFORMANCE_FILE = OUTPUT_DIR / "performance.json"

# YouTube Analytics data lags 24-72h behind real time.
STATS_MATURITY_DAYS = 3

# Comparable performance windows. The API exposes daily rather than hourly
# historical buckets, so 24h/72h are calendar-day approximations anchored to
# the upload date. Each window is fetched only after the normal Analytics lag.
PERFORMANCE_WINDOWS = (("24h", 1), ("72h", 3), ("7d", 7))
LEARNING_WINDOW = "7d"
MIN_LEARNING_ENGAGED_VIEWS = 100
MIN_LEARNING_SAMPLE_SIZE = 5
MIN_CATEGORY_SAMPLE_SIZE = 3
FEEDBACK_COHORT_SIZE = 5

# View milestones that qualify a Short topic for long-form expansion.
LONG_FORM_TIERS = [(10000, "10 minute video"), (5000, "8 minute video"), (1000, "5 minute video")]

# The two daily publish slots (see .github/workflows/shorts.yml). Each slot has
# several redundant cron triggers so a Short still goes out even when GitHub
# delays or silently drops a scheduled event. All morning crons fire before this
# UTC hour and all evening crons after it, so the boundary cleanly maps a run to
# its slot and the dedup guard publishes at most once per slot per day.
SLOT_BOUNDARY_HOUR_UTC = 14


def _slot_of(when: dt.datetime) -> str:
    """Return the publish slot ("morning"/"evening") a datetime falls in."""
    return "morning" if when.hour < SLOT_BOUNDARY_HOUR_UTC else "evening"


def last_upload_time() -> dt.datetime | None:
    """Most recent recorded upload time, or None if nothing uploaded yet."""
    latest: dt.datetime | None = None
    for entry in _load():
        stamp = entry.get("uploaded_at")
        if not stamp:
            continue
        try:
            when = dt.datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            continue
        if latest is None or when > latest:
            latest = when
    return latest


def should_publish_now(now: dt.datetime | None = None) -> bool:
    """Whether a Short should be published for the current slot.

    Returns False when a Short was already uploaded in the same slot today, so
    that the redundant cron triggers (backups against dropped/delayed schedules)
    don't publish a duplicate. Fails open (True) when history is missing so a
    genuine outage never silently stops publishing.
    """
    now = now or dt.datetime.now()
    last = last_upload_time()
    if last is None:
        return True
    return not (last.date() == now.date() and _slot_of(last) == _slot_of(now))


def _load() -> list[dict[str, Any]]:
    if not PERFORMANCE_FILE.exists():
        return []
    try:
        return json.loads(PERFORMANCE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict[str, Any]]) -> None:
    PERFORMANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PERFORMANCE_FILE.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def record_generation(topic: str, category: str, fmt: str) -> None:
    """Record a newly generated topic so it can later be matched to a video id."""
    entries = _load()
    entries.append(
        {
            "topic": topic,
            "category": category,
            "format": fmt,
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
    )
    _save(entries)


def record_upload(topic: str, video_id: str) -> None:
    """Attach the uploaded video id + upload time to the latest entry for *topic*."""
    now = dt.datetime.now()
    entries = _load()
    for entry in reversed(entries):
        if entry.get("topic") == topic and not entry.get("video_id"):
            entry["video_id"] = video_id
            entry["uploaded_at"] = now.isoformat(timespec="seconds")
            entry["upload_hour"] = now.hour
            break
    else:
        entries.append(
            {
                "topic": topic,
                "video_id": video_id,
                "uploaded_at": now.isoformat(timespec="seconds"),
                "upload_hour": now.hour,
                "created_at": now.isoformat(timespec="seconds"),
            }
        )
    _save(entries)


def record_detail(topic: str, **fields: Any) -> None:
    """Attach extra details (hook, duration_seconds, ...) to the latest entry."""
    entries = _load()
    for entry in reversed(entries):
        if entry.get("topic") == topic:
            entry.update({k: v for k, v in fields.items() if v is not None})
            _save(entries)
            return


def _parse_uploaded_at(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        uploaded = dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if uploaded.tzinfo is not None:
        uploaded = uploaded.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return uploaded


def _refresh_performance_windows(
    entries: list[dict[str, Any]],
    fetcher: Callable[..., dict[str, dict[str, Any]]],
    *,
    now: dt.datetime | None = None,
) -> bool:
    """Fill missing 24h/72h/7d calendar windows after Analytics has matured."""
    now = now or dt.datetime.now()
    pending: dict[
        tuple[str, str], list[tuple[dict[str, Any], str, str]]
    ] = {}

    for entry in entries:
        video_id = str(entry.get("video_id", ""))
        uploaded = _parse_uploaded_at(entry.get("uploaded_at"))
        if not video_id or uploaded is None:
            continue
        windows = entry.get("performance_windows")
        if not isinstance(windows, dict):
            windows = {}
        for label, days in PERFORMANCE_WINDOWS:
            if label in windows:
                continue
            start = uploaded.date()
            end = start + dt.timedelta(days=days - 1)
            ready_on = end + dt.timedelta(days=STATS_MATURITY_DAYS)
            if now.date() < ready_on:
                continue
            key = (start.isoformat(), end.isoformat())
            pending.setdefault(key, []).append((entry, label, video_id))

    changed = False
    captured_at = now.isoformat(timespec="seconds")
    for (start_date, end_date), targets in pending.items():
        video_ids = list(dict.fromkeys(video_id for _, _, video_id in targets))
        metrics_by_video = fetcher(
            video_ids, start_date=start_date, end_date=end_date
        )
        for entry, label, video_id in targets:
            metrics = metrics_by_video.get(video_id)
            if not metrics:
                continue
            snapshot = dict(metrics)
            snapshot.update(
                {
                    "start_date": start_date,
                    "end_date": end_date,
                    "captured_at": captured_at,
                    "window_basis": "calendar_day",
                }
            )
            windows = entry.get("performance_windows")
            if not isinstance(windows, dict):
                windows = {}
                entry["performance_windows"] = windows
            windows[label] = snapshot
            changed = True
    return changed


def refresh_stats() -> list[dict[str, Any]]:
    """Refresh statistics for all recorded videos.

    Prefers the YouTube Analytics API (retention, watch time, subscribers
    gained — needs the yt-analytics.readonly OAuth scope); falls back to
    public Data API stats via YOUTUBE_API_KEY for views/likes/comments.
    """
    entries = _load()
    ids = [e["video_id"] for e in entries if e.get("video_id")]
    if not ids:
        return entries

    refreshed_at = dt.datetime.now()
    refreshed_at_iso = refreshed_at.isoformat(timespec="seconds")

    from .analytics import fetch_video_analytics

    analytics = fetch_video_analytics(ids)
    if analytics:
        for entry in entries:
            m = analytics.get(entry.get("video_id", ""))
            if not m:
                continue
            entry.pop("swipe_away_pct", None)
            entry.update(m)
            entry["stats_updated_at"] = refreshed_at_iso
        _refresh_performance_windows(
            entries, fetch_video_analytics, now=refreshed_at
        )
        _save(entries)
        return entries

    if not settings.youtube_api_key:
        logger.info("No Analytics access and no YOUTUBE_API_KEY; skipping refresh.")
        return entries

    from googleapiclient.discovery import build

    stats: dict[str, dict[str, Any]] = {}
    try:
        youtube = build("youtube", "v3", developerKey=settings.youtube_api_key)
        for i in range(0, len(ids), 50):
            response = (
                youtube.videos()
                .list(part="statistics", id=",".join(ids[i : i + 50]))
                .execute()
            )
            for item in response.get("items", []):
                stats[item["id"]] = item.get("statistics", {})
    except Exception as exc:
        logger.warning("Data API stats refresh failed: %s", exc)
        return entries

    for entry in entries:
        s = stats.get(entry.get("video_id", ""))
        if not s:
            continue
        for field_name, api_key in (
            ("views", "viewCount"),
            ("likes", "likeCount"),
            ("comments", "commentCount"),
        ):
            if _valid_number(s.get(api_key)):
                entry[field_name] = int(float(s[api_key]))
        entry["stats_updated_at"] = refreshed_at_iso
    _save(entries)
    return entries


def _window_metrics(
    entry: dict[str, Any], window: str = LEARNING_WINDOW
) -> dict[str, Any]:
    windows = entry.get("performance_windows")
    if not isinstance(windows, dict):
        return {}
    metrics = windows.get(window)
    return metrics if isinstance(metrics, dict) else {}


def _signal_views(entry: dict[str, Any]) -> float:
    """Return monetization-relevant engaged views, or views as a fallback."""
    if _valid_number(entry.get("engaged_views")):
        return float(entry["engaged_views"])
    if _valid_number(entry.get("views")):
        return float(entry["views"])
    return 0.0


def _entry_score(e: dict[str, Any]) -> float:
    """Composite performance score used for automatic strategy adjustment.

    Seven-day engaged views are weighted by retention and net subscriber
    conversion. Raw lifetime values are used only by callers that explicitly
    pass an entry without a performance window.
    """
    metrics = _window_metrics(e) or e
    views = _signal_views(metrics)
    score = views
    retention = metrics.get("retention_pct")
    if _valid_number(retention):
        # 80% retention doubles a view's value; 40% keeps it at 1x; floor 0.25x.
        score *= max(0.25, float(retention) / 40.0)
    subs = metrics.get("net_subscribers", metrics.get("subs_gained"))
    if _valid_number(subs) and views > 0:
        # Reward subscriber conversion, but do not let one noisy result dominate.
        score *= min(2.0, max(0.5, 1.0 + (float(subs) / views) * 100.0))
    return score


def category_weights() -> dict[str, float]:
    """Return {category: weight} learned from past performance.

    Weight = category's median seven-day composite score relative to the
    overall median. Categories need at least three qualified videos and the
    result is clamped to [0.5, 2.0] to preserve exploration.
    """
    entries = [e for e in _with_stats() if e.get("category")]
    if len(entries) < MIN_LEARNING_SAMPLE_SIZE:
        return {}
    by_cat: dict[str, list[float]] = {}
    for e in entries:
        by_cat.setdefault(e["category"], []).append(_entry_score(e))
    by_cat = {
        category: scores
        for category, scores in by_cat.items()
        if len(scores) >= MIN_CATEGORY_SAMPLE_SIZE
    }
    all_scores = [score for scores in by_cat.values() for score in scores]
    if not all_scores:
        return {}
    overall = statistics.median(all_scores)
    if overall <= 0:
        return {}
    weights: dict[str, float] = {}
    for cat, scores in by_cat.items():
        category_median = statistics.median(scores)
        weights[cat] = min(2.0, max(0.5, category_median / overall))
    return weights


# Injected into the topic/hook/script prompts when the latest measurable video
# failed to hold the audience.
RETENTION_FEEDBACK_THRESHOLD = 80.0
EARLY_EXIT_THRESHOLD = 50.0
_URGENT_HOOK_FEEDBACK = (
    "[URGENT_HOOK_OPTIMIZATION] The recent five-video cohort lost over half of "
    "playbacks in the initial seconds. Make the hook 2x more dramatic: a "
    "shocking, high-stakes statement in the first 3 words, and the single most "
    "jaw-dropping visual of the whole video in the very first frame."
)
_RETENTION_FEEDBACK = (
    "[OPTIMIZATION] The recent five-video cohort had median retention below "
    "80%. Make the opening hook shorter and more dramatic, and increase the "
    "visual pace: every scene's image must change subject, scale or palette "
    "more aggressively."
)


def retention_feedback() -> str:
    """Return an LLM prompt addendum when the latest measured video underperformed.

    Uses the most recent five qualified seven-day windows. A cohort median
    prevents one noisy upload from rewriting the next video's prompt.
    """
    entries = sorted(
        [
            e
            for e in _with_stats()
            if _valid_number(e.get("retention_pct"))
        ],
        key=lambda e: str(e.get("uploaded_at", "")),
        reverse=True,
    )[:FEEDBACK_COHORT_SIZE]
    if len(entries) < FEEDBACK_COHORT_SIZE:
        return ""
    early_exits = [
        float(e["early_exit_pct"])
        for e in entries
        if _valid_number(e.get("early_exit_pct"))
    ]
    if (
        len(early_exits) == FEEDBACK_COHORT_SIZE
        and statistics.median(early_exits) > EARLY_EXIT_THRESHOLD
    ):
        return _URGENT_HOOK_FEEDBACK
    retention = statistics.median(float(e["retention_pct"]) for e in entries)
    if retention < RETENTION_FEEDBACK_THRESHOLD:
        return _RETENTION_FEEDBACK
    return ""


def winning_video() -> dict[str, Any] | None:
    """The mature video with the best retention x views composite score.

    Anchor for idea farming: new concepts are generated strictly within this
    video's sub-niche. Returns None when no mature video has full stats.
    """
    entries = [
        e for e in _with_stats() if _valid_number(e.get("retention_pct"))
    ]
    if not entries:
        return None
    return max(entries, key=_entry_score)


def winning_patterns() -> list[str]:
    """Human-readable report of category performance vs. the overall average."""
    entries = [e for e in _with_stats() if e.get("category")]
    if len(entries) < MIN_LEARNING_SAMPLE_SIZE:
        return [
            "Not enough qualified 7-day data yet "
            f"(need {MIN_LEARNING_SAMPLE_SIZE} videos with "
            f"{MIN_LEARNING_ENGAGED_VIEWS}+ engaged views)."
        ]
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        by_cat.setdefault(e["category"], []).append(e)
    overall = statistics.median(_entry_score(e) for e in entries)
    lines = []
    for cat, items in sorted(
        by_cat.items(),
        key=lambda kv: -statistics.median(_entry_score(e) for e in kv[1]),
    ):
        median_score = statistics.median(_entry_score(e) for e in items)
        median_views = statistics.median(_signal_views(e) for e in items)
        delta = (median_score / overall - 1) * 100 if overall else 0.0
        lines.append(
            f"{cat}: median {median_views:.0f} engaged views at 7d, "
            f"score {delta:+.0f}% vs channel median (n={len(items)})"
        )
    return lines


def performance_window_status() -> list[str]:
    """Summarize comparable-window coverage for the optimize command."""
    entries = [entry for entry in _load() if entry.get("video_id")]
    if not entries:
        return ["No uploaded videos are tracked yet."]
    lines = [f"Tracked uploads: {len(entries)}"]
    for label, _ in PERFORMANCE_WINDOWS:
        captured = sum(bool(_window_metrics(entry, label)) for entry in entries)
        lines.append(f"{label} windows captured: {captured}/{len(entries)}")
    qualified = len(_with_stats())
    lines.append(
        f"Qualified for learning: {qualified} "
        f"({LEARNING_WINDOW}, {MIN_LEARNING_ENGAGED_VIEWS}+ engaged views)"
    )
    return lines


def _valid_number(v: Any) -> bool:
    """True for a real, finite number (rejects None, NaN, inf, non-numeric)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))


def _with_stats(*, require_signal: bool = True) -> list[dict[str, Any]]:
    """Return entries enriched with comparable seven-day performance metrics."""
    entries: list[dict[str, Any]] = []
    for raw in _load():
        metrics = _window_metrics(raw)
        if not (
            _valid_number(metrics.get("engaged_views"))
            or _valid_number(metrics.get("views"))
        ):
            continue
        enriched = dict(raw)
        enriched.update(metrics)
        enriched["performance_window"] = LEARNING_WINDOW
        if require_signal and _signal_views(enriched) < MIN_LEARNING_ENGAGED_VIEWS:
            continue
        entries.append(enriched)
    return entries


def _leaders(key: str, label: str, fmt: str = "{:.1f}") -> list[str]:
    entries = [e for e in _with_stats() if e.get(key) is not None]
    lines = []
    for e in sorted(entries, key=lambda x: -float(x.get(key, 0)))[:5]:
        value = fmt.format(float(e.get(key, 0)))
        lines.append(f"{value} {label}  {e.get('topic', '?')}")
    return lines


def retention_leaders() -> list[str]:
    """Videos ranked by audience retention (averageViewPercentage)."""
    return _leaders("retention_pct", "% retention", "{:.0f}")


def watch_time_leaders() -> list[str]:
    """Videos ranked by watch time in their first seven calendar days."""
    return _leaders("watch_minutes", "min watched at 7d", "{:.0f}")


def subscriber_leaders() -> list[str]:
    """Videos ranked by net subscribers per 1k engaged seven-day views."""
    entries = [
        e
        for e in _with_stats()
        if _valid_number(e.get("net_subscribers", e.get("subs_gained")))
        and _signal_views(e) > 0
    ]

    def conversion(entry: dict[str, Any]) -> float:
        subscribers = float(
            entry.get("net_subscribers", entry.get("subs_gained", 0))
        )
        return subscribers / _signal_views(entry)

    lines = []
    for e in sorted(entries, key=lambda x: -conversion(x))[:5]:
        subscribers = int(e.get("net_subscribers", e.get("subs_gained", 0)))
        rate = conversion(e) * 1000
        lines.append(
            f"{rate:.1f} net subs/1k engaged views "
            f"({subscribers:+d} total)  {e.get('topic', '?')}"
        )
    return lines


def top_topics() -> list[str]:
    """Videos ranked by composite performance score."""
    entries = _with_stats()
    lines = []
    for e in sorted(entries, key=lambda x: -_entry_score(x))[:5]:
        lines.append(
            f"{int(_signal_views(e))} engaged views at 7d  {e.get('topic', '?')}"
        )
    return lines


def top_hooks() -> list[str]:
    """Hooks of the best-performing videos (pattern source for future scripts)."""
    entries = [e for e in _with_stats() if e.get("hook")]
    lines = []
    for e in sorted(entries, key=lambda x: -_entry_score(x))[:5]:
        retention = e.get("retention_pct")
        suffix = f" ({retention:.0f}% retention)" if retention is not None else ""
        lines.append(f'"{e["hook"]}"{suffix}')
    return lines


def best_upload_hours() -> list[str]:
    """Upload hours ranked by median seven-day composite score."""
    entries = [e for e in _with_stats() if e.get("upload_hour") is not None]
    by_hour: dict[int, list[float]] = {}
    for e in entries:
        by_hour.setdefault(int(e["upload_hour"]), []).append(_entry_score(e))
    qualified = {
        hour: scores
        for hour, scores in by_hour.items()
        if len(scores) >= MIN_CATEGORY_SAMPLE_SIZE
    }
    lines = []
    for hour, scores in sorted(
        qualified.items(), key=lambda kv: -statistics.median(kv[1])
    )[:5]:
        lines.append(
            f"{hour:02d}:00 UTC  median score {statistics.median(scores):.0f} "
            f"(n={len(scores)})"
        )
    return lines


_DURATION_BUCKETS = [(0, 20, "<20s"), (20, 26, "20-25s"), (26, 31, "26-30s"), (31, 999, "31s+")]


def best_durations() -> list[str]:
    """Video-length buckets ranked by median seven-day composite score."""
    entries = [e for e in _with_stats() if e.get("duration_seconds")]
    by_bucket: dict[str, list[float]] = {}
    for e in entries:
        d = float(e["duration_seconds"])
        for lo, hi, label in _DURATION_BUCKETS:
            if lo <= d < hi:
                by_bucket.setdefault(label, []).append(_entry_score(e))
                break
    qualified = {
        label: scores
        for label, scores in by_bucket.items()
        if len(scores) >= MIN_CATEGORY_SAMPLE_SIZE
    }
    lines = []
    for label, scores in sorted(
        qualified.items(), key=lambda kv: -statistics.median(kv[1])
    ):
        lines.append(
            f"{label}  median score {statistics.median(scores):.0f} "
            f"(n={len(scores)})"
        )
    return lines


def long_form_candidates() -> list[dict[str, Any]]:
    """Shorts whose seven-day engaged views qualify for long-form expansion."""
    out = []
    for e in _with_stats():
        views = int(_signal_views(e))
        for threshold, target in LONG_FORM_TIERS:
            if views >= threshold:
                out.append(
                    {
                        "topic": e.get("topic"),
                        "video_id": e.get("video_id"),
                        "views": views,
                        "window": LEARNING_WINDOW,
                        "recommended": target,
                    }
                )
                break
    return sorted(out, key=lambda x: -x["views"])
