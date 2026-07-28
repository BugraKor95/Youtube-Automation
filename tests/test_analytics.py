from __future__ import annotations

import unittest

from ai_shorts_factory.analytics import _metrics_from_data


class AnalyticsMetricTests(unittest.TestCase):
    def test_maps_engagement_and_subscriber_metrics(self) -> None:
        metrics = _metrics_from_data(
            {
                "views": "2000",
                "engagedViews": "1500",
                "likes": "120",
                "comments": "14",
                "shares": "25",
                "estimatedMinutesWatched": "840.5",
                "averageViewDuration": "33.6",
                "averageViewPercentage": "91.2",
                "subscribersGained": "12",
                "subscribersLost": "2",
            }
        )

        self.assertEqual(metrics["engaged_views"], 1500)
        self.assertEqual(metrics["shares"], 25)
        self.assertEqual(metrics["net_subscribers"], 10)
        self.assertEqual(metrics["early_exit_pct"], 25.0)
        self.assertNotIn("swipe_away_pct", metrics)

    def test_early_exit_proxy_is_clamped(self) -> None:
        metrics = _metrics_from_data({"views": 100, "engagedViews": 110})

        self.assertEqual(metrics["early_exit_pct"], 0.0)

    def test_missing_values_are_not_written_as_zero(self) -> None:
        metrics = _metrics_from_data(
            {
                "views": None,
                "engagedViews": "nan",
                "subscribersGained": None,
                "subscribersLost": None,
            }
        )

        self.assertNotIn("views", metrics)
        self.assertNotIn("engaged_views", metrics)
        self.assertNotIn("net_subscribers", metrics)


if __name__ == "__main__":
    unittest.main()
