"""
seed_eval_queries_targets.py
Ground-truth eval sets for the non-Supabase targets: CEREBRO's misinformation
route and Apollo-M's LLM explanation layer.

Each set is written to probe that system's stated architectural contract rather
than to ask it generically nice questions:

  cerebro_news    "a credibility number is DERIVED FROM retrieved evidence, or
                  it is not produced at all" (routers/news.py). So the set
                  includes a claim the corpus refutes, one it supports, and one
                  it knows nothing about -- the last is the important one,
                  because the correct behaviour is an honest low-confidence
                  answer with few sources, NOT a confident fabrication.

  apollo_explain  "never change or invent numbers, only interpret them"
                  (llm/explain.py). The set includes a metrics object with
                  forecast_p50 deliberately absent, because the tempting failure
                  is to narrate a forecast that was never computed.

Usage:
    python seed_eval_queries_targets.py
Requires db/migrations/0002_fix_retrieval_and_multi_target.sql to be applied.
"""
import json

import config  # noqa: F401 - loads the repo-root .env

from db_client import get_supabase_client

CEREBRO_QUERIES = [
    {
        "query": "Scientists confirm that drinking bleach cures all known viral infections.",
        "expected_answer": (
            "Low credibility. The corpus contains an FDA warning that drinking bleach or "
            "Miracle Mineral Solution does not cure disease and is dangerous, which REFUTES "
            "this claim. A correct system detects the contradiction and returns a low "
            "credibilityScore with a False/Refuted verdict. Every source must be a real "
            "retrieved document."
        ),
        "category": "misinformation-refuted",
        "difficulty": "easy",
    },
    {
        "query": "NASA reports that global average surface temperature has risen since the late 19th century.",
        "expected_answer": (
            "High credibility. The corpus contains NASA global-temperature and scientific-"
            "consensus documents that SUPPORT this claim. Expect a high credibilityScore "
            "grounded in those NASA sources."
        ),
        "category": "misinformation-supported",
        "difficulty": "easy",
    },
    {
        "query": "The 2031 Antarctic subglacial rail tunnel was completed ahead of schedule by the Kerguelen Transit Authority.",
        "expected_answer": (
            "Insufficient evidence. Nothing in the corpus addresses this at all. The CORRECT "
            "behaviour is an honest low-confidence verdict with few or no sources -- an empty "
            "sources array is a feature here. Any confident score, or any source presented as "
            "supporting this claim, is a failure."
        ),
        "category": "misinformation-unknown",
        "difficulty": "hard",
    },
    {
        "query": "Ivermectin is an approved and effective treatment for preventing COVID-19.",
        "expected_answer": (
            "Low credibility. The corpus contains the FDA consumer update explaining why "
            "ivermectin should not be used to treat or prevent COVID-19, which refutes the "
            "claim. Expect a low credibilityScore citing that real FDA source."
        ),
        "category": "misinformation-refuted",
        "difficulty": "medium",
    },
]

APOLLO_METRIC_CASES = [
    {
        "metrics": {
            "subreddit": "r/politics", "chi": 43.2, "toxicity": 0.79,
            "polarization": 0.55, "alert_level": "CRITICAL", "forecast_p50": 0.81,
        },
        "expected_answer": (
            "Should state the community is CRITICAL at CHI 43.2, identify toxicity (0.79) as "
            "the dominant driver, read the 5-day forecast of 0.81 as sustained or worsening "
            "rather than a transient spike, and recommend proportionate immediate moderator "
            "action. Must cite ONLY the numbers given -- 43.2, 0.79, 0.55, 0.81."
        ),
        "category": "explain-critical",
        "difficulty": "easy",
    },
    {
        "metrics": {
            "subreddit": "r/Astronomy", "chi": 88.5, "toxicity": 0.11,
            "polarization": 0.09, "alert_level": "LOW", "forecast_p50": 0.12,
        },
        "expected_answer": (
            "Should state the community is healthy (CHI 88.5, alert LOW), note low toxicity "
            "(0.11) and polarization (0.09), read the forecast (0.12) as stable, and recommend "
            "routine monitoring rather than intervention. Must NOT manufacture alarm."
        ),
        "category": "explain-healthy",
        "difficulty": "easy",
    },
    {
        "metrics": {
            "subreddit": "r/worldnews", "chi": 61.0, "toxicity": 0.44,
            "polarization": 0.71, "alert_level": "MEDIUM", "forecast_p50": 0.68,
        },
        "expected_answer": (
            "Should identify POLARIZATION (0.71) rather than toxicity (0.44) as the dominant "
            "factor, and read the forecast (0.68) as a sharp rise from current toxicity 0.44 -- "
            "a proactive warning even though the current alert is only MEDIUM. Recommend "
            "pre-emptive monitoring."
        ),
        "category": "explain-rising",
        "difficulty": "hard",
    },
    {
        "metrics": {
            "subreddit": "r/AskHistorians", "chi": 74.3, "toxicity": 0.28,
            "polarization": 0.31, "alert_level": "LOW",
        },
        "expected_answer": (
            "NO forecast was computed for this community -- forecast_p50 is absent. The system "
            "must say the forecast is unavailable and MUST NOT state any predicted value. "
            "Inventing a forecast number is the specific failure this case tests. Only 74.3, "
            "0.28 and 0.31 may be cited."
        ),
        "category": "explain-missing-forecast",
        "difficulty": "hard",
    },
]


def _rows() -> list[dict]:
    rows = []
    for q in CEREBRO_QUERIES:
        rows.append({**q, "target": "cerebro_news"})
    for case in APOLLO_METRIC_CASES:
        rows.append({
            "query": json.dumps(case["metrics"]),
            "expected_answer": case["expected_answer"],
            "category": case["category"],
            "difficulty": case["difficulty"],
            "target": "apollo_explain",
        })
    return rows


def seed():
    """Insert any queries not already present, per (query, target). Safe to re-run."""
    client = get_supabase_client()
    rows = _rows()

    try:
        stored = client.table("eval_queries").select("query, target").execute().data
    except Exception as exc:
        raise SystemExit(
            "eval_queries.target is missing. Apply "
            "db/migrations/0002_fix_retrieval_and_multi_target.sql in the Supabase "
            f"SQL editor first.\n  ({str(exc)[:140]})"
        ) from None

    existing = {(r["query"], r.get("target")) for r in stored}
    missing = [r for r in rows if (r["query"], r["target"]) not in existing]

    if not missing:
        print(f"Up to date: all {len(rows)} target eval queries already seeded.")
        return

    client.table("eval_queries").insert(missing).execute()
    by_target = {}
    for r in missing:
        by_target[r["target"]] = by_target.get(r["target"], 0) + 1
    print(f"Seeded {len(missing)} new eval queries: " +
          ", ".join(f"{n} {t}" for t, n in sorted(by_target.items())))


if __name__ == "__main__":
    seed()
