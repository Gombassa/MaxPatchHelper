# Max MSP AI Assistant Implementation Plan

Implement a local, RAG-enabled AI assistant for Max MSP (v8 & v9) and Max for Live (M4L) with guided build, explanation, and patch generation capabilities.

## Progress Summary

### Phase 1 — Complete
- **Scrape & Chunk**: Scraped 842 unique valid pages of documentation and reference tables, chunking them to 21,498 chunks using `tiktoken`.
- **Embed & Ingest**: Generated vector embeddings via `nomic-embed-text` and ingested chunks into local ChromaDB `max8_docs` collection.
- **Performance Note**: Ingestion took ~3 hours due to unbatched embedding calls. We must fix batching before re-ingesting for Max 9.
- **Verification**: Verified that exact-match `cycle~` retrieval and general M4L tempo/LOM retrieval both return correct results.

### Phase 2 — Complete
- **Intent Classifier**: LLM pre-prompt classifier (`mistral:latest`, zero temperature, 1-token output) routes user queries to `EXPLAIN`, `GENERATE`, or `GUIDED` modes.
- **Streaming & API**: Real-time token streaming to stdout enabled via `stream=True` and a callback parameter ready for FastAPI Server-Sent Events (SSE).
- **Retrieval Window**: Configured `n_results=3` for general queries and forced `n_results=6` for exact-match object reference pages.
- **Structured Index**: Compiled `inlet_outlet_index.json` containing 20 core objects (including `cycle~` and `live.path`).
- **Second-Pass Index Injection**: After ChromaDB retrieval, the query and chunk texts are scanned for known object names, and matching index entries are injected automatically. This fixes cases where the user does not name the object explicitly.
- **Context Size**: Set `num_ctx: 8192` in Ollama options and moved it to `config.py` as a configurable per-mode value (`explain` = 8192, `generate` = 16384).
- **Chat API Segregation**: Refactored LLM connection to use Ollama's native `/api/chat` instead of `/api/generate`, segregating system rules and document contexts into separate roles.

### Known Gaps to Address Before Phase 3
1. **Index Coverage**: `inlet_outlet_index.json` currently only covers 20 core objects. Build a parser to auto-populate from `data/raw/` scraped pages.
2. **Missing M4L UI Objects**: Key M4L UI objects (e.g., `live.dial`, `live.slider`, `live.numbox`, `live.button`, `live.thisdevice`, `live.banks`, `live.remote~`) are not yet fully populated in the index.
3. **Data Git-Ignoring**: Ensure `data/inlet_outlet_index.json` and any generated data files are git-ignored, keeping only generator scripts in the repository.

---

## User Decisions & Alignments

### Q1: VRAM Contention with SoundAgent
- **Decision**: SoundAgent (audio analysis and tagging stack) can be gated and remains dormant most of the time. It will not compete for GPU resources during active MaxPatchHelper sessions.
- **Approach**: We will proceed with `qwen2.5-coder:14b` as the primary generator model.

### Q2: Scraping Restrictions & Rate-Limiting
- **Decision**: Implement a polite crawler with rate-limiting pauses. 
- **Approach**: We will also search for local Max installation directories to ingest local help files and reference documentation directly, minimizing web scraping traffic.

### Q3: Guided Build Context Management
- **Decision**: Implement an end-of-session **learning stage** to summarize progress, choices, and lessons learned.
- **Approach**: This summary will be appended to the personal idioms/session history layer. Future sessions will load these summaries rather than raw, verbose history, keeping the context window compact and efficient.

### Q4: Scraping Live Object Model (LOM) — Scraper vs. Static JSON
- **Comparison**:
  - **Dynamic Scraping of LOM Tables**:
    - *Pros*: Stays up-to-date automatically if Cycling '74/Ableton updates the online API reference.
    - *Cons*: High fragility (layout changes break parsing) and noisy/imprecise chunking of tabular structures.
  - **Static JSON Schema (Recommended)**:
    - *Pros*: Extremely clean, structured, and deterministic. The LOM hierarchy is stable and changes very rarely (only across major Ableton versions like Live 11 to 12).
    - *Cons*: Requires manual initial setup or manual updates for new Live releases.
- **Approach**: We recommend using a static, hand-curated JSON schema for the LOM hierarchy to guarantee exact path resolution, supplemented by the polite scraper for prose documentation pages.

### Q5: Max vs. MSP Disambiguation
- **Decision**: In Max MSP, audio rate (MSP) objects are explicitly distinguished from control rate (Max) objects by their `~` suffix (e.g., `delay` vs `delay~`).
- **Approach**: The indices will treat them as completely distinct object classes. No complex domain classification is required for these; standard exact-match lookups on the symbol name will resolve to the correct object documentation.

