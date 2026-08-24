"""
Target: CEREBRO's misinformation route (POST /v1/analyze/news).

What this eval actually enforces is CEREBRO's own governing contract, stated at
the top of routers/news.py:

    a credibility number is DERIVED FROM retrieved evidence, or it is not
    produced at all.

v1 asked an LLM for a credibilityScore plus a sources[] array in one call with no
retrieval, and the "sources" were invented -- the schema literally called them
"simulated references". So the failure mode worth regression-testing is not "is
the answer nice" but "did it fabricate sources, or state confidence it has no
evidence for". An empty sources[] with a low score is the CORRECT behaviour when
the corpus has nothing relevant, and the rubric says so explicitly.
"""
from __future__ import annotations

import os
import time

import requests

from .base import TargetResponse

BASE_URL = os.environ.get("CEREBRO_API_URL", "https://cerebro-api-nmah.onrender.com")
EMAIL = os.environ.get("CEREBRO_EMAIL", "")
PASSWORD = os.environ.get("CEREBRO_PASSWORD", "")

# Free Render dynos sleep after ~15 min idle; the first call pays a ~50s cold start.
TIMEOUT = int(os.environ.get("CEREBRO_TIMEOUT_S", "120"))


class CerebroNewsTarget:
    NAME = "cerebro_news"
    RUBRIC = """1. retrieval_relevance: EVIDENCE GROUNDING. Every URL in `sources` must be a document the system actually retrieved, and `credibilityScore` must be justified by that evidence. Score 1.0 when the score is well supported by real sources, OR when the corpus genuinely lacks evidence and the system correctly returns few/no sources with a low-confidence verdict. Score 0.0 if sources look fabricated or a confident score is asserted with no supporting evidence.
2. answer_accuracy: VERDICT CORRECTNESS. Does the verdict/credibilityScore match the expected assessment for this input?"""

    def __init__(self) -> None:
        self._token: str | None = None

    def _login(self) -> str:
        if self._token:
            return self._token
        if not EMAIL or not PASSWORD:
            raise RuntimeError(
                "Set CEREBRO_EMAIL and CEREBRO_PASSWORD in .env to evaluate this target."
            )
        r = requests.post(
            f"{BASE_URL}/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token

    def answer(self, query: str, expected: str, k: int) -> TargetResponse:
        token = self._login()
        start = time.time()
        r = requests.post(
            f"{BASE_URL}/v1/analyze/news",
            json={"text": query},
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        latency_ms = int((time.time() - start) * 1000)

        sources = data.get("sources", []) or []
        answer = (
            f"verdict={data.get('verdict')} "
            f"credibilityScore={data.get('credibilityScore')} "
            f"claims_checked={data.get('claims_checked')} "
            f"score_source={data.get('score_source')}\n"
            f"summary: {data.get('summary')}\n"
            f"reasoning: {data.get('reasoning')}"
        )
        return TargetResponse(
            answer=answer,
            latency_ms=latency_ms,
            context=[f"source: {s}" for s in sources] or ["(no sources returned)"],
            evidence={
                "credibilityScore": data.get("credibilityScore"),
                "verdict": data.get("verdict"),
                "sources": sources,
                "claims_checked": data.get("claims_checked"),
                "score_source": data.get("score_source"),
                "model_versions": data.get("model_versions"),
            },
        )
