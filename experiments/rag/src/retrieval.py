"""Index only the authoritative catalog in isolated, versioned Chroma collections."""

import hashlib
import json
from pathlib import Path

import sqlite3
import sys

# Chroma requires SQLite >= 3.35; reuse the installed compatibility package.
if sqlite3.sqlite_version_info < (3, 35, 0):
    import pysqlite3
    sys.modules["sqlite3"] = pysqlite3

from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

from .pattern_catalog import Pattern, load_pattern_catalog

ROOT = Path(__file__).resolve().parent.parent
CHROMA_PATH = ROOT / "data" / "chroma"
MODEL_CACHE = ROOT / "data" / "model_cache"
ADR4AI_COLLECTION = "adr4ai-patterns"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
RERANKER_MODEL = "BAAI/bge-reranker-base"
VECTOR_CANDIDATES = 15
FINAL_CANDIDATES = 5

TEXT_VERSION = "1"


def retrieval_text(pattern: Pattern) -> str:
    """Use source labels and values; do not synthesize absent pattern sections."""
    fields = pattern.model_dump()
    lines = [f"Pattern ID: {pattern.id}"]
    for key in ("name", "aka", "motivation", "solution", "consequences",
                "examples", "categories", "related", "resources"):
        value = fields[key]
        if isinstance(value, list):
            value = "; ".join(entry for entry in value if entry.strip())
        if value.strip():
            lines.append(f"{key.title()}: {value}")
    return "\n".join(lines)


def catalog_fingerprint(patterns: list[Pattern]) -> str:
    """Include source content, text format, and embedding model in compatibility."""
    payload = {"records": [p.model_dump() for p in patterns],
               "text_version": TEXT_VERSION, "embedding_model": EMBEDDING_MODEL}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def pattern_documents(patterns: list[Pattern]) -> list[Document]:
    fingerprint = catalog_fingerprint(patterns)
    return [Document(page_content=retrieval_text(p), metadata={
        "pattern_id": p.id, "knowledge_item_id": p.id, "name": p.name,
        "source": "catalogs/all-patterns.json", "catalog_fingerprint": fingerprint,
        "record_json": json.dumps(p.model_dump(), ensure_ascii=False, sort_keys=True),
    }) for p in patterns]


def index_is_compatible(store, documents: list[Document]) -> bool:
    """Check complete IDs, metadata, and text, including partial or damaged indexes."""
    stored = store.get(include=["documents", "metadatas"])
    expected = {d.metadata["pattern_id"]: d for d in documents}
    if len(stored["ids"]) != len(expected) or set(stored["ids"]) != set(expected):
        return False
    if len(stored["documents"]) != len(expected) or len(stored["metadatas"]) != len(expected):
        return False
    for key, content, metadata in zip(stored["ids"], stored["documents"], stored["metadatas"]):
        if content != expected[key].page_content or metadata != expected[key].metadata:
            return False
    return True


def ensure_pattern_index(catalog_path: str | Path | None = None,
                         persist_directory: str | Path = CHROMA_PATH,
                         embeddings=None):
    """Build before use; never open the legacy default collection.

    Each fingerprint gets its own collection. A failed new build cannot damage
    an earlier catalog's index. Incomplete or corrupted builds are retried on
    the next call. Old versions are retained; no unrelated collection is deleted.
    """
    patterns = load_pattern_catalog(catalog_path)
    documents = pattern_documents(patterns)
    fingerprint = catalog_fingerprint(patterns)
    if embeddings is None:
        from fastembed import TextEmbedding
        embeddings = FastEmbedEmbeddings.model_construct(
            model_name=EMBEDDING_MODEL,
            model=TextEmbedding(model_name=EMBEDDING_MODEL,
                                cache_dir=str(MODEL_CACHE), threads=2))
    store = Chroma(collection_name=f"{ADR4AI_COLLECTION}-{fingerprint}",
                   persist_directory=str(persist_directory), embedding_function=embeddings,
                   collection_metadata={"catalog_fingerprint": fingerprint,
                                        "embedding_model": EMBEDDING_MODEL,
                                        "text_version": TEXT_VERSION})
    rebuilt = not index_is_compatible(store, documents)
    if rebuilt:
        # Only this ADR4AI catalog version is replaced, after source validation.
        store.reset_collection()
        store.add_documents(documents, ids=[p.id for p in patterns])
        if not index_is_compatible(store, documents):
            raise RuntimeError("ADR4AI index integrity verification failed")
    return store, rebuilt


def create_retrieval_components():
    """Load the same embedding wrapper and cross-encoder as the recorded run."""
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    store, _ = ensure_pattern_index()
    reranker = TextCrossEncoder(model_name=RERANKER_MODEL,
                               cache_dir=str(MODEL_CACHE), threads=2)
    return store, reranker


def retrieve_rankings(store, reranker, query):
    """Preserve vector order and rerank by score with vector-rank tie-breaking."""
    import math

    candidates = store.similarity_search_with_score(query, k=VECTOR_CANDIDATES)
    if len(candidates) != VECTOR_CANDIDATES:
        raise ValueError("Vector retrieval must return exactly fifteen candidates")
    scores = list(reranker.rerank(query, [d.page_content for d, _ in candidates]))
    if len(scores) != len(candidates) or not all(math.isfinite(float(s)) for s in scores):
        raise ValueError("Reranker must return one finite score per candidate")
    top15 = [json.loads(document.metadata["record_json"])
             for document, _ in candidates]
    ranked = sorted(enumerate(zip(top15, scores), start=1),
                    key=lambda item: (-float(item[1][1]), item[0]))
    top5 = [item[1][0] for item in ranked[:FINAL_CANDIDATES]]
    return top15, top5
