"""
Unit tests for ingest.chunk_text — pure function, no network/DB needed.
Run with: pytest tests/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from ingest import chunk_text  # noqa: E402


def test_short_text_single_chunk():
    text = "This is a short paragraph well under the chunk size limit."
    chunks = chunk_text(text, size=800, overlap=120)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_respects_paragraph_boundaries_when_possible():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunks = chunk_text(text, size=800, overlap=120)
    # All fits in one chunk under the size limit, paragraphs preserved with separators
    assert len(chunks) == 1
    assert "Paragraph one." in chunks[0]
    assert "Paragraph three." in chunks[0]


def test_splits_long_text_into_multiple_chunks():
    paragraph = "word " * 50  # ~250 chars
    text = "\n\n".join([paragraph] * 10)  # ~2500+ chars total
    chunks = chunk_text(text, size=400, overlap=50)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 400 + 1  # allow tiny rounding slack from strip()


def test_no_empty_chunks():
    text = "\n\n\n   \n\nReal content here.\n\n\n"
    chunks = chunk_text(text, size=800, overlap=120)
    assert all(c.strip() for c in chunks)


def test_hard_wraps_single_oversized_paragraph():
    huge_paragraph = "a" * 2000  # no paragraph breaks at all
    chunks = chunk_text(huge_paragraph, size=500, overlap=50)
    assert len(chunks) > 1
    # reconstructed length should roughly cover the original (allowing overlap)
    assert sum(len(c) for c in chunks) >= len(huge_paragraph)
