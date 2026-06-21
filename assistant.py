import os
import sys
import argparse

# Add assistant subdirectory to path to avoid name conflict with assistant.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "assistant"))
from retrieve import query_vector_db, format_results
from classify import classify_intent
from explain import explain_query

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
        print("GENERATE mode is planned for Phase 3.")
    elif mode == "guided":
        print("GUIDED mode is planned for Phase 3.")

if __name__ == "__main__":
    main()
