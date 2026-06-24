"""
ingest.py
Loads Supabase docs (from local markdown files by default — see
sample_docs/ — or from a list of URLs via --urls), chunks them, embeds
each chunk, and writes documents + document_chunks into Supabase.

Usage:
    python ingest.py --dir ../sample_docs
    python ingest.py --urls urls.txt
"""
import argparse
import glob
import os
import re
import time

from embeddings import embed_texts
from db_client import insert_document, insert_chunks

CHUNK_SIZE = 800      # characters, not tokens — simple + dependency-free
CHUNK_OVERLAP = 120


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks, current = [], ""

    for p in paragraphs:
        if len(current) + len(p) + 2 <= size:
            current = f"{current}\n\n{p}".strip()
        else:
            if current:
                chunks.append(current)
            current = p
            while len(current) > size:
                chunks.append(current[:size])
                current = current[size - overlap:]
    if current:
        chunks.append(current)
    return [c.strip() for c in chunks if c.strip()]


def ingest_local_dir(dir_path: str):
    files = sorted(glob.glob(os.path.join(dir_path, "*.md")))
    if not files:
        print(f"No .md files found in {dir_path}")
        return

    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        title = os.path.basename(path).replace(".md", "").replace("-", " ").title()
        ingest_document(source_url=f"local://{os.path.basename(path)}", title=title, raw_content=raw)
        print(f"  waiting 20s to respect rate limit...")
        time.sleep(20)


def ingest_urls(urls_file: str):
    import requests
    with open(urls_file) as f:
        urls = [line.strip() for line in f if line.strip()]

    for url in urls:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        ingest_document(source_url=url, title=url, raw_content=resp.text)
        print(f"  waiting 20s to respect rate limit...")
        time.sleep(20)


def ingest_document(source_url: str, title: str, raw_content: str):
    doc_id = insert_document(source_url=source_url, title=title, raw_content=raw_content)
    chunks = chunk_text(raw_content)
    if not chunks:
        print(f"  skipped (no chunks): {title}")
        return

    embeddings = embed_texts(chunks)
    rows = [
        {
            "document_id": doc_id,
            "chunk_index": i,
            "content": chunk,
            "token_count": len(chunk.split()),
            "embedding": emb,
        }
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    insert_chunks(rows)
    print(f"  ingested: {title} -> {len(rows)} chunks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", help="Directory of local .md files to ingest")
    parser.add_argument("--urls", help="Text file with one doc URL per line")
    args = parser.parse_args()

    if args.urls:
        ingest_urls(args.urls)
    else:
        ingest_local_dir(args.dir or os.path.join(os.path.dirname(__file__), "..", "sample_docs"))