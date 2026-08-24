"""
Target: Apollo-M's LLM explanation layer (llm/explain.py -> explain_community).

Apollo-M's governing rule is that deterministic models produce every number and
the LLM only narrates them -- explain.py's own system prompt says "never change
or invent numbers, only interpret them". That is a testable invariant, so this
target checks it two ways:

  * a deterministic scan (_unverified_numbers) that extracts every number from
    the narration and flags any that is not in the input metrics. No model
    needed, runs in microseconds, and cannot itself hallucinate.
  * the LLM judge, which weighs interpretation quality.

The cheap check runs first and its result is handed to the judge as evidence.
A number the pipeline never computed appearing in a moderator-facing briefing is
the exact failure this layer is designed to prevent.

Queries for this target are JSON metrics objects rather than questions, e.g.
  {"subreddit": "r/politics", "chi": 43.2, "toxicity": 0.79, ...}
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

from .base import TargetResponse

APOLLO_M_PATH = os.environ.get(
    "APOLLO_M_PATH", r"C:\cerebro_repo (apollo int)\apollo-m"
)

# Numbers that are structural to the prompt/answer rather than claims about the
# data (the horizon is literally "5-day", CHI is defined on a 0-100 scale).
_STRUCTURAL = {0.0, 1.0, 5.0, 100.0}

# The lookbehind matters: a naive -?\d+ reads the hyphen in "0-1 scale" or
# "CHI 43-67" as a minus sign and invents a negative number that is in no
# metrics dict, so every stated range gets flagged as a hallucination.
_NUM_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


def _numbers_in(text: str) -> list[float]:
    out = []
    for m in _NUM_RE.findall(text):
        try:
            out.append(float(m))
        except ValueError:
            pass
    return out


def _is_rounding_of(n: float, given: set[float]) -> bool:
    """True if n is one of the given values, rounded to some precision.

    Defined as actual rounding rather than a tolerance band. A flat tolerance
    wide enough to accept 0.79 -> 0.8 is also wide enough to accept a fabricated
    0.81 as if it were 0.79, which silently defeats the whole check.
    """
    for g in given:
        if abs(n - g) < 1e-9:
            return True
        if any(abs(round(g, d) - n) < 1e-9 for d in range(5)):
            return True
    return False


def _unverified_numbers(narration: str, metrics: dict) -> list[dict]:
    """Numbers asserted in the narration that are not present in the input.

    This is a SCREEN, not a verdict. A regex cannot tell a fabricated metric
    ("toxicity is 0.91") from a legitimate non-metric figure ("act within 24
    hours"), so every hit is returned WITH the surrounding text and handed to
    the judge, which decides. Reporting a bare number with no context would be
    unactionable and would make false positives indistinguishable from real
    hallucinations.
    """
    given = set()
    for v in metrics.values():
        if isinstance(v, (int, float)):
            given.add(round(float(v), 4))
    for v in _numbers_in(json.dumps(metrics)):
        given.add(round(v, 4))

    flagged = []
    for m in _NUM_RE.finditer(narration):
        try:
            n = float(m.group())
        except ValueError:
            continue
        r = round(n, 4)
        if r in _STRUCTURAL:
            continue
        if _is_rounding_of(r, given):
            continue
        start, end = max(0, m.start() - 45), min(len(narration), m.end() + 45)
        snippet = narration[start:end].replace("\n", " ").strip()
        flagged.append({"value": n, "context": f"...{snippet}..."})
    return flagged


class ApolloExplainTarget:
    NAME = "apollo_explain"
    RUBRIC = """1. retrieval_relevance: NUMERIC FIDELITY. Apollo-M's rule is that the LLM narrates only the numbers it was given and never invents or alters one. You are shown `unverified_numbers` -- every figure in the briefing that does not appear in the input metrics, each with the text around it. That list is a SCREEN, not a verdict: it is produced by a regex and cannot tell a fabricated metric from a legitimate non-metric figure.
   Judge each entry by its context. A number presenting itself as measured data about this community (a toxicity, CHI, polarization, churn, echo-chamber or forecast value the pipeline never produced) is a real violation -- score 0.0. A number that is plainly not a data claim (a timeframe like "within 48-72 hours", an ordinal, a scale bound) is a false positive: ignore it.
   Score 1.0 when every figure presented as data is faithful to the input, even if the screen flagged non-metric numbers. Score 0.0 when the briefing asserts a metric value the pipeline never computed.
2. answer_accuracy: BRIEFING QUALITY. Does it correctly state the community's health, identify the driving factor, read the forecast, and recommend a proportionate moderation action, matching the expected assessment?"""

    def __init__(self) -> None:
        if APOLLO_M_PATH not in sys.path:
            sys.path.insert(0, APOLLO_M_PATH)

    def answer(self, query: str, expected: str, k: int) -> TargetResponse:
        metrics = json.loads(query)
        from llm.explain import explain_community  # noqa: PLC0415 - needs sys.path set

        start = time.time()
        narration = explain_community(metrics)
        latency_ms = int((time.time() - start) * 1000)

        unverified = _unverified_numbers(narration, metrics)
        return TargetResponse(
            answer=narration,
            latency_ms=latency_ms,
            context=[f"input metric {key} = {val}" for key, val in metrics.items()],
            evidence={
                "input_metrics": metrics,
                "unverified_numbers": unverified,
                "numeric_fidelity_ok": not unverified,
                "used_template_fallback": "[template fallback" in narration,
            },
        )
