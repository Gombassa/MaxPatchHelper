import os

# Base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ChromaDB
CHROMA_DB_PATH = os.path.join(DATA_DIR, "chroma")

# References
LOM_REF_PATH = os.path.join(DATA_DIR, "lom_reference.json")
INDEX_PATH = os.path.join(DATA_DIR, "inlet_outlet_index.json")

# Scraper / ingest pipeline
RAW_WEB_DIR = os.path.join(DATA_DIR, "raw", "web")
RAW_LOCAL_DIR = os.path.join(DATA_DIR, "raw", "local")
CHUNKS_FILE = os.path.join(DATA_DIR, "chunks.json")

# Ollama URLs
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embeddings"
OLLAMA_BATCH_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embed"

# Models
CLASSIFY_MODEL = "mistral:latest"
EXPLAIN_MODEL = "mistral:latest"
EMBED_MODEL = "nomic-embed-text"

# Context Windows (num_ctx)
CLASSIFY_CONTEXT_WINDOW = 2048
EXPLAIN_CONTEXT_WINDOW = 4096

