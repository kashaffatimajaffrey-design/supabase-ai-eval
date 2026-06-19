"""
run_eval.py
The eval-first loop: for every query in eval_queries.json, run the RAG
agent, score it with the LLM judge, and log everything to Supabase
(eval_runs + eval_results) so the dashboard can chart quality over time.

Usage:
    python eval/run_eval.py --label "baseline chunk_size=800 k=5"
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

from rag_agent import answer_query, MODEL as GEN_MODEL
from embeddings import EMBEDDING_MODEL
from judge import judge
from db_client import (
    get_supabase_client,
    create_eval_run,
    finish_eval_run,
    insert_eval_result,
)

PASS_THRESHOLD = 0.7
QUERIES_PATH = os.path.join(os.path.dirname(__file__), "eval_queries.json")


def get_git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        return ""


def seed_eval_queries(queries: list[dict]) -> dict:
    """Get-or-create each eval query in Supabase, return {query_text: id}."""
    client = get_supabase_client()
    existing = {row["query"]: row["id"] for row in client.table("eval_queries").select("id, query").execute().data}

    id_map = {}
    for q in queries:
        if q["query"] in existing:
            id_map[q["query"]] = existing[q["query"]]
            continue
        res = client.table("eval_queries").insert({
            "query": q["query"],
            "expected_answer": q["expected_answer"],
            "category": q.get("category"),
            "difficulty": q.get("difficulty"),
        }).execute()
        id_map[q["query"]] = res.data[0]["id"]
    return id_map


def run(label: str, k: int):
    with open(QUERIES_PATH) as f:
        queries = json.load(f)

    query_ids = seed_eval_queries(queries)
    run_id = create_eval_run(
        run_label=label,
        model_used=GEN_MODEL,
        embed_model=EMBEDDING_MODEL,
        git_commit=get_git_commit(),
    )

    print(f"eval run: {run_id}  ({len(queries)} queries)\n")
    passed_count = 0
    rows_printed = []

    for q in queries:
        result = answer_query(q["query"], k=k)
        scores = judge(
            query=q["query"],
            expected_answer=q["expected_answer"],
            retrieved_chunks=result["retrieved_chunks"],
            generated_answer=result["answer"],
        )
        passed = scores["answer_accuracy"] >= PASS_THRESHOLD
        passed_count += int(passed)

        insert_eval_result({
            "eval_run_id": run_id,
            "eval_query_id": query_ids[q["query"]],
            "retrieved_chunk_ids": result["retrieved_chunk_ids"],
            "generated_answer": result["answer"],
            "retrieval_relevance": scores["retrieval_relevance"],
            "answer_accuracy": scores["answer_accuracy"],
            "latency_ms": result["latency_ms"],
            "passed": passed,
            "judge_reasoning": scores["reasoning"],
        })

        status = "PASS" if passed else "FAIL"
        rows_printed.append(
            f"  [{status}] {q['category']:<14} ret={scores['retrieval_relevance']:.2f} "
            f"acc={scores['answer_accuracy']:.2f} {result['latency_ms']}ms  {q['query'][:50]}"
        )
        print(rows_printed[-1])

    pass_rate = passed_count / len(queries)
    finish_eval_run(run_id, notes=f"pass_rate={pass_rate:.2f}")

    print(f"\n{'='*60}")
    print(f"pass rate: {pass_rate:.0%}  ({passed_count}/{len(queries)})")
    print(f"run logged to Supabase as eval_runs.id = {run_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="unlabeled run")
    parser.add_argument("--k", type=int, default=5, help="chunks to retrieve per query")
    args = parser.parse_args()
    run(label=args.label, k=args.k)
