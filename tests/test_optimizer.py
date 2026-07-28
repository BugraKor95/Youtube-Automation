from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from ai_shorts_factory import optimizer


def _window(
    engaged_views: int,
    *,
    views: int | None = None,
    retention: float = 85.0,
    early_exit: float = 20.0,
    net_subscribers: int = 0,
) -> dict[str, int | float | str]:
    return {
        "views": views if views is not None else engaged_views,
        "engaged_views": engaged_views,
        "retention_pct": retention,
        "early_exit_pct": early_exit,
        "net_subscribers": net_subscribers,
        "start_date": "2026-01-01",
        "end_date": "2026-01-07",
        "window_basis": "calendar_day",
    }


def _entry(
    topic: str,
    category: str,
    engaged_views: int,
    *,
    retention: float = 85.0,
    early_exit: float = 20.0,
    uploaded_at: str = "2026-01-01T10:00:00",
    lifetime_views: int = 0,
) -> dict[str, object]:
    return {
        "topic": topic,
        "category": category,
        "uploaded_at": uploaded_at,
        "views": lifetime_views,
        "performance_windows": {
            "7d": _window(
                engaged_views,
                retention=retention,
                early_exit=early_exit,
            )
        },
    }


class OptimizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_file = optimizer.PERFORMANCE_FILE
        optimizer.PERFORMANCE_FILE = Path(self.temp_dir.name) / "performance.json"

    def tearDown(self) -> None:
        optimizer.PERFORMANCE_FILE = self.original_file
        self.temp_dir.cleanup()

    def test_captures_comparable_performance_windows(self) -> None:
        entries = [
            {
                "topic": "Ready",
                "video_id": "video-1",
                "uploaded_at": "2026-01-01T10:00:00",
            },
            {
                "topic": "Too new",
                "video_id": "video-2",
                "uploaded_at": "2026-01-19T10:00:00",
            },
        ]
        calls: list[tuple[tuple[str, ...], str, str]] = []

        def fake_fetcher(
            video_ids: list[str], *, start_date: str, end_date: str
        ) -> dict[str, dict[str, int]]:
            calls.append((tuple(video_ids), start_date, end_date))
            return {
                video_id: {"views": 2000, "engaged_views": 1500}
                for video_id in video_ids
            }

        changed = optimizer._refresh_performance_windows(
            entries,
            fake_fetcher,
            now=dt.datetime(2026, 1, 20, 12, 0, 0),
        )

        self.assertTrue(changed)
        self.assertEqual(
            set(entries[0]["performance_windows"]),
            {"24h", "72h", "7d"},
        )
        self.assertNotIn("performance_windows", entries[1])
        self.assertEqual(len(calls), 3)
        self.assertEqual(
            entries[0]["performance_windows"]["7d"]["window_basis"],
            "calendar_day",
        )

    def test_category_weights_use_medians_and_minimum_samples(self) -> None:
        entries = [
            *[_entry(f"A{i}", "space", 2000) for i in range(3)],
            *[_entry(f"B{i}", "physics", 1000) for i in range(3)],
            _entry("Outlier", "scale", 1_000_000),
        ]
        optimizer._save(entries)

        weights = optimizer.category_weights()

        self.assertGreater(weights["space"], 1.0)
        self.assertLess(weights["physics"], 1.0)
        self.assertNotIn("scale", weights)

    def test_winner_uses_seven_day_window_not_lifetime_views(self) -> None:
        optimizer._save(
            [
                _entry(
                    "Old lifetime winner",
                    "space",
                    1200,
                    lifetime_views=1_000_000,
                ),
                _entry(
                    "True seven day winner",
                    "physics",
                    5000,
                    lifetime_views=10_000,
                ),
            ]
        )

        winner = optimizer.winning_video()

        self.assertIsNotNone(winner)
        self.assertEqual(winner["topic"], "True seven day winner")
        self.assertEqual(winner["performance_window"], "7d")

    def test_feedback_uses_recent_cohort_median(self) -> None:
        entries = [
            _entry(
                f"Video {index}",
                "space",
                2000,
                retention=70.0,
                uploaded_at=f"2026-01-{index + 1:02d}T10:00:00",
            )
            for index in range(5)
        ]
        optimizer._save(entries)

        feedback = optimizer.retention_feedback()

        self.assertIn("median retention below 80%", feedback)

    def test_one_bad_video_does_not_trigger_feedback(self) -> None:
        entries = [
            _entry(
                f"Video {index}",
                "space",
                2000,
                retention=40.0 if index == 4 else 95.0,
                uploaded_at=f"2026-01-{index + 1:02d}T10:00:00",
            )
            for index in range(5)
        ]
        optimizer._save(entries)

        self.assertEqual(optimizer.retention_feedback(), "")

    def test_high_cohort_early_exit_triggers_hook_feedback(self) -> None:
        entries = [
            _entry(
                f"Video {index}",
                "space",
                2000,
                retention=90.0,
                early_exit=60.0,
                uploaded_at=f"2026-01-{index + 1:02d}T10:00:00",
            )
            for index in range(5)
        ]
        optimizer._save(entries)

        feedback = optimizer.retention_feedback()

        self.assertIn("lost over half of playbacks", feedback)


if __name__ == "__main__":
    unittest.main()
