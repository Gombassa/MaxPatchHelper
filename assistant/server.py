import os
import sys
import json
import asyncio
import functools
import queue
import threading
import requests
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Add assistant directory to path if running directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from retrieve import query_vector_db
from explain import explain_query, load_inlet_outlet_index, load_lom_schema, detect_m4l_context
from generate import generate_patch
from validate import validate_patch
from guided import (
    load_personal_idioms,
    check_gitignore_for_idioms,
    append_to_personal_idioms,
    GUIDED_SYSTEM_PROMPT,
    ENRICHED_USER_TEMPLATE
)
from config import (
    OLLAMA_CHAT_URL,
    GUIDED_MODEL,
    GUIDED_CONTEXT_WINDOW,
    EXPLAIN_MODEL,
    EXPLAIN_CONTEXT_WINDOW,
    GENERATE_MODEL,
    GENERATE_CONTEXT_WINDOW
)

app = FastAPI(title="Max MSP AI Assistant API", version="1.0.0")

# Enable CORS for frontend integration (Vite dev server default: http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

class GenerateRequest(BaseModel):
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
            "explain": EXPLAIN_MODEL,
            "generate": GENERATE_MODEL,
            "guided": GUIDED_MODEL
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

@app.post("/api/generate")
async def generate_max_patch(req: GenerateRequest, request: Request):
    """Generate a Max/MSP patch JSON based on a prompt, streaming attempts, logs, and final patch via SSE."""
    async def sse_generator():
        q = queue.Queue()
        stop_event = threading.Event()

        def run_generate():
            try:
                # Callback receives structured dictionaries
                def callback(event: dict):
                    q.put(event)

                generate_patch(
                    query_text=req.query,
                    domain=req.domain,
                    version=req.version,
                    model=GENERATE_MODEL,
                    callback=callback,
                    stream_to_stdout=False,
                    stop_event=stop_event
                )
            except Exception as e:
                q.put(e)
            finally:
                q.put(None)

        threading.Thread(target=run_generate, daemon=True).start()

        try:
            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    print("[Generate] Client disconnected. Aborting generation.")
                    stop_event.set()
                    break

                try:
                    event = q.get_nowait()
                    if event is None:
                        break
                    if isinstance(event, Exception):
                        yield f"data: {json.dumps({'type': 'error', 'content': [str(event)]})}\n\n"
                        break
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    await asyncio.sleep(0.01)
        finally:
            print("[Generate] Generator stream exited. Setting stop event.")
            stop_event.set()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(sse_generator(), media_type="text/event-stream", headers=headers)

# ----------------------------------------------------
# WebSocket Stateful Guided Build Handler
# ----------------------------------------------------

