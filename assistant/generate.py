import os
import sys
import json
import requests
from typing import Dict, Any, List, Optional
from retrieve import query_vector_db
from explain import load_inlet_outlet_index, load_lom_schema, detect_m4l_context
from validate import validate_patch
from config import OLLAMA_CHAT_URL, GENERATE_CONTEXT_WINDOW, GENERATE_MODEL
EXAMPLE_MAX_PATCH_PATH = "data/example_patches/max/sine_generator.json"
EXAMPLE_M4L_PATCH_PATH = "data/example_patches/m4l/audio_effect_volume.json"

GENERATE_SYSTEM_PROMPT = """You are an expert offline AI assistant specialized in generating valid JSON patcher files (.maxpat) for Cycling '74 Max MSP and Max for Live (M4L).
Your goal is to output a single, structurally valid, and fully-functioning .maxpat JSON patch or sub-patch that fulfills the user's description.

Follow these strict formatting and structural rules:
1. Output ONLY a valid JSON block, optionally wrapped in a markdown ```json ``` code block. Do not write any prose explanation before or after the JSON.
2. Ground your patch structure in the provided "Documentation Context" chunks and "Structured Inlet/Outlet Index".
3. Connections (lines) MUST use correct, existing box IDs (e.g. "obj-1") and valid, 0-indexed inlet/outlet ports. 
   - Verify: If an object has 1 outlet, the only valid outlet index is 0. If it has 2 inlets, the valid inlet indices are 0 and 1.
4. M4L UI parameters (live.dial, live.slider, live.numbox, live.button, live.toggle, live.menu, live.gain~) MUST carry unique "varname" and unique "parameter_longname" properties, and "parameter_enable" MUST be set to 1. Crucially, "parameter_longname" MUST be nested inside the box structure under "saved_attribute_attributes" -> "valueof" -> "parameter_longname" (along with "parameter_shortname" and "parameter_type"). Do not place parameter_longname at the box root level.
5. Max for Live Anchors:
   - Audio Effects MUST contain a "plugin~" object (audio input) and a "plugout~" object (audio output).
   - Instruments MUST contain a MIDI input object ("midiin" or "notein") and a "plugout~" object.
   - MIDI Effects MUST contain a MIDI input object and a MIDI output object ("midiout" or "noteout").
6. Max for Live patches should include a "live.thisdevice" object to trigger path and observer initializations on load.
7. Signal rate objects must carry the "~" suffix (e.g., "cycle~", "gain~", "dac~").
8. Always coordinate ID naming (e.g. "obj-1", "obj-2", "obj-3") sequentially and ensure no duplicate box IDs exist.
9. Do NOT feel obliged to use every object listed in the "Structured Inlet/Outlet Index" or "Documentation Context". The index is provided for reference only. Only include objects that are necessary to build the requested patch.
10. Semantic constraint for audio output (dac~): dac~ inlet 0 accepts an audio signal OR an on/off integer control message, but NOT both simultaneously. If a toggle is used to turn audio on/off, do not connect it directly to the same inlet (inlet 0) that receives left-channel audio. Instead, wire the toggle separately (e.g. to a message box sending 'start'/'stop' to dac~, or to a separate dac~ object, or connect the toggle to dac~ via a 't b' object, or use ezdac~ which has a built-in on/off button).
"""

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
==================================================

USER REQUEST:
Generate a patch for: {query}

JSON PATCH OUTPUT:"""

def detect_m4l_device_type(query_text: str) -> str:
    query_lower = query_text.lower()
    if any(k in query_lower for k in ["synth", "instrument", "sampler", "poly~", "oscillator", "generator", "midiin", "notein"]):
        return "instrument"
    elif any(k in query_lower for k in ["midi effect", "midi filter", "note", "chord", "velocity", "seq", "arp", "midiout", "noteout"]):
        return "midi_effect"
    else:
        return "audio_effect"

def load_example_patch(domain: str) -> str:
    """Loads matching example patch for the target domain."""
    path = EXAMPLE_M4L_PATCH_PATH if domain == "m4l" else EXAMPLE_MAX_PATCH_PATH
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                # Return compact formatted JSON string
                return json.dumps(json.load(f), indent=2)
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

def generate_patch(
    query_text: str, 
    domain: Optional[str] = None, 
    version: str = "8", 
    model: str = GENERATE_MODEL,
    callback: Optional[callable] = None,
    stream_to_stdout: bool = False
) -> Dict[str, Any]:
    """
    Generates a Max/MSP or M4L patch based on a natural language query.
    Utilizes qwen2.5-coder:14b and runs a 3-attempt self-correction validation loop.
    """
    # 1. Infer domain if not provided
    if not domain:
        query_lower = query_text.lower()
        if detect_m4l_context(query_text, None):
            domain = "m4l"
        elif any(x in query_lower for x in ["~", "audio", "oscillator", "signal", "synth", "msp", "filter", "sine", "wave", "gain", "volume", "sound", "dac", "adc", "cycle", "envelope"]):
            domain = "msp"
        else:
            domain = "max"

    print(f"[Generate] Inferred domain: {domain}")
    
    # 2. Retrieve documents
    n_results = 6 if domain == "m4l" else 3
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
    
    # 6. Build initial user prompt
    user_prompt = GENERATE_USER_TEMPLATE.format(
        structured_index_text=structured_index_text,
        context_text=context_text,
        lom_schema_text=lom_schema_text,
        example_patch_text=example_patch_text,
        query=query_text
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
        print(f"[Generate] Inference Attempt {attempt}/{max_attempts}...")
        try:
            response = requests.post(
                OLLAMA_CHAT_URL,
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.2,
                        "num_ctx": GENERATE_CONTEXT_WINDOW
                    }
                },
                stream=True,
                timeout=300
            )
            
            if response.status_code != 200:
                return {
                    "valid": False,
                    "patch": None,
                    "errors": [f"Ollama returned HTTP error {response.status_code}: {response.text}"]
                }
            
            # Read tokens (streaming output if requested)
            full_response = ""
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    token = chunk.get("message", {}).get("content", "")
                    full_response += token
                    if callback:
                        callback(token)
                    if stream_to_stdout:
                        sys.stdout.write(token)
                        sys.stdout.flush()
            if stream_to_stdout:
                print()
                
            # Extract JSON block
            json_str = extract_json_block(full_response)
            
            # Validate JSON syntax and structure
            try:
                patch_dict = json.loads(json_str)
                # Run validate_patch
                val_result = validate_patch(patch_dict, domain_override=domain, device_type_override=expected_device_type)
                
                if val_result["valid"]:
                    print(f"[Generate] Success! Valid patch generated on attempt {attempt}.")
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
            except json.JSONDecodeError as je:
                validation_errors = [f"JSON parsing error: {je}"]
                print(f"[Generate] JSON parsing failed on attempt {attempt}: {je}")
                
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
                return {
                    "valid": False,
                    "patch": None,
                    "errors": validation_errors,
                    "attempts": max_attempts
                }
                
        except Exception as e:
            print(f"[Generate] Connection error on attempt {attempt}: {e}")
            if attempt == max_attempts:
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
