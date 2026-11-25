"""Steps 4-7 of the pipeline: embedding generation, ChromaDB storage and similarity search."""

from __future__ import annotations

from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import Settings
from app.rag.preprocess import chunk_documents, load_documents


@lru_cache
def get_embeddings(model_name: str) -> HuggingFaceEmbeddings:
    # Sentence Transformers model; normalised vectors so cosine similarity == dot product.
    return HuggingFaceEmbeddings(model_name=model_name, encode_kwargs={"normalize_embeddings": True})


class VectorStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.embeddings = get_embeddings(settings.embedding_model)
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.store = Chroma(
            collection_name=settings.collection_name,
            embedding_function=self.embeddings,
            persist_directory=str(settings.chroma_dir),
            collection_metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return self.store._collection.count()

    def rebuild(self, chunks: list[Document]) -> None:
        self.store.reset_collection()
        if chunks:
            self.store.add_documents(chunks, ids=[c.metadata["chunk_id"] for c in chunks])

    def search(self, query: str, k: int) -> list[tuple[Document, float]]:
        """Semantic similarity search. Returns (chunk, relevance score in [0, 1]) pairs, best first."""
        if self.count() == 0:
            return []
        return self.store.similarity_search_with_relevance_scores(query, k=k)


def build_index(settings: Settings, store: VectorStore | None = None) -> dict:
    """Run the full ingestion pipeline and (re)build the ChromaDB collection."""
    store = store or VectorStore(settings)
    docs = load_documents(settings.data_dir)
    chunks = chunk_documents(docs, settings.chunk_size, settings.chunk_overlap)
    store.rebuild(chunks)
    files = sorted({d.metadata["source"] for d in docs})
    return {"files": files, "documents": len(docs), "chunks": len(chunks)}
