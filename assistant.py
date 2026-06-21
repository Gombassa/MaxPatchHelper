import os
import sys
import argparse

# Add assistant subdirectory to path to avoid name conflict with assistant.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "assistant"))
from retrieve import query_vector_db, format_results

def main():
    parser = argparse.ArgumentParser(description="Max MSP AI Assistant CLI")
    parser.add_argument("query", type=str, nargs="?", help="The query/search term")
    parser.add_argument("--mode", type=str, choices=["explain", "generate", "guided"], default="explain", help="Assistant mode")
    parser.add_argument("--domain", type=str, choices=["max", "msp", "m4l"], help="Filter by domain")
    parser.add_argument("--version", type=str, default="8", help="Filter by Max version")
    parser.add_argument("--results", type=int, default=5, help="Number of results to return")
    
    args = parser.parse_args()
    
    if not args.query and args.mode != "guided":
        parser.print_help()
        sys.exit(1)
        
    if args.mode == "explain":
        print(f"Routing to EXPLAIN mode (Retrieving documents for: '{args.query}')")
        results = query_vector_db(
            query_text=args.query,
            domain=args.domain,
            max_version=args.version,
            n_results=args.results
        )
        format_results(results)
    elif args.mode == "generate":
        print("GENERATE mode is planned for Phase 3.")
    elif args.mode == "guided":
        print("GUIDED mode is planned for Phase 3.")

if __name__ == "__main__":
    main()
