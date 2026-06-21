import os
import json
import uuid
import argparse
import requests
import chromadb

CHUNKS_FILE = "data/chunks.json"
CHROMA_DB_PATH = "data/chroma"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"


def get_embedding(text, model=EMBED_MODEL):
    """Call local Ollama endpoint to generate vector embedding."""
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
    except requests.exceptions.ConnectionError:
        print("[Ollama] Connection Error: Is Ollama running on http://localhost:11434?")
        return None
    except Exception as e:
        print(f"[Ollama] Error generating embedding: {e}")
        return None


def ingest_chunks(collection_name="max8_docs", batch_size=20):
    """Load chunks, embed them, and save to ChromaDB."""
    if not os.path.exists(CHUNKS_FILE):
        print(f"[Ingest] Error: Chunks file not found at {CHUNKS_FILE}. Did you run chunk.py?")
        return

    with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
        chunks = json.load(f)

    print(f"[Ingest] Loaded {len(chunks)} chunks from {CHUNKS_FILE}")

    # Initialize ChromaDB
    print(f"[Ingest] Initializing ChromaDB persistent client at {CHROMA_DB_PATH}...")
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = chroma_client.get_or_create_collection(name=collection_name)

    # Process in batches
    ids = []
    embeddings = []
    metadatas = []
    documents = []
    
    count = 0
    success_count = 0

    print(f"[Ingest] Ingesting into collection '{collection_name}'...")
    for chunk in chunks:
        text = chunk["text"]
        metadata = chunk["metadata"]
        
        # ChromaDB metadata values must be simple types (str, int, float, bool)
        # Flatten dictionary or clean any complex types if necessary
        clean_metadata = {}
        for k, v in metadata.items():
            if isinstance(v, (str, int, float, bool)):
                clean_metadata[k] = v
            else:
                clean_metadata[k] = str(v)
        
        # Get embedding
        vector = get_embedding(text)
        if not vector:
            print(f"[Ingest] Skipping chunk due to embedding failure.")
            continue
            
        ids.append(str(uuid.uuid4()))
        embeddings.append(vector)
        metadatas.append(clean_metadata)
        documents.append(text)
        
        count += 1
        success_count += 1

        # Check if we should insert the batch
        if len(ids) >= batch_size:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )
            print(f"[Ingest] Stored batch of {len(ids)} chunks ({success_count}/{len(chunks)})")
            # Reset batch buffers
            ids, embeddings, metadatas, documents = [], [], [], []

    # Insert any remaining chunks
    if ids:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )
        print(f"[Ingest] Stored final batch of {len(ids)} chunks ({success_count}/{len(chunks)})")

    print(f"[Ingest] Ingestion completed. Successfully stored {success_count} chunks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest documentation chunks into ChromaDB")
    parser.add_argument("--collection", type=str, default="max8_docs", help="ChromaDB collection name")
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size for embeddings insertion")
    args = parser.parse_args()

    ingest_chunks(collection_name=args.collection, batch_size=args.batch_size)
