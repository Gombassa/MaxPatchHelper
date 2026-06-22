import os
import sys
import json
import requests
import re
from retrieve import query_vector_db
from config import OLLAMA_CHAT_URL, EXPLAIN_MODEL, LOM_REF_PATH, INDEX_PATH, EXPLAIN_CONTEXT_WINDOW

EXPLAIN_SYSTEM_PROMPT = """You are an expert offline AI assistant specialized in Cycling '74 Max MSP, MSP audio synthesis, and Max for Live (M4L) development.
Your goal is to answer the user's questions about Max/MSP objects, messages, signal flows, and the Live Object Model (LOM) clearly and accurately.

Follow these strict rules:
1. Ground your answers in the provided "Documentation Context" chunks.
2. If you cite information from a specific documentation chunk, mention its source (e.g. "[cycle~ Reference]" or "[MSP Polyphony Tutorial 1]").
3. If the answer cannot be confidently found in the context or if you are unsure, state: "Based on the available documentation, I am not sure about..." rather than fabricating object names, arguments, or LOM paths.
4. Never suggest Jitter video objects (starting with 'jit.') as they are explicitly out of scope.
5. If the question relates to Max for Live (M4L) or the Live API, refer to the "Live Object Model (LOM) Schema" below to provide exact, valid LOM paths and property access methods.
6. Max/MSP is a visual graphical programming language. NEVER write textual programming-style pseudo-code (e.g. `live_set.tempo = ...`) to describe Max patches. Instead, describe the solution step-by-step as a list of visual objects, message boxes, and connection flows (e.g. "1. Create a `live.path` object. 2. Create a message box containing `path live_set` and connect it to the inlet of `live.path`...").
7. Only use programming code blocks if you are explaining Javascript for the `js` object, or GenExpr for the `gen~` object.
8. Be extremely precise about inlet and message routing. Never conflate inlets (e.g., left vs. right). If an action requires a specific message format (like a `reset` message followed by a float in the left inlet), clearly distinguish it from sending a raw float (which might set frequency in the left inlet or phase in the right inlet). NEVER list a message under both inlets unless the documentation explicitly states that both inlets accept it (e.g., for `cycle~`, `reset` is accepted only in the left inlet).
9. For Max for Live (M4L) path queries involving `live.path`, always explicitly state that `live.path` must receive a `bang` message (e.g., triggered via `loadbang` or `live.thisdevice`) to resolve and output the resolved target ID before the downstream `live.observer` or `live.object` will fire or work. Surfacing this initialization step is critical as it is the most common M4L developer error.
10. If the "STRUCTURED INLET/OUTLET INDEX" section is provided for an object, you MUST prioritize its exact inlet and outlet counts and descriptions over your pre-trained weights or general knowledge. Adhere to it strictly and state the inlet/outlet structure exactly as defined there.
"""

EXPLAIN_PROMPT_TEMPLATE = """{structured_index_text}

==================================================
DOCUMENTATION CONTEXT:
{context_text}
==================================================

{lom_schema_text}

USER QUERY:
{query}

CRITICAL: If a "STRUCTURED INLET/OUTLET INDEX" is provided above for the object(s) in the query, you MUST use its exact inlet and outlet counts and descriptions. Do NOT hallucinate other inlets/outlets or rely on pre-trained weights or conflicting documentation context. State the inlets and outlets exactly as defined in the index.

EXPLANATION:"""

def load_inlet_outlet_index(query_text, additional_text=""):
    """Scan query and additional text (e.g. retrieved chunks) for potential object names and load matching inlet/outlet index data."""
    if not os.path.exists(INDEX_PATH):
        return ""
        
    try:
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            index_data = json.load(f).get("inlet_outlet_index", {})
            
        candidates = []
        for w in query_text.split():
            w_clean = w.strip("?,.:;()\"'")
            if w_clean in index_data:
                candidates.append(w_clean)
            elif w_clean.lower() in index_data:
                candidates.append(w_clean.lower())
                
        if additional_text:
            for obj_name in index_data.keys():
                # Avoid short matches unless it's a distinct word
                pattern = r'(?<!\w)' + re.escape(obj_name) + r'(?!\w)'
                if re.search(pattern, additional_text):
                    candidates.append(obj_name)
                    
        if not candidates:
            return ""
            
        lines = ["==================================================", "STRUCTURED INLET/OUTLET INDEX (100% Deterministic & Accurate):"]
        for c in set(candidates):
            obj_info = index_data[c]
            lines.append(f"Object: {c}")
            lines.append("Inlets:")
            for inlet in obj_info.get("inlets", []):
                lines.append(f"  * {inlet}")
            lines.append("Outlets:")
            for outlet in obj_info.get("outlets", []):
                lines.append(f"  * {outlet}")
            lines.append("")
        lines.append("==================================================\n")
        return "\n".join(lines)
    except Exception as e:
        print(f"[Explain] Error loading inlet/outlet index: {e}")
        return ""

