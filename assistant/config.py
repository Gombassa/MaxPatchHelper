import os

# Base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ChromaDB
CHROMA_DB_PATH = os.path.join(DATA_DIR, "chroma")

# References
LOM_REF_PATH = os.path.join(DATA_DIR, "lom_reference.json")
INDEX_PATH = os.path.join(DATA_DIR, "inlet_outlet_index.json")

# Ollama URLs
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embeddings"

# Models
CLASSIFY_MODEL = "mistral:latest"
EXPLAIN_MODEL = "mistral:latest"
GENERATE_MODEL = "qwen2.5-coder:7b"
EMBED_MODEL = "nomic-embed-text"
GUIDED_MODEL = "mistral:latest"

# Context Windows (num_ctx)
CLASSIFY_CONTEXT_WINDOW = 2048
EXPLAIN_CONTEXT_WINDOW = 8192
GENERATE_CONTEXT_WINDOW = 8192
GUIDED_CONTEXT_WINDOW = 12288
