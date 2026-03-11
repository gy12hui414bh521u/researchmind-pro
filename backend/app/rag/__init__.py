"""
ResearchMind Pro — RAG Pipeline
"""

from app.rag.embeddings import EmbeddingClient, get_embedding_client
from app.rag.ingestion import (
    DocumentChunk,
    IngestionResult,
    ingest_text,
    ingest_pdf,
    ingest_url,
    clean_text,
    split_by_tokens_approx,
)
from app.rag.retriever import (
    RetrievalResult,
    retrieve,
    agentic_retrieve,
    delete_doc_vectors,
    get_collection_stats,
)

__all__ = [
    # embeddings
    "EmbeddingClient", "get_embedding_client",
    # ingestion
    "DocumentChunk", "IngestionResult",
    "ingest_text", "ingest_pdf", "ingest_url",
    "clean_text", "split_by_tokens_approx",
    # retriever
    "RetrievalResult",
    "retrieve", "agentic_retrieve",
    "delete_doc_vectors", "get_collection_stats",
]
