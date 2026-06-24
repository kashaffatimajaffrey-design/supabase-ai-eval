"""
run_eval.py
Runs the eval harness: loads eval_queries from Supabase, calls the RAG
agent on each, uses Claude as a judge to score answers, and writes
eval_runs + eval_results back to Supabase.

Usage:
    python run_eval.py
    python run_eval.py --label "chunk_size=800 / k=5" --k 5
"""
import argparse
import json
import os
import subprocess
import time

from dotenv import load_dotenv
load_dotenv()

from anthropic import Anthropic
from db_client import get_supabase_client
from rag_agent import answer_query, MODEL

EMBED_MODEL = os.environ.get("EMBEDDING_MODEL", "voyage-3-lite")
PASS_THRESHOLD = 0.7


def get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def load_eval_queries(client) -> list[dict]:
    res = client.table("eval_queries").select("*").execute()
    return res.data


def create_eval_run(client, label: str) -> str:
    res = client.table("eval_runs").insert({
        "run_label": label,
        "model_used": MODEL,
        "embed_model": EMBED_MODEL,
        "git_commit": get_git_commit(),
    }).execute()
    return res.data[0]["id"]


def finish_eval_run(client, run_id: str):
    client.table("eval_runs").update({
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }).eq("id", run_id).execute()


def judge_result(query: str, expected: str, answer: str, chunks: list[dict]) -> dict:
    """Use Claude to score retrieval relevance and answer accuracy."""
    client = Anthropic()
    prompt = f"""You are an evaluation judge for a RAG system over Supabase docs.
Score the following on two dimensions, each 0.0–1.0:

1. retrieval_relevance: Did the retrieved chunks contain information needed to answer the question?
2. answer_accuracy: Does the generated answer correctly address the question based on the expected facts?

Question: {query}
Expected facts: {expected}
Retrieved chunks:
{chr(10).join(f'[{i+1}] {c["content"][:300]}' for i, c in enumerate(chunks))}
Generated answer: {answer}

Respond ONLY with a JSON object like:
{{"retrieval_relevance": 0.8, "answer_accuracy": 0.9, "reasoning": "brief explanation"}}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # strip markdown fences if Claude wrapped it
        clean = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)


def insert_eval_result(client, run_id: str, query_id: str, rag_result: dict, scores: dict):
    accuracy = scores.get("answer_accuracy", 0.0)
    client.table("eval_results").insert({
        "eval_run_id": run_id,
        "eval_query_id": query_id,
        "retrieved_chunk_ids": rag_result["retrieved_chunk_ids"],
        "generated_answer": rag_result["answer"],
        "retrieval_relevance": scores.get("retrieval_relevance", 0.0),
        "answer_accuracy": accuracy,
        "latency_ms": rag_result["latency_ms"],
        "passed": accuracy >= PASS_THRESHOLD,
        "judge_reasoning": scores.get("reasoning", ""),
    }).execute()


def run_eval(label: str, k: int):
    client = get_supabase_client()
    queries = load_eval_queries(client)

    if not queries:
        print("No eval_queries found in DB. Seed some first (see seed_eval_queries.py).")
        return

    print(f"Running eval: {len(queries)} queries | k={k} | label='{label}'")
    run_id = create_eval_run(client, label)
    print(f"Eval run ID: {run_id}\n")

    passed = 0
    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {q['query'][:70]}...")
        try:
            rag_result = answer_query(q["query"], k=k)
            scores = judge_result(
                query=q["query"],
                expected=q["expected_answer"],
                answer=rag_result["answer"],
                chunks=rag_result["retrieved_chunks"],
            )
            insert_eval_result(client, run_id, q["id"], rag_result, scores)

            status = "PASS" if scores.get("answer_accuracy", 0) >= PASS_THRESHOLD else "FAIL"
            if status == "PASS":
                passed += 1
            print(f"  {status} | relevance={scores.get('retrieval_relevance'):.2f} "
                  f"| accuracy={scores.get('answer_accuracy'):.2f} "
                  f"| {rag_result['latency_ms']}ms")
        except Exception as e:
            print(f"  ERROR: {e}")

    finish_eval_run(client, run_id)
    print(f"\nDone. {passed}/{len(queries)} passed. Run ID: {run_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="default run", help="Human-readable run label")
    parser.add_argument("--k", type=int, default=5, help="Chunks to retrieve per query")
    args = parser.parse_args()
    run_eval(label=args.label, k=args.k)