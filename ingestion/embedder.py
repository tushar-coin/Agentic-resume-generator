from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from config.settings import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    print(f"DEBUG embedder: loading embedding model {EMBEDDING_MODEL}")
    return SentenceTransformer(EMBEDDING_MODEL)


def get_embedding(text: str) -> list[float]:
    """Embed text using one cached SentenceTransformer instance."""
    model = _get_model()
    return model.encode(text).tolist()
