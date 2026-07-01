import os
import json
import asyncio
import queue
import threading
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from assistant.retrieve import query_vector_db
from assistant.explain import explain_query, load_inlet_outlet_index, load_lom_schema, detect_m4l_context
from assistant.validate import validate_patch
from assistant.config import (
    EXPLAIN_MODEL,
    EXPLAIN_CONTEXT_WINDOW
)

app = FastAPI(title="Max MSP AI Assistant API", version="1.0.0")

# Enable CORS for frontend integration (Vite dev server default: http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------
# Pydantic Schemas
# ----------------------------------------------------
class RetrieveRequest(BaseModel):
    query: str
    domain: Optional[str] = None
    version: Optional[str] = "8"
    results: Optional[int] = 3

class ExplainRequest(BaseModel):
    query: str
    domain: Optional[str] = None
    version: Optional[str] = "8"

class ValidateRequest(BaseModel):
    patch: Dict[str, Any]
    domain: Optional[str] = None
    device_type: Optional[str] = None

# ----------------------------------------------------
# Endpoints
# ----------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Lightweight health check endpoint for frontend connection management."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "models": {
            "explain": EXPLAIN_MODEL
        }
    }

@app.post("/api/retrieve")
async def retrieve_documents(req: RetrieveRequest):
    """Query the vector database directly for relevant chunks."""
    try:
        results = query_vector_db(
            query_text=req.query,
            domain=req.domain,
            max_version=req.version,
            n_results=req.results
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/validate")
async def validate_max_patch(req: ValidateRequest):
    """Run validation checks on the provided patch JSON."""
    try:
        val_result = validate_patch(
            patch_data=req.patch,
            domain_override=req.domain,
            device_type_override=req.device_type
        )
        return val_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/explain")
async def explain_patch_query(req: ExplainRequest, request: Request):
    """Explain a Max/MSP concept or object query, streaming the explanation via SSE."""
    async def sse_generator():
        q = queue.Queue()
        stop_event = threading.Event()

        def run_explain():
            try:
                # Callback pushes tokens to the queue
                def callback(token: str):
                    q.put(token)

                explain_query(
                    query_text=req.query,
                    domain=req.domain,
                    version=req.version,
                    model=EXPLAIN_MODEL,
                    callback=callback,
                    stream_to_stdout=False,
                    stop_event=stop_event
                )
            except Exception as e:
                q.put(e)
            finally:
                q.put(None)

        threading.Thread(target=run_explain, daemon=True).start()

        try:
            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    print("[Explain] Client disconnected. Aborting explanation.")
                    stop_event.set()
                    break

                try:
                    token = q.get_nowait()
                    if token is None:
                        break
                    if isinstance(token, Exception):
                        yield f"data: {json.dumps({'error': str(token)})}\n\n"
                        break
                    yield f"data: {json.dumps({'token': token})}\n\n"
                except queue.Empty:
                    await asyncio.sleep(0.01)
        finally:
            print("[Explain] Generator stream exited. Setting stop event.")
            stop_event.set()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(sse_generator(), media_type="text/event-stream", headers=headers)

# ----------------------------------------------------
# Main Launcher
# ----------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
