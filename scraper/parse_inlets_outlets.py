import os
import json
import re
import requests
from typing import Dict, Any

# Target model for extraction
EXTRACT_MODEL = "mistral:latest"
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"

# Directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_WEB_DIR = os.path.join(BASE_DIR, "data", "raw", "web")
OUTPUT_INDEX_PATH = os.path.join(BASE_DIR, "data", "inlet_outlet_index.json")

# Define target objects of interest (M4L UI and core Max/MSP objects)
TARGET_OBJECTS = {
    # M4L UI and Core Objects
    "live.dial", "live.slider", "live.numbox", "live.button", "live.toggle",
    "live.text", "live.menu", "live.tab", "live.arrows", "live.gain~",
    "live.drop", "live.grid", "live.line", "live.step", "live.colors",
    "live.comment", "live.thisdevice", "live.path", "live.observer",
    "live.object", "live.remote~", "live.banks",
    
    # MSP Audio Objects
    "cycle~", "phasor~", "delay~", "gate~", "sig~", "snapshot~",
    "dac~", "adc~", "ezdac~", "ezadc~", "gain~", "groove~", "buffer~",
    "play~", "record~", "saw~", "rect~", "tri~", "noise~", "biquad~",
    "lores~", "tapin~", "tapout~", "plugin~", "plugout~", "send~", "receive~",
    "pass~", "selector~", "matrix~", "line~", "curve~",
    
    # Max Objects
    "metro", "toggle", "delay", "gate", "route", "poly~", "coll", "dict",
    "button", "trigger", "pack", "unpack", "pak", "unjoin", "join", "zl",
    "expr", "if", "routepass", "send", "receive", "defer", "deferlow",
    "loadbang", "loadmess", "closebang", "bpatcher", "thispatcher", "pcontrol",
    "slider", "dial", "number", "flonum", "umenu", "textbutton", "comment",
    "message", "active"
}

def clean_json_string(text: str) -> str:
    """Extracts raw JSON content from potential markdown wrapper."""
    text = text.strip()
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        return text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        return text[start:end].strip()
    return text

def extract_inlets_outlets_llm(object_name: str, body_text: str) -> Dict[str, Any]:
    """Calls Ollama to extract structured inlets and outlets from doc body."""
    # Truncate body_text to prevent context window issues, but keep the core Messages/Output sections
    # Find Messages and Output sections if present
    messages_idx = body_text.lower().find("messages")
    output_idx = body_text.lower().find("output")
    
    snippet = body_text
    if messages_idx != -1 or output_idx != -1:
        start_idx = min(idx for idx in [messages_idx, output_idx] if idx != -1)
        # Grab up to 5000 chars from where Messages/Output starts, or fallback to start of doc
        snippet = body_text[start_idx:start_idx + 6000]
    else:
        snippet = body_text[:6000]

    prompt = (
        f"You are an expert Cycling '74 Max/MSP developer.\n"
        f"Analyze the following raw documentation reference text for the object '{object_name}' and extract:\n"
        f"1. The list of inlets, explaining what each inlet accepts (e.g. left inlet, right inlet) and the message types (e.g. signal, float, bang).\n"
        f"2. The list of outlets, explaining what each outlet outputs (e.g. left outlet, right outlet) and types.\n\n"
        f"Format the response as a JSON object with two keys:\n"
        f"- \"inlets\": a list of strings, each string describing one inlet (e.g. \"Left Inlet (Signal/Float): Oscillator frequency...\")\n"
        f"- \"outlets\": a list of strings, each string describing one outlet (e.g. \"Left Outlet (Signal): Output waveform...\")\n\n"
        f"Important Rules:\n"
        f"- Output ONLY the valid JSON block. Do not include any markdown formatting, explanations, or backticks outside the JSON.\n"
        f"- Ensure the JSON is well-formed.\n"
        f"- Ground the description strictly in the provided text. Do not use external knowledge or fabricate inlets/outlets.\n\n"
        f"Reference Text Snippet:\n{snippet}\n"
    )

    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": EXTRACT_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a precise technical extractor that outputs ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "num_ctx": 4096
                }
            },
            timeout=60
        )
        if response.status_code == 200:
            content = response.json().get("message", {}).get("content", "").strip()
            cleaned = clean_json_string(content)
            parsed = json.loads(cleaned)
            if "inlets" in parsed and "outlets" in parsed:
                return {
                    "inlets": parsed["inlets"],
                    "outlets": parsed["outlets"]
                }
        print(f"[Extractor] Warning: Ollama returned invalid status/format for {object_name}.")
    except Exception as e:
        print(f"[Extractor] Error calling LLM for {object_name}: {e}")
    
    return {}

def main():
    print(f"[Extractor] Scanning raw crawled files in {RAW_WEB_DIR}...")
    if not os.path.exists(RAW_WEB_DIR):
        print(f"[Extractor] Error: Raw crawled web directory not found.")
        return

    # Load existing index if it exists to preserve hand-curated definitions or past runs
    existing_index = {}
    if os.path.exists(OUTPUT_INDEX_PATH):
        try:
            with open(OUTPUT_INDEX_PATH, "r", encoding="utf-8") as f:
                existing_index = json.load(f).get("inlet_outlet_index", {})
            print(f"[Extractor] Loaded {len(existing_index)} existing objects from index.")
        except Exception as e:
            print(f"[Extractor] Error reading existing index: {e}")

    new_index = {}
    
    # Traverse raw files
    files = [f for f in os.listdir(RAW_WEB_DIR) if f.endswith("_reference.json")]
    print(f"[Extractor] Found {len(files)} reference pages to check.")

    for filename in files:
        filepath = os.path.join(RAW_WEB_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            title = data.get("title", "")
            # Determine object name from title (e.g., "cycle~ Reference" -> "cycle~")
            if not title.lower().endswith("reference"):
                continue
            
            object_name = title[:-10].strip() # Strip " Reference"
            
            if object_name not in TARGET_OBJECTS:
                continue

            # If it's already in the existing index, we can reuse it (or overwrite it if we want fresh parsing)
            if object_name in existing_index:
                print(f"[Extractor] Reusing existing index entry for '{object_name}'")
                new_index[object_name] = existing_index[object_name]
                continue

            print(f"[Extractor] Processing new object '{object_name}'...")
            body_text = data.get("body", "")
            parsed_data = extract_inlets_outlets_llm(object_name, body_text)
            
            if parsed_data:
                print(f"[Extractor] Successfully extracted inlets/outlets for '{object_name}':")
                print(f"  Inlets: {parsed_data['inlets']}")
                print(f"  Outlets: {parsed_data['outlets']}")
                new_index[object_name] = parsed_data
            else:
                print(f"[Extractor] Failed to extract for '{object_name}', skipping.")

        except Exception as e:
            print(f"[Extractor] Error processing file {filename}: {e}")

    # Ensure all hand-curated core objects are present (fallback to old ones if LLM failed)
    for k, v in existing_index.items():
        if k not in new_index:
            new_index[k] = v

    # Save output
    output_data = {"inlet_outlet_index": new_index}
    try:
        with open(OUTPUT_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        print(f"[Extractor] Success! Saved index with {len(new_index)} objects to {OUTPUT_INDEX_PATH}")
    except Exception as e:
        print(f"[Extractor] Error saving final index: {e}")

if __name__ == "__main__":
    main()