@app.websocket("/api/ws/guided")
async def websocket_guided_build(websocket: WebSocket):
    """Stateful, real-time WebSocket connection for Guided Build Mode."""
    await websocket.accept()
    
    # Initialize connection state
    session_history: List[Dict[str, str]] = []
    domain_context = "max"
    
    try:
        # Load and send personal idioms
        idioms_text = load_personal_idioms()
        await websocket.send_json({
            "type": "status",
            "content": "[System] Guided session initialized. Loading past design history."
        })
        if idioms_text:
            await websocket.send_json({
                "type": "idioms",
                "content": idioms_text
            })
            
        await websocket.send_json({
            "type": "status",
            "content": "Welcome to Max Guided Build Mode! Describe what you want to build to get started."
        })
        
        while True:
            # Receive client message
            data = await websocket.receive_json()
            msg_type = data.get("type")
            text = data.get("text", "").strip()
            
            if not text and msg_type != "exit":
                continue
                
            if msg_type == "exit":
                # Run learning summaries and clean up
                await run_websocket_learning_stage(websocket, session_history)
                await websocket.send_json({
                    "type": "status",
                    "content": "[System] Guided session ended. Connection closing."
                })
                break
                
            elif msg_type == "generate":
                if not session_history:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Cannot generate a patch: no design specification has been discussed yet."
                    })
                    continue
                # Compile design specifications and run the generator
                await run_websocket_generation_stage(websocket, session_history, domain_context)
                continue
                
            elif msg_type == "chat":
                # Update domain context if M4L terms are used
                if detect_m4l_context(text, None):
                    domain_context = "m4l"
                    
                # RAG document retrieval
                retrieved = query_vector_db(text, domain=domain_context, n_results=3)
                context_blocks = []
                if retrieved and retrieved.get("documents") and retrieved["documents"][0]:
                    documents = retrieved["documents"][0]
                    metadatas = retrieved["metadatas"][0]
                    for idx, (doc, meta) in enumerate(zip(documents, metadatas)):
                        source_title = meta.get("title", meta.get("object_name", "Unknown Source"))
                        context_blocks.append(f"--- Chunk #{idx + 1} Source: [{source_title}] ---\n{doc}\n")
                context_text = "\n".join(context_blocks) if context_blocks else "No relevant documents found."
                
                # Structured index & LOM schema
                structured_index_text = load_inlet_outlet_index(text, context_text)
                lom_schema_text = load_lom_schema() if domain_context == "m4l" else ""
                
                # Format turn prompt — text concatenated separately to avoid .format() injection
                enriched_user_content = (
                    ENRICHED_USER_TEMPLATE.format(
                        personal_idioms_section=idioms_text,
                        structured_index_section=structured_index_text,
                        lom_schema_section=lom_schema_text,
                        context_section=context_text,
                    )
                    + f"\n\n==================================================\nUSER INPUT:\n{text}\n=================================================="
                )
                
                # Append user prompt to history
                session_history.append({"role": "user", "content": text})
                
                # Prepare LLM messages
                api_messages = [
                    {"role": "system", "content": GUIDED_SYSTEM_PROMPT}
                ] + session_history[:-1] + [
                    {"role": "user", "content": enriched_user_content}
                ]
                
                # Call LLM and stream tokens to client
                full_response = await run_websocket_llm_turn(websocket, api_messages)
                
                # Append assistant output to history
                if full_response:
                    session_history.append({"role": "assistant", "content": full_response})
                    # Extract the CURRENT PATCH SPECIFICATION section to send separately
                    await extract_and_send_spec(websocket, full_response)
                    
    except WebSocketDisconnect:
        # Handle graceful cleanup on drop, preventing file corruption
        print("[Server] Guided build WebSocket disconnected unexpectedly.")
    except Exception as e:
        print(f"[Server] WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "content": f"WebSocket server error: {e}"})
        except:
            pass

# ----------------------------------------------------
# WebSocket Helper Routines
# ----------------------------------------------------

async def run_websocket_llm_turn(websocket: WebSocket, api_messages: List[Dict[str, str]]) -> str:
    """Invokes LLM for guided build turn, pushing stream tokens to WebSocket."""
    q = queue.Queue()
    stop_event = threading.Event()

    def target(stop_event: threading.Event):
        try:
            response = requests.post(
                OLLAMA_CHAT_URL,
                json={
                    "model": GUIDED_MODEL,
                    "messages": api_messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.3,
                        "num_ctx": GUIDED_CONTEXT_WINDOW
                    }
                },
                stream=True,
                timeout=300
            )
            if response.status_code != 200:
                q.put(Exception(f"Ollama returned HTTP {response.status_code}"))
                return
            for line in response.iter_lines():
                if stop_event.is_set():
                    break
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    token = chunk.get("message", {}).get("content", "")
                    q.put(token)
        except Exception as e:
            q.put(e)
        finally:
            q.put(None)

    threading.Thread(target=target, args=(stop_event,), daemon=True).start()

    full_response = ""
    try:
        while True:
            try:
                token = q.get_nowait()
                if token is None:
                    break
                if isinstance(token, Exception):
                    await websocket.send_json({"type": "error", "content": str(token)})
                    break
                full_response += token
                await websocket.send_json({"type": "token", "content": token})
            except queue.Empty:
                await asyncio.sleep(0.01)
    finally:
        stop_event.set()

    return full_response

async def extract_and_send_spec(websocket: WebSocket, text: str):
    """Finds the 'CURRENT PATCH SPECIFICATION' section in text and pushes it to client."""
    spec_markers = [
        "CURRENT PATCH SPECIFICATION",
        "Current Patch Specification",
        "current patch specification"
    ]

    spec_start = -1
    for marker in spec_markers:
        idx = text.find(marker)
        if idx != -1:
            spec_start = idx
            break

    if spec_start != -1:
        # Move start back to capture heading formatting (e.g. ## or ###) if present
        prefix = text[:spec_start]
        heading_idx = prefix.rfind("#")
        start_pos = heading_idx if heading_idx != -1 and (spec_start - heading_idx) < 10 else spec_start
        spec_content = text[start_pos:].strip()

        await websocket.send_json({
            "type": "spec",
            "content": spec_content
        })

