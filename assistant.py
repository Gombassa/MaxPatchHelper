import os
import sys
import argparse

# Add assistant subdirectory to path to avoid name conflict with assistant.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "assistant"))
from retrieve import query_vector_db, format_results
from classify import classify_intent
from explain import explain_query
from generate import generate_patch
from guided import run_guided_build_session

def main():
    parser = argparse.ArgumentParser(description="Max MSP AI Assistant CLI")
    parser.add_argument("query", type=str, nargs="?", help="The query/search term")
    parser.add_argument("--mode", type=str, choices=["auto", "explain", "generate", "guided"], default="auto", help="Assistant mode")
    parser.add_argument("--domain", type=str, choices=["max", "msp", "m4l"], help="Filter by domain")
    parser.add_argument("--version", type=str, default="8", help="Filter by Max version")
    parser.add_argument("--results", type=int, default=3, help="Number of results to return")
    parser.add_argument("--retrieve-only", action="store_true", help="Print raw retrieved document chunks without LLM explanation")
    
    args = parser.parse_args()
    
    if not args.query and args.mode != "guided":
        parser.print_help()
        sys.exit(1)
        
    # Auto-classify intent if mode is 'auto'
    mode = args.mode
    if mode == "auto" and args.query:
        print("[Assistant] Classifying intent...")
        classified = classify_intent(args.query)
        print(f"[Assistant] Detected intent: {classified}")
        mode = classified.lower()
        
    if args.retrieve_only:
        print(f"Retrieving documents for: '{args.query}' (domain: {args.domain or 'any'}, version: {args.version})")
        results = query_vector_db(
            query_text=args.query,
            domain=args.domain,
            max_version=args.version,
            n_results=args.results
        )
        format_results(results)
        sys.exit(0)
        
    if mode == "explain":
        print(f"\n--- EXPLAIN MODE ---")
        print("\n--- Assistant Explanation ---")
        explanation = explain_query(
            query_text=args.query,
            domain=args.domain,
            version=args.version,
            results_count=args.results,
            stream_to_stdout=True
        )
        if explanation.startswith("[Error]"):
            print(explanation)
        print("-----------------------------\n")
    elif mode == "generate":
        print(f"\n--- GENERATE MODE ---")
        print(f"Generating patch for: '{args.query}'")
        result = generate_patch(
            query_text=args.query,
            domain=args.domain,
            version=args.version,
            stream_to_stdout=True
        )
        if result["valid"]:
            print(f"\n[Assistant] Success! Valid patch generated in {result['attempts']} attempts.")
            default_save_path = "data/generated_patch.maxpat"
            print(f"To save the patch, specify a file path or press Enter to save to '{default_save_path}'.")
            try:
                save_path = input("Save path: ").strip()
            except (KeyboardInterrupt, EOFError):
                save_path = ""
            if not save_path:
                save_path = default_save_path
            
            try:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "w", encoding="utf-8") as f:
                    import json
                    json.dump(result["patch"], f, indent=4)
                print(f"[Assistant] Saved patch to {save_path}")
            except Exception as e:
                print(f"[Assistant] Error saving patch file: {e}")
        else:
            print("\n[Assistant] Patch generation failed. Errors:")
            for err in result["errors"]:
                print(f" - {err}")
    elif mode == "guided":
        run_guided_build_session()

if __name__ == "__main__":
    main()
