from __future__ import annotations

import chromadb

from config.settings import CHROMA_PATH, COLLECTION_NAME
from ingestion.embedder import get_embedding


client = chromadb.PersistentClient(path=str(CHROMA_PATH))
collection = client.get_or_create_collection(name=COLLECTION_NAME)


def add_document(doc_id: str, text: str, metadata: dict[str, str] | None = None) -> None:
    embedding = get_embedding(text)
    collection.upsert(
        ids=[doc_id],
        documents=[text],
        embeddings=[embedding],
        metadatas=[metadata or {}],
    )
    print(f"DEBUG chroma: upserted {doc_id}")


def query(text: str, k: int = 4) -> list[str]:
    embedding = get_embedding(text)
    results = collection.query(query_embeddings=[embedding], n_results=k)
    documents = results.get("documents", [[]])[0]
    print(f"DEBUG chroma: retrieved {len(documents)} documents")
    return documents
