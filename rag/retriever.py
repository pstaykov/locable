from typing import List, Dict

from .vectorstore import LocalVectorStore


class Retriever:
    """Simple retriever that returns documents + metadata + distances.

    This is a thin wrapper around `LocalVectorStore` to provide a
    convenient structure for callers that want metadata and distances.
    """

    def __init__(self, persist_dir: str = "data/chroma", collection_name: str = "bootstrap"):
        self.store = LocalVectorStore(persist_dir=persist_dir, collection_name=collection_name)

    def get_relevant(self, query: str, k: int = 20) -> List[Dict]:
        """Return a list of results: {document, metadata, distance} ordered by relevance."""
        # Use the underlying chroma query via the adapter
        res = self.store.chroma.query(query, n_results=k)
        results = []
        if not res:
            return results

        # Expected shape: dict with lists of lists (one list per query)
        doc_lists = res.get("documents", [])
        meta_lists = res.get("metadatas", [])
        dist_lists = res.get("distances", [])

        docs = doc_lists[0] if doc_lists else []
        metas = meta_lists[0] if meta_lists else []
        dists = dist_lists[0] if dist_lists else []

        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) else None
            dist = dists[i] if i < len(dists) else None
            results.append({"document": doc, "metadata": meta, "distance": dist})

        return results
