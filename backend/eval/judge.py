"""
judge.py
LLM-as-judge scoring. Two scores per query, deliberately separated:

  retrieval_relevance — did the retrieved chunks actually contain the
                         facts needed to answer the question? (scores
                         the retriever, independent of the generator)
  answer_accuracy     — does the generated answer match the expected
                         facts? (scores the generator, given what it
                         had to work with)

Keeping these separate is the point of an eval-first design: a low
score tells you whether to fix chunking/embeddings or the prompt/model,
instead of one fuzzy "good/bad" number.
"""
import json
import os
from anthropic import Anthropic

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

JUDGE_SYSTEM = """You are a strict evaluator for a RAG system. You will be given:
- a question
- the expected reference answer (ground truth facts)
- the chunks that were retrieved
- the answer that was generated

Score two things from 0.0 to 1.0:
1. retrieval_relevance: do the retrieved chunks contain the facts needed to
   answer correctly? (1.0 = yes clearly, 0.0 = completely irrelevant chunks)
2. answer_accuracy: does the generated answer match the expected reference
   facts, without contradicting or fabricating? (1.0 = fully correct and
   complete, 0.0 = wrong or fabricated)

Respond with ONLY a JSON object, no markdown fences, no preamble:
{"retrieval_relevance": <float>, "answer_accuracy": <float>, "reasoning": "<one or two sentences>"}
"""


def parse_judge_response(raw: str) -> dict:
    """Pure parsing logic, split out from the API call so it's unit-testable
    without hitting Anthropic. Handles the case where the model wraps its
    JSON in markdown fences despite being told not to."""
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        parsed = json.loads(cleaned.strip())

    return {
        "retrieval_relevance": float(parsed["retrieval_relevance"]),
        "answer_accuracy": float(parsed["answer_accuracy"]),
        "reasoning": parsed.get("reasoning", ""),
    }


def judge(query: str, expected_answer: str, retrieved_chunks: list[dict], generated_answer: str) -> dict:
    chunks_text = "\n\n".join(f"- {c['content']}" for c in retrieved_chunks)
    user_prompt = (
        f"Question: {query}\n\n"
        f"Expected reference answer: {expected_answer}\n\n"
        f"Retrieved chunks:\n{chunks_text}\n\n"
        f"Generated answer: {generated_answer}"
    )

    client = Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = "".join(b.text for b in response.content if b.type == "text")
    return parse_judge_response(raw)
