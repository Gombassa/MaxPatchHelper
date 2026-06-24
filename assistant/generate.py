import os
import sys
import json
import requests
import threading
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
5. Max for Live Anchors and Routing Direction:
   - "plugin~" has 0 inlets and 2 outlets. It is the audio input from Live. You must only connect lines FROM its outlets.
   - "plugout~" has 2 inlets and 0 outlets. It is the audio output to Live. You must only connect lines INTO its inlets.
   - "live.thisdevice" has 0 inlets and 2 outlets. It is a load trigger. You must only connect lines FROM its left outlet (outlet 0) to other objects to trigger them. NEVER connect any line into "live.thisdevice" or change its inlet/outlet count.
   - UI elements (e.g. live.dial) have 1 inlet (inlet 0) and 2 outlets. The left outlet (outlet 0) outputs the value.
   - Audio Effects MUST contain a "plugin~" object (audio input) and a "plugout~" object (audio output).
   - Instruments MUST contain a MIDI input object ("midiin" or "notein") and a "plugout~" object.
   - MIDI Effects MUST contain a MIDI input object and a MIDI output object ("midiout" or "noteout").
   - Max for Live patches should include a "live.thisdevice" object to trigger path and observer initializations on load.
7. Signal rate objects must carry the "~" suffix (e.g., "cycle~", "gain~", "dac~").
8. Always coordinate ID naming sequentially starting from "obj-1", "obj-2", "obj-3", etc. Ensure no duplicate box IDs exist. NEVER jump to high ID numbers like "obj-100" or "obj-121" unless you actually have 100+ objects (which you shouldn't, as patches should be kept small).
9. Keep the patch as minimal and simple as possible. ONLY generate the objects absolutely necessary to satisfy the prompt. Never generate duplicate, redundant, or unused elements. Do NOT feel obliged to use every object listed in the "Structured Inlet/Outlet Index" or "Documentation Context". The index and context are provided for reference only.
10. Semantic constraint for audio output (dac~): dac~ inlet 0 accepts an audio signal OR an on/off integer control message, but NOT both simultaneously. If a toggle is used to turn audio on/off, do not connect it directly to the same inlet (inlet 0) that receives left-channel audio. Instead, wire the toggle separately (e.g. to a message box sending 'start'/'stop' to dac~, or to a separate dac~ object, or connect the toggle to dac~ via a 't b' object, or use ezdac~ which has a built-in on/off button).
11. Max for Live Objects Whitelist and JSON format:
    - ONLY use valid live.* objects: live.dial, live.slider, live.numbox, live.button, live.toggle, live.text, live.menu, live.tab, live.arrows, live.gain~, live.meter~, live.step, live.grid, live.line, live.drop, live.banks, live.comment, live.thisdevice, live.path, live.observer, live.object, live.remote~, live.param~.
    - NEVER generate objects like live.device, live.control, live.controlsurface, or live.macrocontrol. They do not exist in Max.
    - In your JSON, LOM objects must be "newobj" with text: "live.path", "live.observer", "live.object", "live.thisdevice". Ensure they carry their correct physical inlet/outlet ports:
      * {"box": {"id": "obj-A", "maxclass": "newobj", "text": "live.path", "numinlets": 1, "numoutlets": 2}}
      * {"box": {"id": "obj-B", "maxclass": "newobj", "text": "live.observer", "numinlets": 2, "numoutlets": 2}}
      * {"box": {"id": "obj-C", "maxclass": "newobj", "text": "live.object", "numinlets": 2, "numoutlets": 2}}
      * {"box": {"id": "obj-D", "maxclass": "newobj", "text": "live.thisdevice", "numinlets": 0, "numoutlets": 2}}
12. Message Boxes and LOM Connection Directions:
    - Message boxes MUST use "maxclass": "message" and their contents in "text". NEVER write {"box": {"maxclass": "newobj", "text": "message", ...}} or {"box": {"maxclass": "newobj", "text": "message path..."}}.
    - Example of a message box: {"box": {"id": "obj-3", "maxclass": "message", "text": "path live_set tracks 0 devices 0 parameters 1", "numinlets": 2, "numoutlets": 1}}
    - Routing rules for LOM objects (observe carefully: target ID always goes to inlet 1 (right inlet), control messages always go to inlet 0 (left inlet)):
      * live.path (1 inlet): inlet 0 receives the path message box output.
      * live.object (2 inlets): inlet 0 receives the "set value $1" message box. inlet 1 receives the resolved ID from live.path outlet 0.
      * live.observer (2 inlets): inlet 0 receives the observed property message (e.g. "property tempo"). inlet 1 receives the resolved ID from live.path outlet 0.
    - Reference LOM Parameter Control Connection Template (Copy this wiring layout exactly):
      * live.thisdevice (obj-6) outlet 0 -> path message box (obj-3) inlet 0 (triggers resolution on load)
      * path message box (obj-3) outlet 0 -> live.path (obj-1) inlet 0
      * live.path (obj-1) outlet 0 (resolved ID) -> live.object (obj-4) inlet 1 (right inlet)
      * live.dial (obj-2) outlet 0 -> set value message box (obj-5) inlet 0
      * set value message box (obj-5) outlet 0 -> live.object (obj-4) inlet 0 (left inlet)
      * Optional MIDI CC input: ctlin (obj-7) outlet 0 -> live.dial (obj-2) inlet 0
13. Parameter Scope and UI Constraints:
    - Only UI elements (like live.dial, live.slider, live.toggle, live.numbox) can carry "parameter_enable": 1 and saved parameter attributes. Non-UI API objects (like live.path, live.observer, live.object, live.thisdevice) must NOT carry "parameter_enable": 1.
    - EVERY M4L UI dial/slider/toggle/numbox MUST have a "varname" key directly at the root of the box dictionary (e.g. "varname": "macro_dial_1").
14. STRICT Minimality and Loop Prevention:
    - DO NOT generate multiple redundant copy-pasted objects (such as generating 10+ '*~' or '*' objects).
    - If you are building a MIDI CC receiver or controller, use ONE 'ctlin' or 'midiin' and a single path handler, not separate pathways for every imaginable value.
    - A typical M4L patch is highly compact and should have no more than 6-10 total boxes. Do not generate large lists of dummy objects.
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
            except json.JSONDecodeError as je:
                validation_errors = [f"JSON parsing error: {je}"]
                print(f"[Generate] JSON parsing failed on attempt {attempt}: {je}")
                if callback:
                    callback({"type": "status", "content": f"[Generate] JSON parsing failed on attempt {attempt}: {je}"})
                
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
