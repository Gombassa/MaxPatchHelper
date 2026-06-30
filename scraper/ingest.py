import os
import sys
import json
import uuid
import argparse
import requests
import chromadb

# Add assistant subdirectory to path so config.py is the single source of truth
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assistant"))
from config import CHUNKS_FILE, CHROMA_DB_PATH, OLLAMA_EMBED_URL, OLLAMA_BATCH_EMBED_URL, EMBED_MODEL


def get_embedding(text, model=EMBED_MODEL):
    """Call local Ollama endpoint to generate vector embedding (fallback)."""
    try:
        response = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": model, "prompt": text},
            timeout=15
        )
        if response.status_code == 200:
            return response.json().get("embedding")
        else:
            print(f"[Ollama] Error: HTTP {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"[Ollama] Error generating embedding: {e}")
        return None


def get_embeddings_batch(texts, model=EMBED_MODEL):
    """Call local Ollama batch embed endpoint to get vectors for a list of texts."""
    try:
        response = requests.post(
            OLLAMA_BATCH_EMBED_URL,
            json={"model": model, "input": texts},
            timeout=45
        )
        if response.status_code == 200:
            return response.json().get("embeddings")
        else:
            print(f"[Ollama] Batch Error: HTTP {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"[Ollama] Error generating batch embeddings: {e}")
        return None


def ingest_chunks(collection_name="max8_docs", batch_size=50):
    """Load chunks, embed them using sequential batching via /api/embed, and save to ChromaDB."""
    if not os.path.exists(CHUNKS_FILE):
        print(f"[Ingest] Error: Chunks file not found at {CHUNKS_FILE}. Did you run chunk.py?")
        return

    with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
        chunks = json.load(f)

    print(f"[Ingest] Loaded {len(chunks)} chunks from {CHUNKS_FILE}")

    # Divide chunks into batches
    batches = []
    for i in range(0, len(chunks), batch_size):
        batches.append(chunks[i:i + batch_size])
        
    print(f"[Ingest] Created {len(batches)} batches of size {batch_size}")

    # Initialize ChromaDB
    print(f"[Ingest] Initializing ChromaDB persistent client at {CHROMA_DB_PATH}...")
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = chroma_client.get_or_create_collection(name=collection_name)

    success_count = 0
    
    # Process batches sequentially
    print(f"[Ingest] Generating embeddings and ingesting into ChromaDB...")
    for idx, batch_chunks in enumerate(batches):
        texts = [c["text"] for c in batch_chunks]
        
        # Try batch API
        vectors = get_embeddings_batch(texts)
        
        # Fallback to sequential if batch fails
        if not vectors:
            print(f"[Ingest] Batch {idx + 1} failed, falling back to sequential embeddings...")
            vectors = []
            for text in texts:
                vec = get_embedding(text)
                vectors.append(vec)
                
        ids = []
        embeddings = []
        metadatas = []
        documents = []
        
        for chunk, vector in zip(batch_chunks, vectors):
            if not vector:
                continue
            
            # Clean metadata
            clean_metadata = {}
            for k, v in chunk["metadata"].items():
                if isinstance(v, (str, int, float, bool)):
                    clean_metadata[k] = v
                else:
                    clean_metadata[k] = str(v)
                    
            ids.append(str(uuid.uuid4()))
            embeddings.append(vector)
            metadatas.append(clean_metadata)
            documents.append(chunk["text"])
            
        if ids:
            try:
                collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    documents=documents
                )
                success_count += len(ids)
                print(f"[Ingest] Stored batch {idx + 1}/{len(batches)} ({success_count}/{len(chunks)} chunks)")
            except Exception as e:
                print(f"[Ingest] Error adding batch {idx + 1} to ChromaDB: {e}")
        else:
            print(f"[Ingest] Batch {idx + 1} returned empty embeddings.")

    print(f"[Ingest] Ingestion completed. Successfully stored {success_count} chunks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest documentation chunks into ChromaDB")
    parser.add_argument("--collection", type=str, default="max8_docs", help="ChromaDB collection name")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for embeddings insertion")
    args = parser.parse_args()

    ingest_chunks(collection_name=args.collection, batch_size=args.batch_size)
