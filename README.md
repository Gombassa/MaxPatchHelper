# Max MSP AI Assistant (MaxPatchHelper)

A local, RAG-enabled AI assistant for Cycling '74 Max MSP (v8) and Max for Live (M4L) that provides interactive explanations and documentation search.

---

## Architecture

The Max MSP AI Assistant is structured as a two-tier application consisting of a local FastAPI backend powered by Ollama and a responsive React SPA frontend. At the data layer, a polite web crawler/scraper extracts, chunks, and embeds Cycling '74 legacy docs/API reference pages into a local ChromaDB vector database, which is dynamically augmented by structured static inlet/outlet indexes and a Live Object Model (LOM) schema. The core assistant logic retrieves relevant context and produces RAG-grounded explanations (`mistral:latest`) of Max/MSP and M4L objects, arguments, attributes, and Live Object Model (LOM) paths. The FastAPI web server exposes this through REST endpoints and an SSE-streamed explain endpoint, bridging the backend directly to the Vite-powered React frontend. The codebase also carries a standalone patch validator (`assistant/validate.py`) and object reference data (`assistant/object_reference.py`) — neither is wired into any active feature today; both are foundation kept in place for a planned future patch-analyzer capability.

---

## Features

- **Q&A Explainer**: RAG-augmented explanations of Max MSP objects, arguments, attributes, and Live Object Model (LOM) paths.
- **Documentation Explorer**: Interactive lookup interface for searching and viewing scraped document records and indexes.

---

## Local Setup & Implementation

Follow these steps to run the helper locally as a command-line tool or as a web application.

### Prerequisites

- **Python**: Version 3.10 or higher.
- **Node.js**: Version 18 or higher (with `npm`).
- **Ollama**: Installed and running locally.

### 1. Ollama Model Setup

The assistant depends on local models hosted on Ollama. Run the following commands to pull the necessary models:

```bash
# Embeddings model used for RAG retrieval
ollama pull nomic-embed-text

# LLM used for explanation
ollama pull mistral
```

Ensure Ollama is running in the background (typically at `http://localhost:11434`).

### 2. Repository Ingestion & Backend Setup

Clone this repository and set up a Python virtual environment:

```bash
# Clone the repository
git clone https://github.com/Gombassa/MaxPatchHelper.git
cd MaxPatchHelper

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install Python requirements
pip install -r requirements.txt

# Install the project itself in editable mode (required for assistant/* imports to resolve)
pip install -e .
```

#### Running Ingestion (Optional)
If you want to re-ingest the Max documentation into the local Chroma database:
```bash
# 1. Scrape documentation (downloads to data/raw/web/)
python scraper/crawl.py

# 2. Chunk documents using tiktoken tokenizer
python scraper/chunk.py

# 3. Embed and store chunks in local ChromaDB
python scraper/ingest.py
```

### 3. Frontend UI Setup

Install the Node modules for the React + Vite single-page application:

```bash
cd ui
npm install
```

Configure the application environment variables by creating a `ui/.env` file:
```env
VITE_API_URL=http://localhost:8000/api
```

This variable must include the full path prefix (`/api`) — `api.js` uses it as a complete endpoint URL, not a bare host, so this isn't optional or freely customizable. (`VITE_WS_URL` is no longer used — it was only read by the Guided Spec Builder's WebSocket client, which was removed along with that feature.)

---

## Usage

You can interact with the helper either via the Command Line Interface (CLI) or the Web UI.

### Option A: Command Line Interface (CLI)

Activate your Python virtual environment and run the main entrypoint:

```bash
# Display helper arguments
python assistant.py --help

# Query Explainer Mode
python assistant.py --mode explain "how do I use cycle~"
```

### Option B: Web Application (FastAPI + React)

To experience the full UI dashboard with the Explainer and Doc Explorer panels, run the backend and frontend servers:

1. **Start the FastAPI Backend**:
   From the repository root (with `.venv` active):
   ```bash
   python assistant/server.py
   ```
   *(Alternative: `uvicorn assistant.server:app --reload --port 8000`)*

2. **Start the Vite Dev Server**:
   From the `ui/` directory:
   ```bash
   npm run dev
   ```

3. **Access the App**:
   Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Codebase Reference

- [assistant.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant.py): Primary command line interface entrypoint.
- [assistant/config.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/config.py): Global configurations including LLM model settings, paths, and server configurations.
- [assistant/server.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/server.py): FastAPI backend providing REST endpoints (health, retrieve, validate, explain). No WebSocket routes remain — the Guided Spec Builder's WebSocket channel was removed along with that feature.
- [assistant/validate.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/validate.py): Syntax rules, port restrictions, and connection sanity checks for submitted Max patches. Standalone — kept as foundation for a planned future patch-analyzer feature.
- [assistant/object_reference.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/object_reference.py): Max object maxclass conventions and fixed inlet/outlet counts. Not yet used by any active feature — prep for the same planned patch-analyzer feature.
- [scraper/crawl.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/scraper/crawl.py): Web crawler for scraping legacy Cycling '74 documentation and API references.
- [scraper/ingest.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/scraper/ingest.py): Vector embedding generator and ingestion script for ChromaDB.
- [requirements.txt](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/requirements.txt): Python dependency file.
- [ui/package.json](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/ui/package.json): React UI configuration and dependencies.