### Q6: M4L Device Validation
- **Decision**: Use a local mockup/static ruleset for validation of device types, object linkages, and required tags.
- **Approach**: Real-world functional testing of LOM paths inside Live remains a manual step for Phase 3.

### Q7: UI Framework
- **Decision**: We will build the user interface using **React** instead of Streamlit in Phase 4.
- **Approach**: All assistant core modules (`retrieve.py`, `explain.py`, `generate.py`, `guided.py`) will be structured as importable Python functions rather than standalone CLI scripts. In Phase 4, we will implement a **FastAPI backend layer** (`server.py`) to expose these functions as REST and WebSocket API endpoints, serving as the bridge to the React frontend.

### MCP Bridge (Model Context Protocol)
- **Decision**: Deferred to Phase 5.
- **Approach**: An MCP server bridge to expose this assistant to external agents is out of scope for v1. Revisit this in Phase 5 after the React UI is stable.

### Repo vs. Local Storage
- **Decision**: Keep private and dynamically generated data out of Git.
- **Approach**: The vector store (`data/chroma/`), raw scraped documentation (`data/raw/` and `data/chunks.json`), example templates (`data/example_patches/`), personal idioms (`data/personal_idioms.md`), the static LOM schema (`data/lom_reference.json`), and any private `.maxpat` files are strictly local and ignored via `.gitignore`. Only the scraper/ingestion scripts, retrieval CLI, and general configuration are stored in the repository.

## Phase 1 Scaling & Scaffolding Refinements

To scale Phase 1 from a 5-page proof-of-concept to the full Cycling '74 corpus:

### 1. Crawl Scope & Page Count Estimation
- **Target**: The full Max 8 object refpages, tutorials, vignettes, and M4L API documentation comprises approximately **600 to 800 pages** (excluding Jitter, which is out of scope).
- **Refinement (Dry Run Verified)**: A dry run crawl verified exactly **842 unique valid pages** matching the filters, excluding Jitter. This will yield between **10,000 and 12,000 chunks** after tokenizer-aware splitting.

### 2. URL Link Filtering
- **Issue**: The current scraper follows *any* link matching `docs.cycling74.com`, which leads to infinite crawls of forum threads, search pages, or unrelated versions.
- **Refinement**: We restrict the crawler to follow links matching the patterns:
  - `docs.cycling74.com/legacy/max8/refpages/`
  - `docs.cycling74.com/legacy/max8/tutorials/`
  - `docs.cycling74.com/legacy/max8/vignettes/`
  - `docs.cycling74.com/apiref/` (for Live API references)
  - With explicit exclusion rules rejecting files starting with `jit.` or paths containing `jitter`.

### 3. Batching & Ingest Optimization (Ollama scale-up)
- **Issue**: Processing 10,000 chunks sequentially at 2.3 seconds per chunk would take **~6.4 hours**.
- **Refinement**:
  - Update `scraper/ingest.py` to use Ollama's batch endpoint `/api/embed` (passing a list of inputs in a single HTTP request instead of individual `/api/embeddings` requests).
  - Process batches sequentially (without multithreading) to avoid thread context-overhead on a single-GPU setup where Ollama processes requests serially anyway. This avoids downstream technical debt while capturing the full HTTP round-trip batch win.
  - This reduces estimated ingest time from ~5 hours to **10–15 minutes**.

---

## Proposed Changes

We will implement the codebase in the following structure under the workspace root:

### scraper

#### [NEW] [crawl.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/scraper/crawl.py)
Polite scraper to crawl Cycling '74 legacy docs and Live API reference, with support for scanning local Max help/ref directories.

#### [NEW] [chunk.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/scraper/chunk.py)
Tokenizer and chunker using `tiktoken`.

#### [NEW] [ingest.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/scraper/ingest.py)
Embeds and loads chunks into ChromaDB collections.

### assistant

#### [NEW] [config.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/config.py)
Centralizes assistant configuration parameters (models, endpoints, URLs, and context window sizes per mode).

#### [NEW] [assistant.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant.py)
Core CLI entry point routing mode flags (`--mode`, `--version`, `--domain`).

#### [NEW] [retrieve.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/retrieve.py)
Handles ChromaDB collection queries with metadata filtering.

#### [NEW] [classify.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/classify.py)
LLM pre-prompt classifier for query intent.

#### [NEW] [validate.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/validate.py)
Custom `.maxpat` JSON validator.

#### [NEW] [server.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/server.py)
FastAPI backend server exposing REST and WebSocket endpoints (like `/explain`, `/generate`, `/guided`) for the React frontend.

---

## Verification Plan

### Automated Tests
- Run `pytest` on individual components (scraper, chunker, classifier, validator).
- Validation tests on 10 sample `.maxpat` files to ensure syntax checks work.

### Manual Verification
- Verify retrieval query accuracy for Max/MSP objects and Live API components.
- Inspect generated `.maxpat` outputs in Max 8.
