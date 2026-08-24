"""Registry of systems the eval harness can score."""
from __future__ import annotations

from .apollo_explain import ApolloExplainTarget
from .base import EvalTarget, TargetResponse
from .cerebro_news import CerebroNewsTarget
from .supabase_docs import SupabaseDocsTarget

_TARGETS = {
    t.NAME: t for t in (SupabaseDocsTarget, CerebroNewsTarget, ApolloExplainTarget)
}

TARGET_NAMES = sorted(_TARGETS)


def get_target(name: str) -> EvalTarget:
    try:
        return _TARGETS[name]()
    except KeyError:
        raise SystemExit(
            f"Unknown target {name!r}. Available: {', '.join(TARGET_NAMES)}"
        ) from None


__all__ = ["EvalTarget", "TargetResponse", "TARGET_NAMES", "get_target"]
