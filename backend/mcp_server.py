"""
mcp_server.py
Exposes the Supabase-docs RAG pipeline as an MCP server.

Run directly (stdio transport):
    python mcp_server.py

Or register in Claude Desktop's config:
    {
      "mcpServers": {
        "supabase-docs": {
          "command": "python",
          "args": ["/absolute/path/to/backend/mcp_server.py"]
        }
      }
    }
"""
import os
import sys

# Load env before anything else, silently
from dotenv import load_dotenv
load_dotenv()

# Redirect stdout during imports to prevent any print() from corrupting
# the stdio JSON-RPC channel
_real_stdout = sys.stdout
sys.stdout = open(os.devnull, "w")

from retriever import retrieve
from rag_agent import answer_query

sys.stdout = _real_stdout  # restore stdout for MCP to use

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("supabase-docs")


@mcp.tool()
def search_supabase_docs(query: str, k: int = 5) -> list[dict]:
    """Search embedded Supabase documentation and return the top-k most
    relevant chunks (no generation, just retrieval — useful when an agent
    wants raw source material rather than a synthesized answer)."""
    chunks = retrieve(query, k=k)
    return [
        {"content": c["content"], "similarity": round(c["similarity"], 3)}
        for c in chunks
    ]


@mcp.tool()
def ask_supabase_docs(query: str) -> str:
    """Answer a question about Supabase using retrieval-augmented
    generation over the embedded docs. Returns a grounded answer with
    inline citation markers like [1], [2] referencing retrieved chunks."""
    result = answer_query(query)
    return result["answer"]


if __name__ == "__main__":
    mcp.run(transport="stdio")