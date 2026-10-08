"""Chroma vector database wrapper.

All knowledge chunks (text + embedding + metadata) live in a persistent
Chroma collection, so the index survives restarts without rebuilding.
Deleting a document removes exactly its chunks - no retraining involved.

Search is hybrid:
  1. semantic similarity for the whole question,
  2. plus a keyword probe for distinctive tokens (names like "Siraj" match
     book spellings such as "Sirajuddaula" that embeddings alone can miss).
"""
import re
import threading

import numpy as np
from langchain_core.documents import Document

from ..config import CHROMA_DIR
from ..logger import get_logger
from .embeddings import embedder

log = get_logger("historymaster.vectorstore")

# Three or more "(1999)"-style references => bibliography/endnote chunk.
_CITATION_YEAR_PATTERN = re.compile(r"\((?:19|20)\d{2}[^)]*\)")

# Question words never make good keyword probes.
_COMMON_WORDS = {
    "about", "after", "again", "against", "answer", "because", "before", "being",
    "between", "could", "describe", "during", "explain", "happened", "having",
    "history", "summary", "their", "there", "these", "things", "think", "this",
    "those", "under", "water", "what", "when", "where", "which", "while",
    "who", "whom", "whose", "will", "with", "would", "write", "wrote",
}

COLLECTION_NAME = "knowbot_knowledge_base"


class VectorStoreService:
    def __init__(self) -> None:
        self._store = None
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._store is not None

    def load(self) -> None:
        with self._lock:
            if self._store is not None:
                return
            from langchain_chroma import Chroma

            CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            log.info("Opening Chroma vector DB at %s ...", CHROMA_DIR)
            self._store = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=embedder.get(),
                persist_directory=str(CHROMA_DIR),
                collection_metadata={"hnsw:space": "cosine"},
            )
            log.info("Vector DB ready (%d chunks indexed).", self.count())

    def get(self):
        if self._store is None:
            raise RuntimeError("Vector store not loaded yet.")
        return self._store

    def count(self) -> int:
        if self._store is None:
            return 0
        try:
            return self._store._collection.count()
        except Exception:
            return 0

    def add_chunks(self, doc_id: int, filename: str, chunks: list[str]) -> int:
        """Embed + store chunks for one document. Returns the chunk count."""
        if not chunks:
            return 0
        store = self.get()
        ids = [f"doc{doc_id}-chunk{i}" for i in range(len(chunks))]
        metadatas = [
            {"doc_id": int(doc_id), "filename": filename, "chunk_index": i}
            for i in range(len(chunks))
        ]
        store.add_texts(texts=chunks, metadatas=metadatas, ids=ids)
        return len(chunks)

    def delete_document(self, doc_id: int) -> None:
        self.get()._collection.delete(where={"doc_id": int(doc_id)})

    def search(self, query: str, top_k: int) -> list[tuple]:
        """Return [(Document, cosine_similarity)] sorted best-first.

        Hybrid retrieval:
        1. semantic similarity for the whole question,
        2. keyword probes for distinctive tokens - a probe like "Siraj"
           substring-matches book spellings such as "Sirajuddaula" that pure
           embeddings can rank too low.
        Bibliography/citation chunks get a small score penalty in both paths.
        """
        semantic = self._semantic_search(query, top_k)
        probes = [
            tok for tok in re.findall(r"[A-Za-z]{5,}", query)
            if tok.lower() not in _COMMON_WORDS
        ][:3]
        if not probes:
            return semantic
        lexical = self._keyword_candidates(query, probes, exclude=semantic)
        if not lexical:
            return semantic
        # Keep both sets whole: semantic hits first, then the name-matched
        # candidates. The LLM's grounding contract filters any noise this adds,
        # while name variants ("Siraj ud-Daulah" vs "Sirajuddaula") always
        # reach it. ~30 chunks x 1000 chars is well within the LLM context.
        return semantic + lexical

    def _semantic_search(self, query: str, top_k: int) -> list[tuple]:
        store = self.get()
        pool = max(top_k * 2, top_k + 10)
        pairs = store.similarity_search_with_score(query, k=pool)
        scored = [self._score(doc, 1.0 - float(distance)) for doc, distance in pairs]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def _keyword_candidates(self, query: str, probes: list[str],
                            exclude: list[tuple]) -> list[tuple]:
        """Find chunks containing the probe tokens and score them semantically."""
        collection = self.get()._collection
        key = lambda doc: (doc.metadata.get("doc_id"), doc.metadata.get("chunk_index"))
        seen = {key(doc) for doc, _score in exclude}

        candidates: dict[tuple, Document] = {}
        for probe in probes:
            try:
                got = collection.get(
                    where_document={"$contains": probe},
                    include=["documents", "metadatas"],
                    limit=24,
                )
            except Exception as exc:
                log.debug("Keyword probe %r failed: %s", probe, exc)
                continue
            for text, meta in zip(got.get("documents") or [], got.get("metadatas") or []):
                doc = Document(page_content=text, metadata=meta or {})
                if key(doc) not in seen:
                    candidates[key(doc)] = doc
        if not candidates:
            return []

        docs = list(candidates.values())
        try:
            query_vector = np.asarray(
                embedder.get().embed_query(query), dtype=np.float32
            )
            doc_vectors = np.asarray(
                embedder.get().embed_documents([d.page_content[:1500] for d in docs]),
                dtype=np.float32,
            )
        except Exception as exc:
            log.warning("Keyword probe embedding failed: %s", exc)
            return []
        query_vector /= (np.linalg.norm(query_vector) + 1e-9)
        doc_vectors /= (np.linalg.norm(doc_vectors, axis=1, keepdims=True) + 1e-9)
        scored = []
        for i, doc in enumerate(docs):
            # Bibliography pages often contain the same name tokens (historians
            # named "Sirajul", publishers, year refs) but are never answers -
            # keep them out of the probe pool entirely.
            citation_hits = len(_CITATION_YEAR_PATTERN.findall(doc.page_content))
            if citation_hits >= 3:
                continue
            similarity = float(doc_vectors[i] @ query_vector)
            # Name matching dominates here: a chunk containing (a fuzzy variant
            # of) the probed name is almost certainly about the question's
            # subject, even when its plain embedding score is lukewarm. Rank by
            # match count first, cosine second.
            text_lower = doc.page_content.lower()
            matched_probes = 0
            for probe in probes:
                probe_lower = probe.lower()
                if probe_lower in text_lower or (
                    len(probe_lower) >= 5 and probe_lower[:-1] in text_lower
                ):
                    matched_probes += 1
            if matched_probes:
                similarity += 0.25 * matched_probes
            scored.append((doc, similarity, matched_probes))
        # primary: number of probed names present, secondary: cosine.
        scored.sort(key=lambda item: (item[2], item[1]), reverse=True)
        return [(doc, similarity) for doc, similarity, _count in scored[:10]]

    @staticmethod
    def _score(doc: Document, similarity: float) -> tuple[Document, float]:
        citation_hits = len(_CITATION_YEAR_PATTERN.findall(doc.page_content))
        if citation_hits >= 3:
            similarity *= 0.8
        return doc, similarity


vector_store = VectorStoreService()
