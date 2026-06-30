import json
import requests
from assistant.config import OLLAMA_GENERATE_URL, CLASSIFY_MODEL, CLASSIFY_CONTEXT_WINDOW

CLASSIFIER_PROMPT = """You are an intent classifier for a Max MSP and Max for Live AI assistant.
Classify the user's query into exactly one of these three categories:
- EXPLAIN: The user is asking about how an object works, asking for documentation, explaining a concept, or asking general questions.
- GENERATE: The user is asking to create, write, or generate a patch, subpatch, or `.maxpat` file from scratch.
- GUIDED: The user wants to build a patch step-by-step, interactively, or wants to walk through a design process.

Output ONLY the category name (EXPLAIN, GENERATE, or GUIDED) in uppercase. Do not output any explanation, markdown, or extra text.

User query: "{query}"
Category:"""

def classify_intent(query_text, model=CLASSIFY_MODEL):
    """Classify user query intent into EXPLAIN, GENERATE, or GUIDED using local Ollama."""
    try:
        prompt = CLASSIFIER_PROMPT.format(query=query_text)
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0,  # Zero temperature for deterministic classification
                    "num_ctx": CLASSIFY_CONTEXT_WINDOW
                }
            },
            timeout=45
        )
        if response.status_code == 200:
            result = response.json().get("response", "").strip().upper()
            # Clean up output in case the LLM returned extra symbols
            for category in ["EXPLAIN", "GENERATE", "GUIDED"]:
                if category in result:
                    return category
            return "EXPLAIN"  # Fallback
        else:
            print(f"[Classifier] Error: HTTP {response.status_code} - {response.text}")
            return "EXPLAIN"
    except Exception as e:
        print(f"[Classifier] Error classifying query: {e}")
        return "EXPLAIN"

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python classify.py <query>")
        sys.exit(1)
        
    query = sys.argv[1]
    intent = classify_intent(query)
    print(f"Query: '{query}' -> Intent: {intent}")
