import os
import glob
import json
from typing import List, Dict

# try to import chromadb and its Settings helper (not all versions expose Settings)
try:
    import chromadb
    try:
        from chromadb.config import Settings  # optional, legacy/older usage
    except Exception:
        Settings = None
except Exception:
    chromadb = None
    Settings = None

import numpy as np
from .embedding import embed


class ChromaVectorStore:
    """Simple Chroma-backed vector store for local files."""

    def __init__(self, persist_dir: str = "data/chroma", collection_name: str = "bootstrap"):
        if chromadb is None:
            raise ImportError("chromadb is not installed. Install with `pip install chromadb`")

        # make persist_dir absolute to avoid chroma using a different default location
        self.persist_dir = os.path.abspath(persist_dir)
        self.collection_name = collection_name
        os.makedirs(self.persist_dir, exist_ok=True)

        self.client = None

        # Try new PersistentClient if available (preferred for persistence)
        try:
            if hasattr(chromadb, "PersistentClient"):
                self.client = chromadb.PersistentClient(persist_directory=self.persist_dir, chroma_db_impl="duckdb+parquet")
        except Exception:
            self.client = None

        # Try client constructor with persist_directory kwarg
        if self.client is None:
            try:
                self.client = chromadb.Client(persist_directory=self.persist_dir, chroma_db_impl="duckdb+parquet")
            except TypeError:
                self.client = None
            except ValueError:
                # Some chromadb versions raise ValueError for deprecated configs.
                self.client = None
            except Exception:
                self.client = None

        # Legacy fallback using Settings (older chroma versions)
        if self.client is None and Settings is not None:
            try:
                settings = Settings(chroma_db_impl="duckdb+parquet", persist_directory=self.persist_dir)
                self.client = chromadb.Client(settings)
            except Exception:
                self.client = None

        # Final fallback to a default client (may be in-memory if persistence couldn't be configured)
        if self.client is None:
            self.client = chromadb.Client()

        # Create or get collection in a version-compatible way
        if hasattr(self.client, "get_or_create_collection"):
            self.collection = self.client.get_or_create_collection(self.collection_name)
        else:
            try:
                self.collection = self.client.get_collection(self.collection_name)
            except Exception:
                self.collection = self.client.create_collection(self.collection_name)

    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if overlap < 0:
            overlap = 0
        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = min(start + chunk_size, text_len)
            chunks.append(text[start:end])
            if end == text_len:
                break
            start = max(0, end - overlap)
        return chunks

    def index_bootstrap_files(self, source_dir: str = "data/bootstrap", chunk_size: int = 1000, overlap: int = 200):
        """Index all files under `source_dir` into Chroma. Returns number of chunks indexed."""
        files = glob.glob(os.path.join(source_dir, "**"), recursive=True)
        files = [f for f in files if os.path.isfile(f)]

        all_docs = []
        all_ids = []
        all_metadatas = []

        for path in files:
            # read as text, fallback to replace on decode errors
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except Exception:
                with open(path, "rb") as fh:
                    text = fh.read().decode("utf-8", errors="replace")

            if not text:
                continue

            chunks = self._chunk_text(text, chunk_size=chunk_size, overlap=overlap)
            for i, c in enumerate(chunks):
                doc_id = f"{os.path.basename(path)}::{i}"
                all_ids.append(doc_id)
                all_docs.append(c)
                all_metadatas.append({"source": os.path.abspath(path), "chunk_index": i})

        if not all_docs:
            print("No documents found to index.")
            return 0

        # compute embeddings in batches
        batch_size = 64
        all_embeddings = []
        for i in range(0, len(all_docs), batch_size):
            batch = all_docs[i:i + batch_size]
            # try a vectorized embed(batch) if supported, otherwise fallback per-document
            try:
                emb_batch = embed(batch)
                if hasattr(emb_batch, "tolist"):
                    emb_batch = emb_batch.tolist()
                if not isinstance(emb_batch, list) or len(emb_batch) != len(batch):
                    raise ValueError("embed(batch) did not return expected shape")
                all_embeddings.extend(emb_batch)
            except Exception:
                for doc in batch:
                    v = embed(doc)
                    if hasattr(v, "tolist"):
                        v = v.tolist()
                    all_embeddings.append(v)

        # upsert or add (compatibility for various chroma versions)
        try:
            if hasattr(self.collection, "upsert"):
                self.collection.upsert(ids=all_ids, documents=all_docs, metadatas=all_metadatas, embeddings=all_embeddings)
            else:
                self.collection.add(ids=all_ids, documents=all_docs, metadatas=all_metadatas, embeddings=all_embeddings)
        except Exception as e:
            try:
                self.collection.add(all_ids, all_docs, all_metadatas, all_embeddings)
            except Exception as e2:
                raise RuntimeError(f"Failed to add/upsert documents to Chroma collection: {e} / {e2}")

        # persist if client supports it
        try:
            if hasattr(self.client, "persist"):
                self.client.persist()
            elif hasattr(self.collection, "persist"):
                self.collection.persist()
        except Exception:
            # not fatal; best-effort persistence
            pass

        # --- NEW: write a local snapshot to persist_dir so you always have files locally ---
        try:
            docs_path = os.path.join(self.persist_dir, "documents.json")
            ids_path = os.path.join(self.persist_dir, "ids.json")
            metas_path = os.path.join(self.persist_dir, "metadatas.json")
            emb_path = os.path.join(self.persist_dir, "embeddings.npy")

            with open(docs_path, "w", encoding="utf-8") as f:
                json.dump(all_docs, f, ensure_ascii=False)

            with open(ids_path, "w", encoding="utf-8") as f:
                json.dump(all_ids, f, ensure_ascii=False)

            with open(metas_path, "w", encoding="utf-8") as f:
                json.dump(all_metadatas, f, ensure_ascii=False)

            np_emb = np.array(all_embeddings, dtype=np.float32)
            np.save(emb_path, np_emb)
        except Exception as e:
            print("Warning: failed to write local snapshot:", e)
        # --- end snapshot ---

        print(f"Indexed {len(all_docs)} chunks into Chroma collection '{self.collection_name}' at '{self.persist_dir}'.")
        return len(all_docs)

    def query(self, query_text: str, n_results: int = 3):
        q_emb_raw = embed(query_text)
        q_emb = q_emb_raw.tolist() if hasattr(q_emb_raw, "tolist") else q_emb_raw
        # new APIs typically want query_embeddings list-of-vectors
        try:
            results = self.collection.query(
                query_embeddings=[q_emb],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
        except Exception:
            # fallback older signature
            results = self.collection.query(query_text, n_results=n_results, include=["documents", "metadatas", "distances"])
        # If chroma returned empty documents, fallback to local brute-force search using saved snapshot
        try:
            docs = results.get("documents") or results.get("documents", [])
            if docs and any(docs[0]):
                return results
        except Exception:
            pass

        # fallback: brute-force from local snapshot
        emb_path = os.path.join(self.persist_dir, "embeddings.npy")
        docs_path = os.path.join(self.persist_dir, "documents.json")
        if os.path.exists(emb_path) and os.path.exists(docs_path):
            try:
                stored_emb = np.load(emb_path)
                qv = np.array(q_emb, dtype=np.float32)
                sims = stored_emb @ qv
                topk = np.argsort(-sims)[:n_results]
                with open(docs_path, "r", encoding="utf-8") as f:
                    stored_docs = json.load(f)
                return {"documents": [[stored_docs[i] for i in topk.tolist()]], "distances": [[float(sims[i]) for i in topk.tolist()]], "metadatas": [[None]*len(topk)]}
            except Exception:
                pass

        return results


if __name__ == "__main__":
    print("Chroma Vector Store Indexer")
    try:
        store = ChromaVectorStore(persist_dir="data/chroma", collection_name="bootstrap")
    except ImportError as e:
        print(e)
        print("Install chromadb: pip install chromadb")
        raise SystemExit(1)

    indexed = store.index_bootstrap_files(source_dir="data/bootstrap", chunk_size=1000, overlap=200)
    print(f"Done. Indexed {indexed} chunks.")
