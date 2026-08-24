"""
run_eval.py
Runs the eval harness against a pluggable system under test.

    python run_eval.py                                   # supabase_docs (default)
    python run_eval.py --target cerebro_news
    python run_eval.py --target apollo_explain --limit 3
    python run_eval.py --list-targets

Loads that target's eval_queries from Supabase, runs the system, scores the
output with Claude as judge against the TARGET'S OWN rubric, and writes
eval_runs + eval_results back.

Exit codes:
    0  every query was scored (some may legitimately FAIL on quality)
    1  one or more queries could not be scored at all (infrastructure)

The distinction matters: a provider outage previously reported as "0/40 passed",
which is indistinguishable from a total quality regression. An eval harness that
cannot tell those apart is not trustworthy in CI.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

import config  # noqa: F401 - loads the repo-root .env

from anthropic import Anthropic
from db_client import get_supabase_client
from rag_agent import MODEL
from targets import TARGET_NAMES, get_target

EMBED_MODEL = os.environ.get("EMBEDDING_MODEL", "voyage-3-lite")
PASS_THRESHOLD = 0.7

# Abort after this many consecutive infrastructure errors. Grinding through
# every remaining query against a down provider burns quota and tells us
# nothing we did not learn from the first failure.
MAX_CONSECUTIVE_ERRORS = 3

_INFRA_MARKERS = (
    "rate limit", "429", "credit balance", "authentication", "api key",
    "overloaded", "timeout", "connection", "503", "502", "insufficient_quota",
    "max retries exceeded", "nameresolution",
)

_MISSING_COL = ("could not find", "column", "42703", "schema cache")


def _is_missing_column(exc: Exception, col: str) -> bool:
    text = str(exc).lower()
    return col in text and any(m in text for m in _MISSING_COL)


def classify_error(exc: Exception) -> str:
    """'infra' for provider/transport problems, 'data' for everything else."""
    text = str(exc).lower()
    return "infra" if any(m in text for m in _INFRA_MARKERS) else "data"


def get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def load_eval_queries(client, target: str) -> list[dict]:
    try:
        return client.table("eval_queries").select("*").eq("target", target).execute().data
    except Exception as exc:
        if not _is_missing_column(exc, "target"):
            raise
        if target == "supabase_docs":
            print("  note: eval_queries.target missing (migration 0002 not applied);\n"
                  "        treating every stored query as supabase_docs.")
            return client.table("eval_queries").select("*").execute().data
        raise SystemExit(
            f"Target {target!r} needs db/migrations/0002_fix_retrieval_and_multi_target.sql.\n"
            f"Apply it in the Supabase SQL editor, then re-run."
        ) from None


def create_eval_run(client, label: str, target: str) -> str:
    row = {
        "run_label": label,
        "model_used": MODEL,
        "embed_model": EMBED_MODEL,
        "git_commit": get_git_commit(),
        "target": target,
    }
    try:
        return client.table("eval_runs").insert(row).execute().data[0]["id"]
    except Exception as exc:
        if not _is_missing_column(exc, "target"):
            raise
        row.pop("target")
        return client.table("eval_runs").insert(row).execute().data[0]["id"]


def finish_eval_run(client, run_id: str):
    client.table("eval_runs").update({
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }).eq("id", run_id).execute()


def judge_result(query: str, expected: str, response, rubric: str) -> dict:
    """Score one response with Claude, against the target's own rubric."""
    client = Anthropic()
    context_block = "\n".join(f"[{i+1}] {c[:300]}" for i, c in enumerate(response.context))
    evidence_block = json.dumps(response.evidence, indent=2, default=str)[:1500]

    prompt = f"""You are an evaluation judge. Score the system's output on two dimensions, each 0.0-1.0, using EXACTLY these definitions:

{rubric}

Input given to the system:
{query}

Expected assessment:
{expected}

Context / evidence the system used:
{context_block or '(none)'}

Structured evidence returned by the system:
{evidence_block}

System output:
{response.answer}

Respond ONLY with a JSON object like:
{{"retrieval_relevance": 0.8, "answer_accuracy": 0.9, "reasoning": "brief explanation"}}"""

    # max_tokens has to cover reasoning as well as the answer. At 400 the budget
    # was being spent on thinking, so the JSON came back empty or truncated and
    # every judge call died on a decode error.
    r = client.messages.create(
        model=MODEL, max_tokens=2000, messages=[{"role": "user", "content": prompt}]
    )
    # content[0] is not necessarily the answer: with extended thinking enabled the
    # first block is a ThinkingBlock, which has no .text. Select text blocks by
    # type rather than by position, the way rag_agent.answer_query already does.
    text = "".join(b.text for b in r.content if b.type == "text").strip()
    return _parse_scores(text)


def _parse_scores(text: str) -> dict:
    """Pull the score object out of the judge's reply.

    Tolerates markdown fences and any prose the model wraps around the JSON;
    a judge that scored correctly should not be recorded as an error because it
    added a sentence of preamble.
    """
    if not text:
        raise ValueError("judge returned no text (max_tokens likely exhausted by reasoning)")
    for candidate in (text, text.replace("```json", "").replace("```", "").strip()):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"judge reply was not JSON: {text[:160]!r}")


