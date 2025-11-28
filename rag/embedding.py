import ollama
import numpy as np

def embed(text: str):
    response = ollama.embeddings(
        model="nomic-embed-text",
        prompt=text
    )
    return np.array(response["embedding"], dtype="float32")
