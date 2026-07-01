import os
import sys
import json
import requests
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
from assistant.retrieve import query_vector_db
from assistant.explain import load_inlet_outlet_index, load_lom_schema, detect_m4l_context
from assistant.validate import validate_patch
from assistant.config import OLLAMA_CHAT_URL, GENERATE_CONTEXT_WINDOW, GENERATE_MODEL, DATA_DIR
from assistant.prompts import GENERATE_SYSTEM_PROMPT
EXAMPLE_MAX_PATCH_PATH = os.path.join(DATA_DIR, "example_patches", "max", "sine_generator.json")
EXAMPLE_M4L_PATCH_PATH = os.path.join(DATA_DIR, "example_patches", "m4l", "audio_effect_volume.json")
FAILED_ATTEMPTS_DIR = os.path.join(DATA_DIR, "failed_attempts")

GENERATE_USER_TEMPLATE = """Below is the context to help you design and output a valid Max MSP / M4L patch.

{structured_index_text}

==================================================
DOCUMENTATION CONTEXT:
{context_text}
==================================================

{lom_schema_text}

==================================================
EXAMPLE REFERENCE PATCH FORMAT:
{example_patch_text}
=================================================="""

def detect_m4l_device_type(query_text: str) -> str:
    query_lower = query_text.lower()
    # Avoid matching 'instrument rack' as a synth/instrument device type
    query_clean = query_lower.replace("instrument rack", "")
    if any(k in query_clean for k in ["synth", "instrument", "sampler", "poly~", "oscillator", "generator", "notein"]):
        return "instrument"
    elif any(k in query_clean for k in ["midi effect", "midi filter", "note", "chord", "velocity", "seq", "arp", "midiout", "noteout", "midi", "cc", "ctlin", "midiin"]):
        return "midi_effect"
    else:
        return "audio_effect"

def load_example_patch(domain: str) -> str:
    """Loads matching example patch for the target domain."""
    path = EXAMPLE_M4L_PATCH_PATH if domain == "m4l" else EXAMPLE_MAX_PATCH_PATH
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Unwrap if wrapped
                if isinstance(data, dict) and "patch" in data:
                    data = data["patch"]
                return json.dumps(data, indent=2)
        except Exception as e:
            print(f"[Generate] Error loading example patch: {e}")
    return ""

def extract_json_block(text: str) -> str:
    """Extracts raw JSON block from text by finding the outermost curly braces."""
    try:
        start = text.index("{")
        end = text.rindex("}")
        return text[start:end + 1].strip()
    except ValueError:
        return text.strip()

def log_failed_attempt(query_text: str, domain: str, patch_dict: Dict[str, Any], errors: List[str], attempt: int) -> None:
    """Writes a failed validation attempt to disk for post-hoc diagnosis. Never raises."""
    try:
        os.makedirs(FAILED_ATTEMPTS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(FAILED_ATTEMPTS_DIR, f"{timestamp}_attempt{attempt}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "query_text": query_text,
                "domain": domain,
                "patch": patch_dict,
                "errors": errors,
            }, f, indent=2)
    except Exception as e:
        print(f"[Generate] Warning: failed to write failed-attempt log: {e}")

def log_failed_parse(query_text: str, domain: str, raw_text: str, attempt: int) -> None:
    """Writes an unparseable LLM response to disk for post-hoc diagnosis. Never raises."""
    try:
        os.makedirs(FAILED_ATTEMPTS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(FAILED_ATTEMPTS_DIR, f"{timestamp}_attempt{attempt}_parsefail.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "query_text": query_text,
                "domain": domain,
                "raw_response": raw_text,
                "errors": [f"JSON parsing error"],
            }, f, indent=2)
    except Exception as e:
        print(f"[Generate] Warning: failed to write failed-parse log: {e}")