async def _ollama_post(payload: dict, timeout: int = 300) -> requests.Response:
    """Run a blocking requests.post to Ollama in a thread so the event loop stays free."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(requests.post, OLLAMA_CHAT_URL, json=payload, timeout=timeout)
    )


async def run_websocket_learning_stage(websocket: WebSocket, session_history: List[Dict[str, str]]):
    """Generates idioms summary at the end of the session, appending it to personal_idioms.md."""
    if not session_history:
        return

    await websocket.send_json({
        "type": "status",
        "content": "[System] Running end-of-session learning stage. Compiling idioms..."
    })

    summary_prompt = (
        "Analyze the following conversation history of a patch design session. "
        "Create a concise, bulleted Markdown summary of the following:\n"
        "1. What patch was designed/attempted (the core goal).\n"
        "2. Key design and architectural choices (e.g. object selections, signal flows, parameters, M4L components).\n"
        "3. Any lessons learned, gotchas, or reusable personal idioms discovered during the session.\n\n"
        "Keep the summary extremely concise, practical, and under 15 lines of text.\n\n"
        "Conversation History:\n"
    )
    for msg in session_history:
        role = "User" if msg["role"] == "user" else "Assistant"
        summary_prompt += f"\n[{role}]: {msg['content']}\n"

    try:
        response = await _ollama_post({
            "model": GUIDED_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a concise technical summarizer. Output a concise markdown bulleted list of lessons learned, design choices, and personal idioms from the session."
                },
                {"role": "user", "content": summary_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": GUIDED_CONTEXT_WINDOW
            }
        })

        if response.status_code == 200:
            summary_text = response.json().get("message", {}).get("content", "").strip()
            
            # Format entry
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_entry = f"### Session Summary - {timestamp}\n{summary_text}"
            
            # Write to idioms
            if check_gitignore_for_idioms():
                append_to_personal_idioms(formatted_entry)
                await websocket.send_json({
                    "type": "idioms",
                    "content": formatted_entry
                })
            else:
                await websocket.send_json({
                    "type": "status",
                    "content": "[Warning] personal_idioms.md not in .gitignore. Skipping summary write."
                })
        else:
            await websocket.send_json({
                "type": "error",
                "content": f"Failed to run summarizer: HTTP {response.status_code}"
            })
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "content": f"Error running summarizer: {e}"
        })

async def run_websocket_generation_stage(websocket: WebSocket, session_history: List[Dict[str, str]], domain: str):
    """Compiles spec and triggers generate_patch validation loops, sending results to WebSocket."""
    await websocket.send_json({
        "type": "status",
        "content": "[System] Compiling final design specifications..."
    })

    spec_prompt = (
        "Based on the conversation history below, extract and list the complete final design specifications "
        "needed to construct the patch. Detail all objects (with names, classes, attributes) and "
        "all patchline connections between them.\n\n"
        "Conversation History:\n"
    )
    for msg in session_history:
        role = "User" if msg["role"] == "user" else "Assistant"
        spec_prompt += f"\n[{role}]: {msg['content']}\n"

    spec_summary = ""
    try:
        response = await _ollama_post({
            "model": GUIDED_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a technical analyst. Extract a clear, structured list of objects and connection specifications from the conversation. Do not generate JSON, only a structured text spec list."
                },
                {"role": "user", "content": spec_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": GUIDED_CONTEXT_WINDOW
            }
        })
        if response.status_code == 200:
            spec_summary = response.json().get("message", {}).get("content", "").strip()
            await websocket.send_json({
                "type": "status",
                "content": f"[System] Design specs compiled:\n{spec_summary}"
            })
        else:
            await websocket.send_json({
                "type": "error",
                "content": f"Failed to compile specs: HTTP {response.status_code}"
            })
            return
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "content": f"Error compiling specs: {e}"
        })
        return

    # Call generate_patch and stream validation loop status
    await websocket.send_json({
        "type": "status",
        "content": f"[System] Starting patch generation using model {GENERATE_MODEL}..."
    })

    q = queue.Queue()

    def run_generate():
        try:
            def callback(event: dict):
                q.put(event)
                
            generate_patch(
                query_text=spec_summary,
                domain=domain,
                model=GENERATE_MODEL,
                callback=callback,
                stream_to_stdout=False
            )
        except Exception as e:
            q.put(e)
        finally:
            q.put(None)

    threading.Thread(target=run_generate, daemon=True).start()

    while True:
        try:
            event = q.get_nowait()
            if event is None:
                break
            if isinstance(event, Exception):
                await websocket.send_json({"type": "error", "content": str(event)})
                break
            # Send the generate event directly to WebSocket client
            await websocket.send_json(event)
        except queue.Empty:
            await asyncio.sleep(0.01)

# ----------------------------------------------------
# Main Launcher
# ----------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
