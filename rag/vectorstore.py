import json
import os
from typing import List, Dict, Optional, Any

from .chroma_store import ChromaVectorStore
from .embedding import embed


class LocalVectorStore:
    """Adapter that exposes a simple API backed by Chroma.

    Provides a compatible surface for older code and new template-aware indexing:
      - build_index(chunks_file)
      - search(query, k=3, where=None, include_meta=False)
      - search_templates(description_query, k=5)
      - fetch_css_chunks(template_name, limit=5)
    """

    def __init__(self, persist_dir: str = "data/chroma", collection_name: str = "bootstrap"):
        self.chroma = ChromaVectorStore(persist_dir=persist_dir, collection_name=collection_name)

    def _prepare_chunks(self, payload: List[Any]):
        """Normalize payload into docs/ids/metadata tuples."""
        docs: List[str] = []
        ids: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        if payload and isinstance(payload[0], dict):
            for i, item in enumerate(payload):
                text = item.get("text") or item.get("content")
                if not text:
                    continue
                meta = item.get("metadata") or {}
                doc_id = item.get("id") or meta.get("id") or f"chunk-{i}"
                docs.append(text)
                ids.append(doc_id)
                metadatas.append(meta)
        else:
            for i, text in enumerate(payload):
                if not isinstance(text, str):
                    continue
                docs.append(text)
                ids.append(f"chunk-{i}")
                metadatas.append({"chunk_index": i})
        return docs, ids, metadatas

    def build_index(self, chunks_file: str):
        """Build an index from a JSON file containing text chunks.

        Supports two formats:
          1. ["text", "text2", ...]
          2. [{"id": "...", "text": "...", "metadata": {...}}, ...]
        """
        if not os.path.exists(chunks_file):
            raise FileNotFoundError(chunks_file)

        with open(chunks_file, "r", encoding="utf-8") as f:
            payload = json.load(f)

        if not isinstance(payload, list):
            raise ValueError("Expected a JSON array of text chunks or chunk objects")

        docs, ids, metadatas = self._prepare_chunks(payload)

        if not docs:
            return 0

        embeddings = []
        for doc in docs:
            vec = embed(doc)
            if hasattr(vec, "tolist"):
                vec = vec.tolist()
            embeddings.append(vec)

        # Try upsert first (safer), fall back to add if necessary
        try:
            self.chroma.collection.upsert(ids=ids, documents=docs, metadatas=metadatas, embeddings=embeddings)
        except Exception:
            self.chroma.collection.add(ids=ids, documents=docs, metadatas=metadatas, embeddings=embeddings)

        try:
            if hasattr(self.chroma.client, "persist"):
                self.chroma.client.persist()
            else:
                self.chroma.collection.persist()
        except Exception:
            pass

        return len(docs)

    def search(self, query: str, k: int = 8, where: Optional[Dict[str, Any]] = None, include_meta: bool = False) -> Any:
        """Return top-k documents for the query, optionally including metadata."""
        res = self.chroma.query(query, n_results=k, where=where)
        if include_meta:
            return res
        if not res:
            return []
        documents = res.get("documents") or res.get("documents", [])
        try:
            return documents[0]
        except Exception:
            return documents

    def search_templates(self, description_query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Find templates by comparing the user purpose against template descriptions."""
        res = self.chroma.query(description_query, n_results=k, where={"type": "description"}, include=["documents", "metadatas", "distances"])
        hits: List[Dict[str, Any]] = []
        if not res:
            return hits

        documents = res.get("documents") or [[]]
        metadatas = res.get("metadatas") or [[]]
        distances = res.get("distances") or [[]]

        for i, doc in enumerate(documents[0]):
            meta = metadatas[0][i] or {}
            dist_val = None
            try:
                dist_val = float(distances[0][i])
            except Exception:
                dist_val = None
            hits.append({
                "template": meta.get("template"),
                "description": meta.get("description") or doc,
                "source": meta.get("source"),
                "distance": dist_val,
            })
        return hits

    def fetch_css_chunks(self, template_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return CSS chunks for a template so the builder can reuse its styles."""
        try:
            res = self.chroma.get(where={"template": template_name, "type": "css"}, limit=limit, include=["documents", "metadatas", "ids"])
        except Exception:
            return []

        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        chunks: List[Dict[str, Any]] = []
        for doc, meta in zip(docs, metas):
            chunks.append({"text": doc, "metadata": meta})
        return chunks

    def search_template_chunks(self, query: str, template_name: str, k: int = 5, chunk_type: Optional[str] = None) -> List[str]:
        """Search within a specific template (optionally filtering by chunk type)."""
        where: Dict[str, Any] = {"template": template_name}
        if chunk_type:
            where["type"] = chunk_type
        return self.search(query, k=k, where=where)


def _demo():
    store = LocalVectorStore()
    res = store.search("navbar", k=2, include_meta=True)
    print(res)


if __name__ == "__main__":
    _demo()
