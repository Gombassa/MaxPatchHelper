# Max MSP AI Assistant Implementation Plan

Implement a local, RAG-enabled AI assistant for Cycling '74 Max MSP (v8 & v9) and Max for Live (M4L) with guided build, explanation, and patch generation capabilities.

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

### Phase 3 — Complete
- **Pydantic Validator (`assistant/validate.py`)**: Built validation models checking unique IDs, port bounds, unique M4L UI varnames/longnames, and M4L device requirements.
- **Strict Port Count Table**: Configured `TRUSTED_PORT_COUNTS` to determine port counts for 25+ core Max/MSP/M4L objects.
- **Inlet Conflict Check**: Added checks to prevent control rate (toggle/number) and signal rate sharing the same inlet of `dac~`.
- **Validation Retry Loop (`assistant/generate.py`)**: Cap of 3 retry attempts, feeding validation errors back to the model.
- **Stateful Guided REPL (`assistant/guided.py`)**: Steps through goal, object, line routing, verifying gitignore, and appending Technical Summaries to idioms layer.

---

## User Decisions & Alignments

### Q1: VRAM Contention & Hardware Limitations
- **Decision**: GTX 1060 6GB has 6GB VRAM. qwen2.5-coder:14b requires ~9GB and cannot run on GPU. Hardware reality requires qwen2.5-coder:7b as the permanent generate model on this machine, not a temporary fallback.
- **Approach**: We will proceed with `qwen2.5-coder:7b` as the permanent generate model with an 8K context window (`GENERATE_CONTEXT_WINDOW`).

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

---

## Phase 4 — Web Application Development

Build a unified web interface consisting of a FastAPI backend and a React + Vite frontend.

### Phase 4 — In Progress

- **FastAPI backend complete**: `/api/health`, `/api/retrieve`, `/api/validate`, `/api/explain` (SSE), `/api/generate` (SSE), `/api/ws/guided` (WebSocket)
- **React + Vite frontend scaffolded and built successfully** (248ms, zero errors)
- **Four tabs implemented**: Explainer, Generator, Guided Builder, Doc Explorer
- **WebSocket lazy-open confirmed**: `GuidedBuilder` only connects on "Start Guided Session" button click
- **`VITE_API_URL` and `VITE_WS_URL` configurable** via `ui/.env` (gitignored)
- **Design tokens centralised** in `tokens.css` at `:root` level

### Phase 4 — Remaining: End-to-End Verification (not yet run)

- **Start backend**: `uvicorn assistant.server:app --reload --port 8000`
- **Start frontend**: `cd ui && npm run dev`
- **Verify health badge** shows green in UI
- **Verify Explain tab** streams response to "what does cycle~ do"
- **Verify Generator tab** produces valid patch for "a sine wave generator"
- **Verify Guided Builder WebSocket** connects on button click and accepts a message
- *Only after all four pass: approve commit and push*

### 1. FastAPI Backend Server (`assistant/server.py`)
Expose the assistant logic through REST and WebSocket endpoints:
- **`GET /api/health`**: Lightweight health status endpoint returning backend version and status. Essential for client-side connection states.
- **`POST /api/retrieve`**: Search vector DB documents.
- **`POST /api/explain`**: Explains a Max/MSP question. Supports real-time token streaming using Server-Sent Events (SSE).
- **`POST /api/generate`**: Generates a patch with a 3-attempt validation loop. Streams progress/attempts and outputs final `.maxpat` JSON.
- **`POST /api/validate`**: Validates a patch JSON.
- **`WS /api/ws/guided`**: Binds a stateful multi-turn WebSocket connection for the Guided Builder:
  - **State Management**: Guided builder state (conversation history, spec spec details, etc.) lives in-memory server-side per active connection. 
  - **Graceful Disconnection**: If the WebSocket drops, the connection handler intercepts the `WebSocketDisconnect` exception and safely cleans up memory. The backend will *never* attempt to write summaries or run the learning stage on unexpected connection loss, completely eliminating any risk of corrupting `personal_idioms.md`.
  - **User Commands**: Only explicit `"exit"` messages from the client trigger the technical learning summary and idioms append.

### 2. React + Vite Frontend (`ui/`)
A responsive, high-performance, dark-themed Single Page Application:
- **Design Tokens (HSL Dark System)**:
  - Defined strictly as CSS custom properties at the `:root` level in `ui/src/index.css`.
  - Background: Deep slate (`--bg-primary: #0d0f12`), dark surfaces (`--bg-surface: #14171c`), border colors (`--border-color: #21262d`).
  - Text colors: High-contrast light gray (`--text-primary: #f3f4f6`) and medium gray (`--text-secondary: #8b949e`).
  - Accent colors: Electric indigo (`--accent-primary: #6366f1` / `--accent-secondary: #4f46e5`).
  - Font families: `Outfit` and `Inter` from Google Fonts.
- **SSE Reconnection Management**:
  - The React client uses native `EventSource` wrappers with exponential backoff timers.
  - On sudden drop, it handles retry connection gracefully, presenting a clear reconnecting spinner without clearing already-streamed code/text blocks.
- **Tabbed Layout**:
  - **Q&A Explain Tab**: Interactive chat panel with markdown parsing and source document card sidebar.
  - **Patch Generator Tab**: Prompt entry, live logging of validator attempts (console output), and a read-only code display with download/copy actions.
  - **Guided Builder Tab**: Chat screen with a real-time floating sidebar showing the "CURRENT PATCH SPECIFICATION".
  - **Doc Explorer Tab**: General search panel across scraped Max 8/9 refpages.

---

## User Review Required

We are using a dark-theme glassmorphism design with Outfit/Inter typography and electric purple/indigo accents for a premium feel. We will avoid Tailwind CSS and write clean Vanilla CSS to ensure maximum performance and precise animations.

---

## Proposed Changes

We will implement the codebase in the following structure under the workspace root:

### scraper
*Already implemented and checked in.*

### assistant

#### [MODIFY] [config.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/config.py)
Update to configure backend host/port, CORS origins, and web server parameters.

#### [NEW] [server.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/server.py)
FastAPI backend server exposing REST and WebSocket endpoints (like `/api/explain`, `/api/generate`, `/api/ws/guided`) for the React frontend.

### ui

#### [NEW] [ui/](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/ui)
Vite-based React frontend project directory.

---

## Verification Plan

### Automated Tests
- Test WebSocket endpoints and REST endpoints in a new `tests/test_server.py`.
- Verify CORS config.

### Manual Verification
- Start FastAPI server: `python assistant/server.py` or `uvicorn assistant.server:app --reload`.
- Start Vite React UI: `npm run dev` inside `ui/`.
- Verify real-time explanation streaming in Q&A tab.
- Verify live-logging of validator loops and successful patch output in Generator tab.
- Run a full interactive guided spec design session and compile/generate the final patch.
