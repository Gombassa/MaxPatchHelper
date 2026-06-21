import os
import re
import time
import json
import argparse
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

# Define default paths and headers
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
RAW_WEB_DIR = "data/raw/web"
RAW_LOCAL_DIR = "data/raw/local"


class PoliteWebScraper:
    def __init__(self, base_url, delay=1.5):
        self.base_url = base_url
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
        self.visited_urls = set()

    def get_page(self, url):
        """Fetch page content politely."""
        if url in self.visited_urls:
            return None
        
        print(f"[Web Scraper] Fetching: {url}")
        time.sleep(self.delay)
        
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                self.visited_urls.add(url)
                return response.text
            else:
                print(f"[Web Scraper] Failed to fetch {url}: Status code {response.status_code}")
                return None
        except Exception as e:
            print(f"[Web Scraper] Error fetching {url}: {e}")
            return None

    def clean_text(self, text):
        """Remove multiple spaces and extra newlines."""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def parse_object_page(self, html_content, url):
        """Extract main content and tables from Cycling74 doc pages."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove navigation, header, footer, and sidebar elements
        for element in soup(["nav", "header", "footer", "sidebar", "script", "style"]):
            element.decompose()
            
        title_elem = soup.find('h1')
        title = title_elem.get_text().strip() if title_elem else "Unknown Object"
        
        # Extract structured tables (e.g. LOM property tables or message tables)
        tables_data = []
        for table in soup.find_all('table'):
            headers = [th.get_text().strip() for th in table.find_all('th')]
            rows = []
            for tr in table.find_all('tr'):
                cells = [td.get_text().strip() for td in tr.find_all('td')]
                if cells:
                    rows.append(cells)
            if headers or rows:
                tables_data.append({
                    "headers": headers,
                    "rows": rows
                })
        
        # Extract main body text
        paragraphs = [p.get_text().strip() for p in soup.find_all(['p', 'li', 'div']) if p.get_text().strip()]
        body_text = "\n".join(paragraphs)
        
        return {
            "title": title,
            "url": url,
            "body": body_text,
            "tables": tables_data
        }

    def crawl_docs(self, start_url, max_pages=100):
        """Simple recursive crawl starting from a index URL."""
        os.makedirs(RAW_WEB_DIR, exist_ok=True)
        to_visit = [start_url]
        pages_crawled = 0

        while to_visit and pages_crawled < max_pages:
            current_url = to_visit.pop(0)
            if current_url in self.visited_urls:
                continue

            html = self.get_page(current_url)
            if not html:
                continue

            parsed_data = self.parse_object_page(html, current_url)
            filename = f"web_{pages_crawled}_{parsed_data['title'].replace(' ', '_').lower()}.json"
            filepath = os.path.join(RAW_WEB_DIR, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(parsed_data, f, indent=2, ensure_ascii=False)
            
            pages_crawled += 1
            print(f"[Web Scraper] Saved {filename} ({pages_crawled}/{max_pages})")

            # Extract links to other doc pages under the same base path
            soup = BeautifulSoup(html, 'html.parser')
            for link in soup.find_all('a', href=True):
                full_link = urljoin(current_url, link['href'])
                parsed_link = urlparse(full_link)
                # Keep crawls within cycling74 docs site
                if "docs.cycling74.com" in parsed_link.netloc and full_link not in self.visited_urls:
                    to_visit.append(full_link)


class LocalMaxRefParser:
    def __init__(self, refpages_dir):
        self.refpages_dir = refpages_dir

    def parse_xml_file(self, filepath):
        """Parse local Max .maxref.xml files into a structured dict."""
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
            
            obj_name = root.attrib.get('name', '')
            obj_digest = ""
            obj_description = ""
            
            # Extract digest and description
            digest_node = root.find('digest')
            if digest_node is not None:
                obj_digest = "".join(digest_node.itertext()).strip()
                
            desc_node = root.find('description')
            if desc_node is not None:
                obj_description = "".join(desc_node.itertext()).strip()

            # Extract messages
            messages = []
            for msg_node in root.findall('.//method'):
                msg_name = msg_node.attrib.get('name', '')
                msg_digest = ""
                msg_desc = ""
                
                m_digest = msg_node.find('digest')
                if m_digest is not None:
                    msg_digest = "".join(m_digest.itertext()).strip()
                    
                m_desc = msg_node.find('description')
                if m_desc is not None:
                    msg_desc = "".join(m_desc.itertext()).strip()
                
                messages.append({
                    "name": msg_name,
                    "digest": msg_digest,
                    "description": msg_desc
                })

            # Extract attributes
            attributes = []
            for attr_node in root.findall('.//attribute'):
                attr_name = attr_node.attrib.get('name', '')
                attr_type = attr_node.attrib.get('type', '')
                attr_digest = ""
                attr_desc = ""
                
                a_digest = attr_node.find('digest')
                if a_digest is not None:
                    attr_digest = "".join(a_digest.itertext()).strip()
                    
                a_desc = attr_node.find('description')
                if a_desc is not None:
                    attr_desc = "".join(a_desc.itertext()).strip()
                
                attributes.append({
                    "name": attr_name,
                    "type": attr_type,
                    "digest": attr_digest,
                    "description": attr_desc
                })

            # Extract inlets and outlets
            inlets = []
            outlets = []
            
            # Maxref files sometimes have an inletlist / outletlist section
            for inlet in root.findall('.//inlet'):
                inlets.append({
                    "id": inlet.attrib.get('id', ''),
                    "type": inlet.attrib.get('type', ''),
                    "description": "".join(inlet.itertext()).strip()
                })
            for outlet in root.findall('.//outlet'):
                outlets.append({
                    "id": outlet.attrib.get('id', ''),
                    "type": outlet.attrib.get('type', ''),
                    "description": "".join(outlet.itertext()).strip()
                })

            return {
                "object_name": obj_name,
                "digest": obj_digest,
                "description": obj_description,
                "messages": messages,
                "attributes": attributes,
                "inlets": inlets,
                "outlets": outlets,
                "source_file": filepath
            }
        except Exception as e:
            print(f"[Local Parser] Error parsing XML {filepath}: {e}")
            return None

    def scan_and_parse(self):
        """Recursively scan refpages_dir for .maxref.xml files."""
        os.makedirs(RAW_LOCAL_DIR, exist_ok=True)
        count = 0
        
        print(f"[Local Parser] Scanning {self.refpages_dir} for .maxref.xml files...")
        for root_dir, _, files in os.walk(self.refpages_dir):
            for file in files:
                if file.endswith('.maxref.xml'):
                    full_path = os.path.join(root_dir, file)
                    parsed = self.parse_xml_file(full_path)
                    if parsed:
                        out_filename = f"local_{parsed['object_name'].replace('~', '_tilde').lower()}.json"
                        out_filepath = os.path.join(RAW_LOCAL_DIR, out_filename)
                        with open(out_filepath, 'w', encoding='utf-8') as f:
                            json.dump(parsed, f, indent=2, ensure_ascii=False)
                        count += 1
                        
        print(f"[Local Parser] Successfully parsed and saved {count} XML refpages to {RAW_LOCAL_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Polite Scraper & XML Parser for Max MSP AI Assistant")
    parser.add_argument("--online", action="store_true", help="Run online BeautifulSoup crawler")
    parser.add_argument("--url", type=str, default="https://docs.cycling74.com/legacy/max8", help="Start URL for online crawl")
    parser.add_argument("--max-pages", type=int, default=50, help="Maximum pages to scrape online")
    
    parser.add_argument("--local", action="store_true", help="Parse local Max refpages XML directory")
    parser.add_argument("--path", type=str, help="Path to local Max refpages folder")
    
    args = parser.parse_args()

    if args.online:
        scraper = PoliteWebScraper(base_url=args.url)
        scraper.crawl_docs(args.url, max_pages=args.max_pages)
    
    elif args.local:
        if not args.path:
            print("[Error] Must specify --path when using --local")
        else:
            parser = LocalMaxRefParser(args.path)
            parser.scan_and_parse()
    else:
        print("[Info] Use --online or --local flag to scrape or parse documentation.")
