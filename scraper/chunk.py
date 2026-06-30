import os
import sys
import json
import argparse
import tiktoken

# Add assistant subdirectory to path so config.py is the single source of truth
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assistant"))
from config import RAW_WEB_DIR, RAW_LOCAL_DIR, CHUNKS_FILE

class DocumentChunker:
    def __init__(self, token_limit=500, overlap=50):
        self.token_limit = token_limit
        self.overlap = overlap
        # Use cl100k_base encoding as it's standard for modern models (GPT-4, Qwen, Mistral)
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text):
        return len(self.encoder.encode(text))

    def split_text_by_tokens(self, text, metadata):
        """Split text into chunks based on token counts, preserving overlap."""
        tokens = self.encoder.encode(text)
        total_tokens = len(tokens)
        
        if total_tokens <= self.token_limit:
            return [{
                "text": text,
                "metadata": metadata,
                "token_count": total_tokens
            }]

        chunks = []
        start = 0
        while start < total_tokens:
            end = min(start + self.token_limit, total_tokens)
            chunk_tokens = tokens[start:end]
            chunk_text = self.encoder.decode(chunk_tokens)
            
            chunks.append({
                "text": chunk_text,
                "metadata": metadata,
                "token_count": len(chunk_tokens)
            })
            
            # Move start pointer forward by limit minus overlap
            start += (self.token_limit - self.overlap)
            if start >= total_tokens - self.overlap:
                break
                
        return chunks

    def format_local_xml_doc(self, data):
        """Convert parsed XML object data into structured Markdown for optimal LLM retrieval."""
        name = data.get("object_name", "unknown")
        digest = data.get("digest", "")
        description = data.get("description", "")
        
        md_lines = []
        md_lines.append(f"# Object: {name}")
        if digest:
            md_lines.append(f"**Digest**: {digest}")
        if description:
            md_lines.append(f"**Description**: {description}")
            
        md_lines.append("")
        
        # Inlets & Outlets
        if data.get("inlets"):
            md_lines.append("## Inlets")
            for inlet in data["inlets"]:
                inlet_id = inlet.get("id", "")
                inlet_type = inlet.get("type", "")
                inlet_desc = inlet.get("description", "")
                md_lines.append(f"- **Inlet {inlet_id}** ({inlet_type}): {inlet_desc}")
            md_lines.append("")
            
        if data.get("outlets"):
            md_lines.append("## Outlets")
            for outlet in data["outlets"]:
                outlet_id = outlet.get("id", "")
                outlet_type = outlet.get("type", "")
                outlet_desc = outlet.get("description", "")
                md_lines.append(f"- **Outlet {outlet_id}** ({outlet_type}): {outlet_desc}")
            md_lines.append("")

        # Messages
        if data.get("messages"):
            md_lines.append("## Messages")
            for msg in data["messages"]:
                msg_name = msg.get("name", "")
                msg_digest = msg.get("digest", "")
                msg_desc = msg.get("description", "")
                md_lines.append(f"- **{msg_name}**: {msg_digest} {msg_desc}".strip())
            md_lines.append("")

        # Attributes
        if data.get("attributes"):
            md_lines.append("## Attributes")
            for attr in data["attributes"]:
                attr_name = attr.get("name", "")
                attr_type = attr.get("type", "")
                attr_digest = attr.get("digest", "")
                attr_desc = attr.get("description", "")
                md_lines.append(f"- **{attr_name}** ({attr_type}): {attr_digest} {attr_desc}".strip())
            md_lines.append("")

        return "\n".join(md_lines)

    def format_web_doc(self, data):
        """Convert scraped web page HTML/text data into structured Markdown."""
        title = data.get("title", "")
        url = data.get("url", "")
        body = data.get("body", "")
        
        md_lines = []
        md_lines.append(f"# Title: {title}")
        md_lines.append(f"**Source URL**: {url}")
        md_lines.append("")
        md_lines.append(body)
        md_lines.append("")
        
        # Format tables
        for table in data.get("tables", []):
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            
            if headers:
                md_lines.append("| " + " | ".join(headers) + " |")
                md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            
            for row in rows:
                md_lines.append("| " + " | ".join(row) + " |")
            
            md_lines.append("")

        return "\n".join(md_lines)

    def process_all(self):
        """Process both local and web raw docs, generate chunks and save to CHUNKS_FILE."""
        all_chunks = []

        # 1. Process Local XML docs
        if os.path.exists(RAW_LOCAL_DIR):
            print(f"[Chunker] Processing local XML ref files in {RAW_LOCAL_DIR}...")
            for file in os.listdir(RAW_LOCAL_DIR):
                if file.endswith(".json"):
                    filepath = os.path.join(RAW_LOCAL_DIR, file)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    formatted_text = self.format_local_xml_doc(data)
                    obj_name = data.get("object_name", "")
                    
                    # Determine domain: msp objects end with tilde '~'
                    domain = "msp" if obj_name.endswith("~") else "max"
                    if "live." in obj_name.lower() or "lom" in obj_name.lower():
                        domain = "m4l"
                    
                    metadata = {
                        "source": "local_xml",
                        "object_name": obj_name,
                        "domain": domain,
                        "max_version": "8",
                        "filepath": data.get("source_file", "")
                    }
                    
                    chunks = self.split_text_by_tokens(formatted_text, metadata)
                    all_chunks.extend(chunks)

        # 2. Process Scraped Web docs
        if os.path.exists(RAW_WEB_DIR):
            print(f"[Chunker] Processing scraped web files in {RAW_WEB_DIR}...")
            for file in os.listdir(RAW_WEB_DIR):
                if file.endswith(".json"):
                    filepath = os.path.join(RAW_WEB_DIR, file)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    formatted_text = self.format_web_doc(data)
                    url = data.get("url", "")
                    title = data.get("title", "")
                    
                    # Detect domain from URL or title
                    domain = "max"
                    if "msp" in url.lower() or "msp" in title.lower():
                        domain = "msp"
                    elif "m4l" in url.lower() or "live" in url.lower() or "api" in url.lower():
                        domain = "m4l"
                        
                    metadata = {
                        "source": "web_scrape",
                        "title": title,
                        "domain": domain,
                        "max_version": "8",
                        "url": url
                    }
                    
                    chunks = self.split_text_by_tokens(formatted_text, metadata)
                    all_chunks.extend(chunks)

        # Save all chunks
        os.makedirs(os.path.dirname(CHUNKS_FILE), exist_ok=True)
        with open(CHUNKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_chunks, f, indent=2, ensure_ascii=False)
            
        print(f"[Chunker] Created {len(all_chunks)} chunks total and saved to {CHUNKS_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tokenizer and Chunker for Max MSP docs")
    parser.add_argument("--limit", type=int, default=500, help="Max tokens per chunk")
    parser.add_argument("--overlap", type=int, default=50, help="Token overlap between chunks")
    args = parser.parse_args()

    chunker = DocumentChunker(token_limit=args.limit, overlap=args.overlap)
    chunker.process_all()
