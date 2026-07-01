import os
import sys
import argparse

from assistant.retrieve import query_vector_db, format_results
from assistant.explain import explain_query

def main():
    parser = argparse.ArgumentParser(description="Max MSP AI Assistant CLI")
    parser.add_argument("query", type=str, nargs="?", help="The query/search term")
    parser.add_argument("--mode", type=str, choices=["explain"], default="explain", help="Assistant mode")
    parser.add_argument("--domain", type=str, choices=["max", "msp", "m4l"], help="Filter by domain")
    parser.add_argument("--version", type=str, default="8", help="Filter by Max version")
    parser.add_argument("--results", type=int, default=3, help="Number of results to return")
    parser.add_argument("--retrieve-only", action="store_true", help="Print raw retrieved document chunks without LLM explanation")

    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        sys.exit(1)

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

if __name__ == "__main__":
    main()