def generate_patch(
    query_text: str, 
    domain: Optional[str] = None, 
    version: str = "8", 
    model: str = GENERATE_MODEL,
    callback: Optional[callable] = None,
    stream_to_stdout: bool = False,
    stop_event: Optional[threading.Event] = None
) -> Dict[str, Any]:
    """
    Generates a Max/MSP or M4L patch based on a natural language query.
    Utilizes qwen2.5-coder:14b and runs a 3-attempt self-correction validation loop.
    """
    # 1. Infer or override domain if query text implies M4L/MSP
    if domain != "m4l" and detect_m4l_context(query_text, None):
        domain = "m4l"
    elif not domain or domain == "max":
        query_lower = query_text.lower()
        if any(x in query_lower for x in ["~", "audio", "oscillator", "signal", "synth", "msp", "filter", "sine", "wave", "gain", "volume", "sound", "dac", "adc", "cycle", "envelope"]):
            domain = "msp"
        else:
            domain = "max"

    print(f"[Generate] Inferred domain: {domain}")
    
    # 2. Retrieve documents
    n_results = 3 if domain == "m4l" else 2
    retrieved = query_vector_db(query_text, domain=domain, max_version=version, n_results=n_results)
    
    context_blocks = []
    if retrieved and retrieved.get("documents") and retrieved["documents"][0]:
        documents = retrieved["documents"][0]
        metadatas = retrieved["metadatas"][0]
        for idx, (doc, meta) in enumerate(zip(documents, metadatas)):
            source_title = meta.get("title", meta.get("object_name", "Unknown Source"))
            context_blocks.append(f"--- Chunk #{idx + 1} Source: [{source_title}] ---\n{doc}\n")
    
    context_text = "\n".join(context_blocks) if context_blocks else "No relevant documentation found."
    
    # 3. Load structured index (with second-pass scan of retrieved context text)
    structured_index_text = load_inlet_outlet_index(query_text, context_text)
    
    # 4. Load LOM schema (if M4L)
    lom_schema_text = ""
    if domain == "m4l":
        lom_schema_text = load_lom_schema()
        
    # 5. Load example patch
    example_patch_text = load_example_patch(domain)
    
    # 6. Build initial user prompt — query concatenated separately to avoid .format() injection
    user_prompt = (
        GENERATE_USER_TEMPLATE.format(
            structured_index_text=structured_index_text,
            context_text=context_text,
            lom_schema_text=lom_schema_text,
            example_patch_text=example_patch_text,
        )
        + f"\n\nUSER REQUEST:\nGenerate a patch for: {query_text}"
        + "\n\nJSON PATCH OUTPUT:"
    )
    
    # 7. Initialize Chat History
    messages = [
        {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]
    
    expected_device_type = detect_m4l_device_type(query_text) if domain == "m4l" else None
    
    # 8. 3-Attempt Validation Loop
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        if stop_event and stop_event.is_set():
            print("[Generate] Stop event detected. Exiting generation loop.")
            break
        print(f"[Generate] Inference Attempt {attempt}/{max_attempts}...")
        if callback:
            callback({"type": "status", "content": f"[Generate] Inference Attempt {attempt}/{max_attempts}..."})
        try:
            response = requests.post(
                OLLAMA_CHAT_URL,
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.2,
                        "num_ctx": GENERATE_CONTEXT_WINDOW,
                        "num_predict": 2500
                    }

                },
                stream=True,
                timeout=300
            )
            
            if response.status_code != 200:
                err_msg = f"Ollama returned HTTP error {response.status_code}: {response.text}"
                if callback:
                    callback({"type": "error", "content": [err_msg]})
                return {
                    "valid": False,
                    "patch": None,
                    "errors": [err_msg]
                }
            
            # Read tokens (streaming output if requested)
            full_response = ""
            for line in response.iter_lines():
                if stop_event and stop_event.is_set():
                    print("[Generate] Stop event detected during token reading. Aborting.")
                    break
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    token = chunk.get("message", {}).get("content", "")
                    full_response += token
                    if callback:
                        callback({"type": "token", "content": token})
                    if stream_to_stdout:
                        sys.stdout.write(token)
                        sys.stdout.flush()
            if stop_event and stop_event.is_set():
                break
            if stream_to_stdout:
                print()
                
            # Extract JSON block
            json_str = extract_json_block(full_response)
            
            # Validate JSON syntax and structure
            try:
                patch_dict = json.loads(json_str)
                # If wrapped in "patch" envelope, extract the inner patcher object
                if isinstance(patch_dict, dict) and "patch" in patch_dict:
                    patch_dict = patch_dict["patch"]
                # Run validate_patch
                val_result = validate_patch(patch_dict, domain_override=domain, device_type_override=expected_device_type)
                
                if val_result["valid"]:
                    print(f"[Generate] Success! Valid patch generated on attempt {attempt}.")
                    if callback:
                        callback({"type": "status", "content": f"[Generate] Success! Valid patch generated on attempt {attempt}."})
                        callback({"type": "patch", "content": patch_dict})
                    return {
                        "valid": True,
                        "patch": patch_dict,
                        "errors": [],
                        "warnings": val_result.get("warnings", []),
                        "attempts": attempt
                    }
                else:
                    validation_errors = val_result["errors"]
                    print(f"[Generate] Validation failed on attempt {attempt}: {validation_errors}")
                    if callback:
                        callback({"type": "status", "content": f"[Generate] Validation failed on attempt {attempt}: {validation_errors}"})
                    log_failed_attempt(query_text, domain, patch_dict, validation_errors, attempt)
            except json.JSONDecodeError as je:
                validation_errors = [f"JSON parsing error: {je}"]
                print(f"[Generate] JSON parsing failed on attempt {attempt}: {je}")
                if callback:
                    callback({"type": "status", "content": f"[Generate] JSON parsing failed on attempt {attempt}: {je}"})
                log_failed_parse(query_text, domain, full_response, attempt)
                
            # If we haven't exhausted attempts, append context and error report to retry
            if attempt < max_attempts:
                # Add LLM's faulty response to chat history
                messages.append({"role": "assistant", "content": full_response})
                # Add system feedback detailing the exact errors
                feedback = (
                    "The generated patch is invalid. Please fix the following validation errors and output the complete corrected JSON patch. "
                    "Remember to output ONLY the valid JSON block without extra prose.\n\n"
                    "Validation Errors:\n" + "\n".join(f" - {err}" for err in validation_errors)
                )
                messages.append({"role": "user", "content": feedback})
            else:
                # Out of attempts, return structured error details
                print("[Generate] Exhausted all 3 attempts. Returning structured errors.")
                if callback:
                    callback({"type": "status", "content": "[Generate] Exhausted all 3 attempts. Returning structured errors."})
                    callback({"type": "error", "content": validation_errors})
                return {
                    "valid": False,
                    "patch": None,
                    "errors": validation_errors,
                    "attempts": max_attempts
                }
                
        except Exception as e:
            print(f"[Generate] Connection error on attempt {attempt}: {e}")
            if callback:
                callback({"type": "status", "content": f"[Generate] Connection error on attempt {attempt}: {e}"})
            if attempt == max_attempts:
                if callback:
                    callback({"type": "error", "content": [f"Connection error to Ollama: {e}"]})
                return {
                    "valid": False,
                    "patch": None,
                    "errors": [f"Connection error to Ollama: {e}"],
                    "attempts": max_attempts
                }
            
    return {
        "valid": False,
        "patch": None,
        "errors": ["Failed to run generation loop."],
        "attempts": max_attempts
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python generate.py <prompt>")
        sys.exit(1)
        
    query = sys.argv[1]
    result = generate_patch(query, stream_to_stdout=True)
    print("\n--- Generation Result ---")
    print(f"Valid: {result['valid']}")
    if result["valid"]:
        print(f"Attempts taken: {result['attempts']}")
        print(json.dumps(result["patch"], indent=2)[:500] + "\n...")
    else:
        print("Errors:")
        for err in result["errors"]:
            print(f" - {err}")
