"""
Hybrid retrieval: SQL owns structured user data; Chroma stores resume embeddings
for semantic match against job descriptions (JD ↔ resume section retrieval).

Why both?
- SQL: ACID ownership, auth, application tracker, ATS scores, constraints
- Vector DB: approximate nearest-neighbor over resume chunks for "what experience
  maps to this JD?" — improves optimization context without dumping full resume
  into every prompt blindly
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger("careerforge.vector")

_collection = None
_client = None


def _enabled() -> bool:
    return bool(settings.CHROMA_ENABLED)


def _get_collection():
    global _collection, _client
    if not _enabled():
        return None
    if _collection is not None:
        return _collection
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name="resume_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        return _collection
    except Exception as e:
        logger.warning("chroma_unavailable err=%s", e)
        return None


def _chunk_text(text: str, max_chars: int = 700) -> List[str]:
    parts = re.split(r"\n{2,}|\r\n{2,}", text or "")
    chunks: List[str] = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) + 1 <= max_chars:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= max_chars:
                buf = p
            else:
                for i in range(0, len(p), max_chars):
                    chunks.append(p[i : i + max_chars])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks[:40]  # hard cap per resume


def index_resume(user_id: int, resume_id: int, text: str) -> Optional[str]:
    """
    Upsert resume chunks into Chroma, scoped by user_id for isolation.
    Returns vector namespace key used for this resume.
    """
    col = _get_collection()
    if col is None or not text or len(text.strip()) < 40:
        return None

    namespace = f"u{user_id}_r{resume_id}"
    # Remove previous chunks for this resume (idempotent re-index)
    try:
        existing = col.get(where={"resume_id": resume_id})
        if existing and existing.get("ids"):
            col.delete(ids=existing["ids"])
    except Exception as e:
        logger.info("chroma_delete_old_chunks resume_id=%s err=%s", resume_id, e)

    chunks = _chunk_text(text)
    if not chunks:
        return None

    ids = []
    metadatas = []
    documents = []
    for i, chunk in enumerate(chunks):
        cid = hashlib.sha1(f"{namespace}:{i}:{chunk[:40]}".encode()).hexdigest()[:24]
        ids.append(f"{namespace}_{i}_{cid}")
        documents.append(chunk)
        metadatas.append(
            {
                "user_id": user_id,
                "resume_id": resume_id,
                "chunk_index": i,
                "namespace": namespace,
            }
        )

    try:
        col.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.info(
            "chroma_indexed user_id=%s resume_id=%s chunks=%s",
            user_id,
            resume_id,
            len(ids),
        )
        return namespace
    except Exception as e:
        logger.error("chroma_index_error resume_id=%s err=%s", resume_id, e)
        return None


def delete_resume_vectors(resume_id: int) -> None:
    col = _get_collection()
    if col is None:
        return
    try:
        existing = col.get(where={"resume_id": resume_id})
        if existing and existing.get("ids"):
            col.delete(ids=existing["ids"])
            logger.info("chroma_deleted resume_id=%s count=%s", resume_id, len(existing["ids"]))
    except Exception as e:
        logger.error("chroma_delete_error resume_id=%s err=%s", resume_id, e)


def query_relevant_chunks_detailed(
    user_id: int,
    resume_id: int,
    job_description: str,
    n_results: int = 4,
) -> dict:
    """
    Semantic top-k chunks + cosine distances for Layer-2 ATS scoring.
    Always filtered by user_id + resume_id (tenant isolation).

    Returns:
      {
        "chunks": [str, ...],
        "distances": [float, ...],  # lower = more similar
        "available": bool,
      }
    """
    empty = {"chunks": [], "distances": [], "available": False}
    col = _get_collection()
    if col is None or not job_description.strip():
        return empty

    def _pack(result: dict, filter_user: bool = False) -> dict:
        docs = (result.get("documents") or [[]])[0] or []
        dists = (result.get("distances") or [[]])[0] or []
        metas = (result.get("metadatas") or [[]])[0] or []
        chunks, distances = [], []
        for i, d in enumerate(docs):
            if not d:
                continue
            if filter_user:
                m = metas[i] if i < len(metas) else {}
                if not m or m.get("user_id") != user_id:
                    continue
            chunks.append(d)
            distances.append(float(dists[i]) if i < len(dists) else 1.0)
        return {
            "chunks": chunks[:n_results],
            "distances": distances[:n_results],
            "available": bool(chunks),
        }

    try:
        result = col.query(
            query_texts=[job_description[:2000]],
            n_results=n_results,
            where={
                "$and": [
                    {"user_id": user_id},
                    {"resume_id": resume_id},
                ]
            },
            include=["documents", "distances", "metadatas"],
        )
        packed = _pack(result)
        if packed["available"]:
            logger.info(
                "chroma_query ok user_id=%s resume_id=%s hits=%s best_dist=%s",
                user_id,
                resume_id,
                len(packed["chunks"]),
                min(packed["distances"]) if packed["distances"] else None,
            )
        return packed
    except Exception as e:
        logger.warning("chroma_query_primary_failed err=%s", e)
        try:
            result = col.query(
                query_texts=[job_description[:2000]],
                n_results=max(n_results * 3, 8),
                where={"resume_id": resume_id},
                include=["documents", "distances", "metadatas"],
            )
            return _pack(result, filter_user=True)
        except Exception as e2:
            logger.error("chroma_query_failed err=%s / %s", e, e2)
            return empty


def query_relevant_chunks(
    user_id: int,
    resume_id: int,
    job_description: str,
    n_results: int = 4,
) -> List[str]:
    """Back-compat: return only chunk texts."""
    return query_relevant_chunks_detailed(
        user_id, resume_id, job_description, n_results
    ).get("chunks") or []


def vector_health() -> dict:
    col = _get_collection()
    if col is None:
        return {"enabled": False, "status": "disabled_or_unavailable"}
    try:
        count = col.count()
        return {"enabled": True, "status": "ok", "chunks": count}
    except Exception as e:
        return {"enabled": True, "status": f"error: {e}"}
