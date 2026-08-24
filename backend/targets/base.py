"""
targets/base.py
One interface for every system the harness can score.

The harness started as a Supabase-docs RAG evaluator with answer_query() wired
directly into run_eval. Scoring CEREBRO and Apollo-M meant either forking the
runner per system or giving it a seam -- this is the seam.

A target supplies two things:
  answer()  - run the system under test on one query
  RUBRIC    - what the two stored scores MEAN for this system

The eval_results columns stay retrieval_relevance / answer_accuracy for every
target (no per-target schema), but each target redefines them. For the docs RAG
they mean "did retrieval find the right chunks" and "is the answer factual". For
CEREBRO they mean "is the score grounded in real retrieved evidence" and "is the
verdict right". Same table, same trend chart, honest semantics per system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TargetResponse:
    """What every system under test returns, normalised."""
    answer: str
    latency_ms: int
    # Only the pgvector RAG has chunk UUIDs; others leave this empty.
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    # Text the judge should see as the system's supporting context.
    context: list[str] = field(default_factory=list)
    # Anything worth auditing later (source URLs, raw metrics) -> evidence jsonb.
    evidence: dict[str, Any] = field(default_factory=dict)


class EvalTarget(Protocol):
    NAME: str
    RUBRIC: str

    def answer(self, query: str, expected: str, k: int) -> TargetResponse: ...