def insert_eval_result(client, run_id, query_id, response, scores):
    accuracy = scores.get("answer_accuracy", 0.0)
    row = {
        "eval_run_id": run_id,
        "eval_query_id": query_id,
        "retrieved_chunk_ids": response.retrieved_chunk_ids,
        "generated_answer": response.answer,
        "retrieval_relevance": scores.get("retrieval_relevance", 0.0),
        "answer_accuracy": accuracy,
        "latency_ms": response.latency_ms,
        "passed": accuracy >= PASS_THRESHOLD,
        "judge_reasoning": scores.get("reasoning", ""),
        "evidence": response.evidence,
    }
    try:
        client.table("eval_results").insert(row).execute()
    except Exception as exc:
        if not _is_missing_column(exc, "evidence"):
            raise
        row.pop("evidence")
        client.table("eval_results").insert(row).execute()


def _dim1(target_name: str) -> str:
    """Short label for dimension 1, which each target redefines."""
    return {
        "supabase_docs": "relevance",
        "cerebro_news": "grounding",
        "apollo_explain": "numeric_fidelity",
    }.get(target_name, "dim1")


def run_eval(label: str, k: int, target_name: str, limit: int | None = None) -> int:
    target = get_target(target_name)
    client = get_supabase_client()
    queries = load_eval_queries(client, target_name)

    if not queries:
        print(f"No eval_queries found for target {target_name!r}. "
              f"Seed some first (see seed_eval_queries.py).")
        return 1

    queries.sort(key=lambda q: q["query"])
    if limit:
        queries = queries[:limit]

    print(f"Running eval: target={target_name} | {len(queries)} queries | "
          f"k={k} | label='{label}'")
    run_id = create_eval_run(client, label, target_name)
    print(f"Eval run ID: {run_id}\n")

    passed = failed = errored = 0
    consecutive_infra = 0
    aborted = False

    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {q['query'][:70]}...")
        try:
            response = target.answer(q["query"], q["expected_answer"], k)
            scores = judge_result(q["query"], q["expected_answer"], response, target.RUBRIC)
            insert_eval_result(client, run_id, q["id"], response, scores)
            consecutive_infra = 0

            accuracy = scores.get("answer_accuracy", 0.0)
            if accuracy >= PASS_THRESHOLD:
                passed += 1
                status = "PASS"
            else:
                failed += 1
                status = "FAIL"

            note = ""
            invented = response.evidence.get("unverified_numbers")
            if invented:
                note = f"   <-- INVENTED NUMBERS: {invented}"
            print(f"  {status} | {_dim1(target_name)}="
                  f"{scores.get('retrieval_relevance', 0.0):.2f} "
                  f"| accuracy={accuracy:.2f} | {response.latency_ms}ms{note}")

        except Exception as exc:
            errored += 1
            kind = classify_error(exc)
            # Only provider/transport failures count toward the abort. A data
            # error is specific to one query, so it must not push an unrelated
            # infra error over the threshold and stop an otherwise valid run.
            consecutive_infra = consecutive_infra + 1 if kind == "infra" else 0
            print(f"  ERROR ({kind}) | {str(exc)[:160]}")
            if consecutive_infra >= MAX_CONSECUTIVE_ERRORS:
                aborted = True
                print(f"\nAborting: {consecutive_errors} consecutive infrastructure "
                      f"errors. Remaining {len(queries) - i} queries not attempted.")
                break

    finish_eval_run(client, run_id)

    scored = passed + failed
    print("\n" + "=" * 60)
    print(f"  target   {target_name}")
    print(f"  scored   {scored}/{len(queries)}   (passed {passed}, failed {failed})")
    print(f"  errored  {errored}" + ("  [ABORTED EARLY]" if aborted else ""))
    if scored:
        print(f"  pass rate {passed / scored:.0%} of scored queries")
    print("=" * 60)

    if errored:
        plural = "y" if errored == 1 else "ies"
        print(f"\nThis run is NOT a valid quality signal: {errored} "
              f"quer{plural} never produced a score.")
        print(f"Run ID: {run_id}")
        return 1

    print(f"\nDone. {passed}/{scored} passed. Run ID: {run_id}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="default run", help="Human-readable run label")
    parser.add_argument("--k", type=int, default=5, help="Chunks to retrieve per query")
    parser.add_argument("--target", default="supabase_docs", choices=TARGET_NAMES,
                        help="Which system to evaluate")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N queries")
    parser.add_argument("--list-targets", action="store_true", help="List targets and exit")
    args = parser.parse_args()

    if args.list_targets:
        for name in TARGET_NAMES:
            first_line = get_target(name).RUBRIC.splitlines()[0]
            print(f"  {name:16} {first_line[:95]}")
        sys.exit(0)

    sys.exit(run_eval(label=args.label, k=args.k,
                      target_name=args.target, limit=args.limit))
