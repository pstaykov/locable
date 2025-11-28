import os
import sys
from rag.chroma_store import ChromaVectorStore
import inspect

def print_attr(obj, name):
    try:
        val = getattr(obj, name)
        print(f"{name}: {val}")
    except Exception as e:
        print(f"{name}: <error: {e}>")

store = ChromaVectorStore(persist_dir="data/chroma", collection_name="bootstrap")
client = store.client
collection = store.collection

print("=== store.persist_dir ===")
print(store.persist_dir)
print("=== inspect client type ===")
print(type(client))
print("=== common client attrs ===")
for a in ("persist_directory", "_persist_directory", "persist_dir", "persist_path", "_persist_path", "settings"):
    print_attr(client, a)

print("\n=== repr(client) ===")
print(repr(client))

print("\n=== attributes on client (selected, show paths) ===")
for name, val in inspect.getmembers(client):
    if name.startswith("_"):
        continue
    try:
        sval = repr(val)
    except Exception:
        sval = "<unrepr>"
    # print only likely path-like values or callables count
    if isinstance(val, str) and (os.path.exists(val) or "\\" in val or "/" in val):
        print(f"{name}: {val}")
    elif callable(val):
        continue
    elif name.lower().find("persist") >= 0 or name.lower().find("dir") >= 0 or name.lower().find("path") >= 0:
        print(f"{name}: {sval}")

print("\n=== collection object ===")
print(type(collection), repr(collection))

print("\n=== list files under expected folder ===")
root = os.path.abspath(store.persist_dir)
for r, ds, fs in os.walk(root):
    print(r, "->", len(fs), "files")
    for f in fs[:20]:
        print("   ", f)

print("\n=== quick filesystem search for recent chroma files (top-level) ===")
top = os.path.abspath(os.path.join(os.path.expanduser("~"), ".local"))  # example common place
for r, ds, fs in os.walk(top):
    for f in fs:
        if "chroma" in f.lower() or f.endswith((".parquet", ".db", ".duckdb")):
            print("found:", os.path.join(r, f))