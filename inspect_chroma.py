from rag.chroma_store import ChromaVectorStore
s = ChromaVectorStore(persist_dir="data/chroma", collection_name="bootstrap")
print(s.query("container class css", n_results=3))