def detect_m4l_context(query_text, domain=None):
    """Detect if the query triggers Max for Live (M4L) or Live API context."""
    if domain == "m4l":
        return True
    
    m4l_keywords = ["live.", "m4l", "lom", "live api", "tempo", "track", "clip", "device", "observer", "remote~", "max for live", "live device"]
    query_lower = query_text.lower()
    return any(keyword in query_lower for keyword in m4l_keywords)

def load_lom_schema():
    """Load the hand-curated LOM reference schema."""
    if not os.path.exists(LOM_REF_PATH):
        return ""
    
    try:
        with open(LOM_REF_PATH, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        lines = ["==================================================", "LIVE OBJECT MODEL (LOM) SCHEMA:", "Hierarchy:"]
        hierarchy = schema.get("live_object_model", {}).get("hierarchy", {})
        for obj, info in hierarchy.items():
            lines.append(f"  - {obj}: {info.get('description', '')}")
            if info.get("properties"):
                lines.append("    Properties:")
                for p in info["properties"]:
                    lines.append(f"      * {p['name']} ({p['type']}) [{p['access']}]: {p['description']}")
            if info.get("children"):
                lines.append("    Children:")
                for c in info["children"]:
                    lines.append(f"      * {c['name']} (target: {c['target']}): {c['description']}")
            if info.get("functions"):
                lines.append("    Functions:")
                for fn in info["functions"]:
                    args_str = f" args: {fn['arguments']}" if fn.get("arguments") else ""
                    lines.append(f"      * {fn['name']}() {args_str}: {fn['description']}")
        
        lines.append("\nLOM Path Examples:")
        examples = schema.get("live_object_model", {}).get("lom_path_examples", [])
        for ex in examples:
            lines.append(f"  - {ex['description']}:")
            lines.append(f"    Path: '{ex['path']}'")
            if ex.get("property"):
                lines.append(f"    Property: '{ex['property']}'")
                
        # Add M4L core objects
        m4l_objects = schema.get("live_object_model", {}).get("m4l_core_objects", {})
        if m4l_objects:
            lines.append("\nMax for Live Core Objects Reference:")
            for name, details in m4l_objects.items():
                lines.append(f"  - {name}: {details.get('description', '')}")
                if details.get("inlets"):
                    lines.append("    Inlets:")
                    for inl in details["inlets"]:
                        lines.append(f"      * {inl}")
                if details.get("outlets"):
                    lines.append("    Outlets:")
                    for out in details["outlets"]:
                        lines.append(f"      * {out}")
                if details.get("example_connection"):
                    lines.append(f"    Example Patch Connection: {details['example_connection']}")

        lines.append("==================================================")
        return "\n".join(lines)
    except Exception as e:
        print(f"[Explain] Error loading LOM reference: {e}")
        return ""

def explain_query(query_text, domain=None, version="8", model=EXPLAIN_MODEL, results_count=3, callback=None, stream_to_stdout=False):
    """Retrieve relevant chunks and generate a prose explanation using local Ollama (supporting streaming)."""
    # Retrieve documents
    retrieved = query_vector_db(query_text, domain=domain, max_version=version, n_results=results_count)
    
    context_blocks = []
    if retrieved and retrieved.get("documents") and retrieved["documents"][0]:
        documents = retrieved["documents"][0]
        metadatas = retrieved["metadatas"][0]
        for idx, (doc, meta) in enumerate(zip(documents, metadatas)):
            source_title = meta.get("title", meta.get("object_name", "Unknown Source"))
            context_blocks.append(f"--- Chunk #{idx + 1} Source: [{source_title}] ---\n{doc}\n")
    
    context_text = "\n".join(context_blocks) if context_blocks else "No relevant documentation found."
    
    # Load structured index if relevant
    structured_index_text = load_inlet_outlet_index(query_text, context_text)
    
    # Load LOM schema if relevant
    lom_schema_text = ""
    if detect_m4l_context(query_text, domain):
        lom_schema_text = load_lom_schema()
        
    # Build user prompt
    user_prompt = EXPLAIN_PROMPT_TEMPLATE.format(
        structured_index_text=structured_index_text,
        context_text=context_text,
        lom_schema_text=lom_schema_text,
        query=query_text
    )
    
    messages = [
        {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]
    
    print(f"[Explain] Dispatching to model '{model}' (streaming enabled)...")
    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": 0.2,  # Low temperature for factual grounding
                    "num_ctx": EXPLAIN_CONTEXT_WINDOW
                }
            },
            stream=True,
            timeout=300
        )
        if response.status_code == 200:
            full_text = ""
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    token = chunk.get("message", {}).get("content", "")
                    full_text += token
                    if callback:
                        callback(token)
                    if stream_to_stdout:
                        sys.stdout.write(token)
                        sys.stdout.flush()
            if stream_to_stdout:
                print()
            return full_text.strip()
        else:
            return f"[Error] Ollama returned status code {response.status_code}: {response.text}"
    except Exception as e:
        return f"[Error] Failed to connect to Ollama: {e}"

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python explain.py <query>")
        sys.exit(1)
        
    query = sys.argv[1]
    explanation = explain_query(query)
    print("\n--- Explanation ---")
    print(explanation)
