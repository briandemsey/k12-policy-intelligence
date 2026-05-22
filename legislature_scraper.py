"""
California Legislature Bill Scraper
Scrapes leginfo.legislature.ca.gov for K-12 education bills.
Uses Playwright to handle JavaScript-rendered pages.
Run standalone or imported by collector.py.
"""

import sqlite3
import hashlib
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

DB_PATH = r"F:\CA_5_9_26\LLM\k12_ca.db"

# Search keywords for bill subject search
BILL_SEARCHES = [
    "artificial intelligence education",
    "K-12 curriculum",
    "school technology",
    "student data privacy",
    "education assessment",
    "school funding",
    "teacher training",
]

BASE_URL = "https://leginfo.legislature.ca.gov"
SEARCH_URL = f"{BASE_URL}/faces/billSearchClient.xhtml"


def article_id(url):
    return hashlib.md5(url.encode()).hexdigest()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            url TEXT,
            published TEXT,
            summary TEXT,
            full_text TEXT,
            california_relevant INTEGER DEFAULT 0,
            ai_relevant INTEGER DEFAULT 0,
            h_score REAL DEFAULT NULL,
            h_response TEXT DEFAULT NULL,
            collected_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def scrape_bills():
    new_count = 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (educational research bot)"})

        for keyword in BILL_SEARCHES:
            print(f"  Searching bills: '{keyword}'...")
            try:
                page.goto(SEARCH_URL, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=15000)

                # Fill keyword field and submit
                page.fill("#keyword", keyword)
                page.click("#attrSearch")
                page.wait_for_load_state("networkidle", timeout=15000)

                # Extract bill links from results table
                links = page.query_selector_all("a[href*='billNavClient'], a[href*='billTextClient']")
                if not links:
                    links = page.query_selector_all("table.billList a, td.first a")

                print(f"    Found {len(links)} bill links")

                for link in links[:20]:
                    try:
                        bill_title = link.inner_text().strip()
                        bill_href = link.get_attribute("href")
                        if not bill_href or not bill_title:
                            continue

                        bill_url = bill_href if bill_href.startswith("http") else f"{BASE_URL}{bill_href}"
                        aid = article_id(bill_url)

                        c.execute("SELECT id FROM articles WHERE id = ?", (aid,))
                        if c.fetchone():
                            continue

                        # Visit bill page to extract actual publication date
                        published = str(datetime.now())[:10]
                        summary = f"California bill: {bill_title}"
                        try:
                            bill_page = browser.new_page()
                            bill_page.goto(bill_url, timeout=20000)
                            bill_page.wait_for_load_state("networkidle", timeout=10000)
                            content = bill_page.content()
                            bill_page.close()
                            # Extract "Date Published: MM/DD/YYYY" from page
                            import re
                            m = re.search(r'Date Published:\s*(\d{2}/\d{2}/\d{4})', content)
                            if m:
                                d = datetime.strptime(m.group(1), "%m/%d/%Y")
                                published = d.strftime("%Y-%m-%d")
                            # Extract bill summary text
                            m2 = re.search(r'An act to[^<]{20,300}', content)
                            if m2:
                                summary = m2.group(0).strip()
                        except Exception:
                            pass

                        # Determine relevance
                        title_lower = bill_title.lower()
                        ai_rel = any(kw in title_lower for kw in
                                     ["ai", "artificial intelligence", "technology", "data",
                                      "computer", "digital", "curriculum", "assessment"])

                        c.execute("""
                            INSERT INTO articles
                            (id, source, title, url, published, summary,
                             california_relevant, ai_relevant, collected_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            aid, "CA Legislature", bill_title, bill_url,
                            published, summary,
                            1, 1 if ai_rel else 0,
                            str(datetime.now())
                        ))
                        new_count += 1
                        time.sleep(1)

                    except Exception:
                        continue

                time.sleep(2)

            except Exception as e:
                print(f"    Error searching '{keyword}': {e}")
                continue

        browser.close()

    conn.commit()
    conn.close()
    print(f"CA Legislature: {new_count} new bills collected.")
    return new_count


if __name__ == "__main__":
    init_db()
    print("Scraping California Legislature...")
    scrape_bills()
