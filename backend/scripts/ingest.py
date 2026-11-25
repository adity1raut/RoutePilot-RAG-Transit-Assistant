"""Run the ingestion pipeline: data/raw -> extraction -> cleaning -> chunking -> embeddings -> ChromaDB.

Usage (from backend/):  python -m scripts.ingest
"""

from app.config import get_settings
from app.rag.vectorstore import build_index


def main() -> None:
    settings = get_settings()
    print(f"Indexing files in {settings.data_dir} with {settings.embedding_model} ...")
    stats = build_index(settings)
    print(f"Indexed {stats['documents']} documents as {stats['chunks']} chunks from: {', '.join(stats['files'])}")
    print(f"Vector store: {settings.chroma_dir} (collection '{settings.collection_name}')")


if __name__ == "__main__":
    main()
