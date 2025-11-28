import json
import os
from typing import List, Dict

from .chroma_store import ChromaVectorStore
from .embedding import embed


class LocalVectorStore:
    """Adapter that exposes a simple API backed by Chroma.

    Provides a compatible surface for older code:
      - build_index(chunks_file)
      - search(query, k=3)
    """

    def __init__(self, persist_dir: str = "data/chroma", collection_name: str = "bootstrap"):
        self.chroma = ChromaVectorStore(persist_dir=persist_dir, collection_name=collection_name)

    def build_index(self, chunks_file: str):
        """Build an index from a JSON file containing a list of text chunks.

        The JSON file should contain an array of strings (text chunks).
        This method computes embeddings using the project's `embed()` and
        upserts them into the chroma collection.
        """
        if not os.path.exists(chunks_file):
            raise FileNotFoundError(chunks_file)

        with open(chunks_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        if not isinstance(chunks, list):
            raise ValueError("Expected a JSON array of text chunks")

        ids = [f"chunk-{i}" for i in range(len(chunks))]
        metadatas = [{"source": os.path.abspath(chunks_file), "chunk_index": i} for i in range(len(chunks))]

        # Compute embeddings in batches
        embeddings = []
        batch_size = 64
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_emb = [embed(d).tolist() for d in batch]
            embeddings.extend(batch_emb)

        # Try upsert first (safer), fall back to add if necessary
        try:
            self.chroma.collection.upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
        except Exception:
            self.chroma.collection.add(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)

        try:
            self.chroma.client.persist()
        except Exception:
            pass

        return len(chunks)

    def search(self, query: str, k: int = 3) -> List[str]:
        """Return top-k document chunks for the `query`.

        Returns a list of document strings (chunks).
        """
        res = self.chroma.query(query, n_results=k)
        if not res:
            return []

        # Chroma responses are typically nested lists per query
        documents = res.get("documents") or res.get("documents", [])
        try:
            docs = documents[0]
        except Exception:
            docs = documents
        return docs
