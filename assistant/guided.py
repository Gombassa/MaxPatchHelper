import os
import json
import sys
import requests
from typing import List, Dict, Any, Optional
from retrieve import query_vector_db
from explain import load_inlet_outlet_index, load_lom_schema, detect_m4l_context
from generate import generate_patch
from config import OLLAMA_CHAT_URL, GUIDED_MODEL, GUIDED_CONTEXT_WINDOW, DATA_DIR, GENERATE_MODEL
from prompts import GUIDED_SYSTEM_PROMPT

# Path to personal idioms
IDIOMS_PATH = os.path.join(DATA_DIR, "personal_idioms.md")

ENRICHED_USER_TEMPLATE = """Below is the context for the current turn of the design session.

{personal_idioms_section}

{structured_index_section}

{lom_schema_section}

{context_section}"""

def check_gitignore_for_idioms() -> bool:
    """Verifies that data/personal_idioms.md is listed in .gitignore to prevent committing personal history."""
    gitignore_path = ".gitignore"
    if not os.path.exists(gitignore_path):
        return False
    try:
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        lines = [line.strip() for line in content.splitlines()]
        # Check if 'data/personal_idioms.md' or similar folder-level ignore rules exist
        target = "data/personal_idioms.md"
        return any(target in line or line == "data/" or line == "data/*" for line in lines)
    except Exception as e:
        print(f"[Guided] Error checking .gitignore: {e}")
        return False

def load_personal_idioms() -> str:
    """Loads existing personal idioms and lessons learned from past sessions."""
    if not os.path.exists(IDIOMS_PATH):
        return ""
    try:
        with open(IDIOMS_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return (
                "==================================================\n"
                "PERSONAL IDIOMS & LESSONS LEARNT FROM PAST SESSIONS:\n"
                f"{content}\n"
                "=================================================="
            )
    except Exception as e:
        print(f"[Guided] Error loading personal idioms: {e}")
    return ""

def append_to_personal_idioms(summary: str):
    """Appends the end-of-session summary to the personal idioms file."""
    if not check_gitignore_for_idioms():
        print("[Guided] WARNING: data/personal_idioms.md is not in .gitignore. Refusing to write to it to avoid leakage.")
        return
    
    os.makedirs(os.path.dirname(IDIOMS_PATH), exist_ok=True)
    try:
        # Check if file is empty or new to format correctly
        is_new = not os.path.exists(IDIOMS_PATH) or os.path.getsize(IDIOMS_PATH) == 0
        with open(IDIOMS_PATH, "a", encoding="utf-8") as f:
            if not is_new:
                f.write("\n\n")
            f.write(summary.strip())
        print(f"[Guided] End-of-session summary appended to {IDIOMS_PATH}")
    except Exception as e:
        print(f"[Guided] Error saving personal idioms: {e}")

def run_guided_build_session():
    """Starts the interactive guided patch builder REPL."""
    print("=" * 60)
    print("              MAX/M4L GUIDED BUILD MODE REPL")
    print("=" * 60)
    print("Type your questions or request design suggestions.")
    print("Special Commands:")
    print("  show     - Print current conversation transcript")
    print("  generate - Compile design specs and trigger patch generation")
    print("  help     - Show this help message")
    print("  exit     - End session, trigger learning phase, and exit")
    print("=" * 60)

    # Verify gitignore presence for safety upfront
    if not check_gitignore_for_idioms():
        print("[Guided] Warning: 'data/personal_idioms.md' is not listed in your .gitignore.")
        print("         Please ensure it is ignored before exiting to avoid committing personal settings.")

    # Initialize state
    session_history = []
    domain_context = "max"
    
    # Pre-load idioms
    personal_idioms_text = load_personal_idioms()
    if personal_idioms_text:
        print("[Guided] Loaded past personal idioms and lessons learned.")

    while True:
        try:
            user_input = input("\nguided > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[Guided] Session interrupted. Running end-of-session learning stage...")
            user_input = "exit"

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in ["exit", "quit", "done"]:
            # Trigger learning stage
            run_learning_stage(session_history)
            print("[Guided] Session ended. Goodbye!")
            break
            
        elif cmd == "help":
            print("Special Commands:")
            print("  show     - Print current conversation transcript")
            print("  generate - Compile design specs and trigger patch generation")
            print("  help     - Show this help message")
            print("  exit     - End session, trigger learning phase, and exit")
            continue
            
        elif cmd == "show":
            if not session_history:
                print("[Guided] No conversation history yet.")
            else:
                print("\n--- Current Session Transcript ---")
                for msg in session_history:
                    role_name = "User" if msg["role"] == "user" else "Assistant"
                    print(f"\n[{role_name}]:")
                    print(msg["content"])
                print("-----------------------------------")
            continue
            
        elif cmd == "generate":
            if not session_history:
                print("[Guided] Cannot generate a patch: no design discussions have occurred yet.")
                continue
            run_generation_stage(session_history, domain_context)
            continue

        # Normal Turn: Process user input
        # 1. Update domain if M4L mentioned
        if detect_m4l_context(user_input, None):
            domain_context = "m4l"

        # 2. Retrieve relevant context documents from vector store
        retrieved = query_vector_db(user_input, domain=domain_context, n_results=3)
        context_blocks = []
        if retrieved and retrieved.get("documents") and retrieved["documents"][0]:
            documents = retrieved["documents"][0]
            metadatas = retrieved["metadatas"][0]
            for idx, (doc, meta) in enumerate(zip(documents, metadatas)):
                source_title = meta.get("title", meta.get("object_name", "Unknown Source"))
                context_blocks.append(f"--- Chunk #{idx + 1} Source: [{source_title}] ---\n{doc}\n")
        context_text = "\n".join(context_blocks) if context_blocks else "No specific context documents found."

        # 3. Load structured inlet/outlet index
        structured_index_text = load_inlet_outlet_index(user_input)

        # 4. Load LOM schema if domain is M4L
        lom_schema_text = ""
        if domain_context == "m4l":
            lom_schema_text = load_lom_schema()

        # 5. Format Enriched User message for current turn — user_input concatenated
        # separately to avoid .format() injection via curly braces in user text
        enriched_user_content = (
            ENRICHED_USER_TEMPLATE.format(
                personal_idioms_section=personal_idioms_text,
                structured_index_section=structured_index_text,
                lom_schema_section=lom_schema_text,
                context_section=context_text,
            )
            + f"\n\n==================================================\nUSER INPUT:\n{user_input}\n=================================================="
        )

        # 6. Prepare messages list for API call
        # We append user's raw message to the persistent history, but for this specific LLM call
        # we swap the last user message with the enriched user content
        session_history.append({"role": "user", "content": user_input})
        
        api_messages = [
            {"role": "system", "content": GUIDED_SYSTEM_PROMPT}
        ] + session_history[:-1] + [
            {"role": "user", "content": enriched_user_content}
        ]

        # 7. Call LLM
        print(f"[Guided] Thinking...")
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
                print(f"[Guided] Error: Ollama API returned code {response.status_code}: {response.text}")
                # Remove the user message since we failed to process it
                session_history.pop()
                continue

            # Stream response to stdout
            full_response = ""
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    token = chunk.get("message", {}).get("content", "")
                    full_response += token
                    sys.stdout.write(token)
                    sys.stdout.flush()
            print()

            # Save raw assistant response to persistent history
            session_history.append({"role": "assistant", "content": full_response})

        except Exception as e:
            print(f"[Guided] Error communicating with Ollama: {e}")
            session_history.pop()


def run_learning_stage(session_history: List[Dict[str, str]]):
    """Summarizes progress, architectural choices, and lessons learned, and appends to data/personal_idioms.md."""
    if not session_history:
        print("[Guided] No design history to summarize.")
        return

    print("\n--- Running End-of-Session Learning Stage ---")
    print("[Guided] Compiling personal idioms and architectural lessons learned...")

    summary_prompt = (
        "Analyze the following conversation history of a patch design session. "
        "Create a concise, bulleted Markdown summary of the following:\n"
        "1. What patch was designed/attempted (the core goal).\n"
        "2. Key design and architectural choices (e.g. object selections, signal flows, parameters, M4L components).\n"
        "3. Any lessons learned, gotchas, or reusable personal idioms discovered during the session.\n\n"
        "Keep the summary extremely concise, practical, and under 15 lines of text.\n\n"
        "Conversation History:\n"
    )
    
    # Append session history
    for msg in session_history:
        role = "User" if msg["role"] == "user" else "Assistant"
        summary_prompt += f"\n[{role}]: {msg['content']}\n"

    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json={
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
            },
            timeout=300
        )

        if response.status_code == 200:
            summary_text = response.json().get("message", {}).get("content", "").strip()
            print("\nLessons Learned & Idioms Summary:")
            print("-" * 50)
            print(summary_text)
            print("-" * 50)
            
            # Format with header and timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_entry = f"### Session Summary - {timestamp}\n{summary_text}"
            
            # Append to idioms file
            append_to_personal_idioms(formatted_entry)
        else:
            print(f"[Guided] Error during summarization: HTTP {response.status_code}")
    except Exception as e:
        print(f"[Guided] Failed to compile session summary: {e}")


