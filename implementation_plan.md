# Max MSP AI Assistant Implementation Plan

Implement a local, RAG-enabled AI assistant for Max MSP (v8 & v9) and Max for Live (M4L) with guided build, explanation, and patch generation capabilities.

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
- **Approach**: The backend modules will be designed with clean API endpoints to allow seamless integration with a React frontend.

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

#### [NEW] [assistant.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant.py)
Core CLI entry point routing mode flags (`--mode`, `--version`, `--domain`).

#### [NEW] [retrieve.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/retrieve.py)
Handles ChromaDB collection queries with metadata filtering.

#### [NEW] [classify.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/classify.py)
LLM pre-prompt classifier for query intent.

#### [NEW] [validate.py](file:///c:/Users/robin/Documents/GitHub/MaxPatchHelper/assistant/validate.py)
Custom `.maxpat` JSON validator.

---

## Verification Plan

### Automated Tests
- Run `pytest` on individual components (scraper, chunker, classifier, validator).
- Validation tests on 10 sample `.maxpat` files to ensure syntax checks work.

### Manual Verification
- Verify retrieval query accuracy for Max/MSP objects and Live API components.
- Inspect generated `.maxpat` outputs in Max 8.
