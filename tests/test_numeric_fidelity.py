"""
Unit tests for the Apollo-M numeric-fidelity screen — pure function, no
network/DB/LLM needed.

Apollo-M's governing rule is that deterministic models produce every number and
the LLM only narrates them. This screen is the cheapest stage that can catch a
violation, so it is the stage that should have the test.

Run with: pytest tests/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from targets.apollo_explain import _unverified_numbers  # noqa: E402

METRICS = {
    "subreddit": "r/politics",
    "chi": 43.2,
    "toxicity": 0.79,
    "polarization": 0.55,
    "alert_level": "CRITICAL",
    "forecast_p50": 0.81,
}


def _values(hits):
    return [h["value"] for h in hits]


def test_faithful_narration_flags_nothing():
    narration = (
        "CHI is 43.2 and the alert is CRITICAL. Toxicity (0.79) is the driver, "
        "with polarization at 0.55. The 5-day forecast median is 0.81."
    )
    assert _unverified_numbers(narration, METRICS) == []


def test_fabricated_metric_is_flagged():
    narration = "Churn reached 0.42 last week, and the echo chamber index is 0.67."
    assert sorted(_values(_unverified_numbers(narration, METRICS))) == [0.42, 0.67]


def test_rounding_is_tolerated():
    """The model saying 43.2 -> 43 or 0.79 -> 0.8 is narration, not fabrication."""
    narration = "CHI is about 43 and toxicity is roughly 0.8."
    assert _unverified_numbers(narration, METRICS) == []


def test_structural_numbers_are_ignored():
    """0-1 scales and the 5-day horizon are prompt structure, not data claims."""
    narration = "Toxicity is on a 0-1 scale and the forecast covers 5 days out of 100."
    assert _unverified_numbers(narration, METRICS) == []


def test_every_hit_carries_context():
    """A bare number is unactionable: the judge needs the surrounding text to
    dismiss a false positive like 'within 24 hours'."""
    narration = "Recommend moderator review within 24 hours."
    hits = _unverified_numbers(narration, METRICS)
    assert len(hits) == 1
    assert hits[0]["value"] == 24.0
    assert "24 hours" in hits[0]["context"]


def test_absent_metric_cannot_be_narrated():
    """The specific failure the missing-forecast eval case exists to catch:
    forecast_p50 was never computed, so any predicted value is invented."""
    metrics_no_forecast = {k: v for k, v in METRICS.items() if k != "forecast_p50"}
    narration = "The 5-day forecast median is 0.81, so expect further decline."
    assert _values(_unverified_numbers(narration, metrics_no_forecast)) == [0.81]
