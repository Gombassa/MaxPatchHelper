import os
import json
import argparse
import requests
import chromadb

CHROMA_DB_PATH = "data/chroma"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"


def get_embedding(text, model=EMBED_MODEL):
    """Generate vector embedding using local Ollama."""
    try:
        response = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": model, "prompt": text},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("embedding")
        else:
            print(f"[Ollama] Error: HTTP {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"[Ollama] Error generating embedding: {e}")
        return None


def query_vector_db(query_text, collection_name="max8_docs", domain=None, max_version="8", n_results=5):
    """Query ChromaDB with filters."""
    if not os.path.exists(CHROMA_DB_PATH):
        print(f"[Retrieve] Error: ChromaDB not found at {CHROMA_DB_PATH}. Run crawl, chunk, and ingest first.")
        return []

    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    
    try:
        collection = chroma_client.get_collection(name=collection_name)
    except Exception:
        print(f"[Retrieve] Error: Collection '{collection_name}' does not exist.")
        return []

    # Get query embedding
    query_vector = get_embedding(query_text)
    if not query_vector:
        print("[Retrieve] Error: Failed to generate query embedding.")
        return []

    # Build metadata filter
    where_filter = {}
    if max_version:
        where_filter["max_version"] = max_version
    if domain:
        where_filter["domain"] = domain

    # Query ChromaDB
    try:
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=n_results,
            where=where_filter if where_filter else None
        )
        return results
    except Exception as e:
        print(f"[Retrieve] Error querying collection: {e}")
        return []


def format_results(results):
    """Print results cleanly."""
    if not results or not results.get("documents") or not results["documents"][0]:
        print("\n[Retrieve] No matching documents found.")
        return

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0] if "distances" in results else [0.0] * len(documents)

    print(f"\n[Retrieve] Found {len(documents)} results:")
    for idx, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
        print(f"\n--- Result #{idx + 1} (Score/Distance: {dist:.4f}) ---")
        # Print metadata key-values
        meta_str = ", ".join([f"{k}: {v}" for k, v in meta.items()])
        print(f"Metadata: {meta_str}")
        print("Content:")
        print(doc)
        print("-" * 40)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query Max MSP assistant local vector store")
    parser.add_argument("query", type=str, help="The query/search term")
    parser.add_argument("--collection", type=str, default="max8_docs", help="ChromaDB collection to query")
    parser.add_argument("--domain", type=str, choices=["max", "msp", "m4l"], help="Filter by domain (max, msp, m4l)")
    parser.add_argument("--version", type=str, default="8", help="Filter by Max version")
    parser.add_argument("--results", type=int, default=5, help="Number of results to return")
    
    args = parser.parse_args()

    print(f"Querying vector store for: '{args.query}' (domain: {args.domain or 'any'}, version: {args.version})")
    results = query_vector_db(
        query_text=args.query,
        collection_name=args.collection,
        domain=args.domain,
        max_version=args.version,
        n_results=args.results
    )
    
    format_results(results)
