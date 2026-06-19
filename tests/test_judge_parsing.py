"""
Unit tests for judge.parse_judge_response — pure parsing logic, no API calls.
Run with: pytest tests/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "eval"))

from judge import parse_judge_response  # noqa: E402


def test_parses_clean_json():
    raw = '{"retrieval_relevance": 0.8, "answer_accuracy": 0.9, "reasoning": "solid"}'
    result = parse_judge_response(raw)
    assert result == {
        "retrieval_relevance": 0.8,
        "answer_accuracy": 0.9,
        "reasoning": "solid",
    }


def test_handles_markdown_fenced_json():
    raw = '```json\n{"retrieval_relevance": 0.5, "answer_accuracy": 0.4, "reasoning": "meh"}\n```'
    result = parse_judge_response(raw)
    assert result["retrieval_relevance"] == 0.5
    assert result["answer_accuracy"] == 0.4


def test_defaults_reasoning_when_missing():
    raw = '{"retrieval_relevance": 1.0, "answer_accuracy": 1.0}'
    result = parse_judge_response(raw)
    assert result["reasoning"] == ""


def test_coerces_scores_to_float():
    raw = '{"retrieval_relevance": 1, "answer_accuracy": 0, "reasoning": "x"}'
    result = parse_judge_response(raw)
    assert isinstance(result["retrieval_relevance"], float)
    assert isinstance(result["answer_accuracy"], float)


def test_raises_on_missing_required_keys():
    raw = '{"reasoning": "incomplete response"}'
    try:
        parse_judge_response(raw)
        assert False, "expected KeyError for missing score fields"
    except KeyError:
        pass