def run_generation_stage(session_history: List[Dict[str, str]], domain: str):
    """Compiles the negotiated design specifications and calls generate_patch to build the .maxpat JSON."""
    print("\n--- Finalizing Design Specifications ---")
    
    spec_prompt = (
        "Based on the conversation history below, extract and list the complete final design specifications "
        "needed to construct the patch. Detail all objects (with names, classes, attributes) and "
        "all patchline connections between them.\n\n"
        "Conversation History:\n"
    )
    
    for msg in session_history:
        role = "User" if msg["role"] == "user" else "Assistant"
        spec_prompt += f"\n[{role}]: {msg['content']}\n"

    print("[Guided] Extracting design specifications...")
    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json={
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
            },
            timeout=300
        )

        if response.status_code != 200:
            print(f"[Guided] Error extracting specs: HTTP {response.status_code}")
            return

        spec_summary = response.json().get("message", {}).get("content", "").strip()
        print("\nExtracted Design Specifications:")
        print("-" * 50)
        print(spec_summary)
        print("-" * 50)
        
    except Exception as e:
        print(f"[Guided] Failed to extract specifications: {e}")
        return

    # Trigger generation
    print(f"\n[Guided] Starting patch generator using {GENERATE_MODEL} (domain: {domain})...")
    gen_result = generate_patch(
        query_text=spec_summary,
        domain=domain,
        stream_to_stdout=True
    )
    
    if gen_result["valid"]:
        print(f"\n[Guided] SUCCESS! Valid patch generated in {gen_result['attempts']} attempts.")
        # Ask where to save
        default_save_path = "data/generated_patch.maxpat"
        try:
            save_path = input(f"Enter file path to save patch (default: {default_save_path}): ").strip()
        except (KeyboardInterrupt, EOFError):
            save_path = ""
            
        if not save_path:
            save_path = default_save_path
            
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(gen_result["patch"], f, indent=4)
            print(f"[Guided] Saved patch to: {save_path}")
        except Exception as e:
            print(f"[Guided] Error saving patch file: {e}")
    else:
        print("\n[Guided] Patch generation failed. Errors:")
        for err in gen_result["errors"]:
            print(f" - {err}")

if __name__ == "__main__":
    run_guided_build_session()
