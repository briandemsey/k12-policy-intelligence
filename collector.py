"""
K-12 AI Education Policy Collector
Pulls from RSS feeds + NewsAPI, filters for relevance, stores in SQLite,
then verifies via hallucinations.cloud multi-model H-Score methodology.
"""

import feedparser
import requests
import sqlite3
import hashlib
import json
import os
import time
from datetime import datetime
from openai import OpenAI
import anthropic
import google.generativeai as genai
import cohere

# --- Configuration ---

DB_PATH = r"F:\CA_5_9_26\LLM\k12_ca.db"

# LLM API keys (match Hallucinations_1_28_26.py naming)
openai_key     = os.environ.get("OPENAI_API_KEY", "")
anthropic_key  = os.environ.get("ANTHROPIC_API_KEY", "")
google_key     = os.environ.get("GOOGLE_API_KEY", "")
cohere_key     = os.environ.get("COHERE_API_KEY", "")
deepseek_key   = os.environ.get("DEEPSEEK_API_KEY", "")
openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
perplexity_key = os.environ.get("PERPLEXITY_API_KEY", "")
grok_key       = os.environ.get("GROK_API_KEY", "")

openai_client    = OpenAI(api_key=openai_key) if openai_key else None
anthropic_client = anthropic.Anthropic(api_key=anthropic_key) if anthropic_key else None
if google_key:
    genai.configure(api_key=google_key)

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
NEWSAPI_URL = "https://newsapi.org/v2/everything"

NEWSAPI_QUERIES = [
    "K-12 education AI legislation",
    "K-12 school artificial intelligence policy",
    "K-12 education California legislature",
    "student assessment education reform",
    "education technology school policy",
    "public school funding legislation 2026",
    "teacher shortage education policy",
    "school curriculum standards state legislature",
    "student mental health schools policy",
    "education budget cuts Congress 2026",
    "charter school voucher legislation",
    "special education policy reform",
]

KEYWORDS = [
    "california", "k-12", "k12", "education", "school", "student",
    "artificial intelligence", "AI", "curriculum", "assessment",
    "legislature", "legislation", "bill", "policy", "learning"
]

CALIFORNIA_KEYWORDS = ["california", "cde", "lausd", "sacramento", "san francisco",
                       "los angeles", "san diego", "bay area", "silicon valley"]

AI_KEYWORDS = ["artificial intelligence", " ai ", "machine learning", "chatgpt",
               "generative", "algorithm", "automation", "technology", "digital",
               "computer", "coding", "data", "software", "robot", "stem"]

RSS_FEEDS = [
    # Policy & Legislation
    {"name": "K-12 Dive Policy",      "url": "https://www.k12dive.com/feeds/news/"},
    {"name": "Education Week",         "url": "https://www.edweek.org/feed/"},
    {"name": "eSchool News",           "url": "https://www.eschoolnews.com/feed/"},
    {"name": "THE Journal",            "url": "https://thejournal.com/rss-feeds/all-articles.aspx"},
    {"name": "Chalkbeat",              "url": "https://www.chalkbeat.org/rss/feed"},
    {"name": "The 74 Million",         "url": "https://the74million.org/feed/"},
    {"name": "EdSurge",                "url": "https://www.edsurge.com/news.rss"},
    {"name": "Hechinger Report",       "url": "https://hechingerreport.org/feed/"},
    # Government & Legislative
    {"name": "California DOE News",    "url": "https://www.cde.ca.gov/re/pn/rss/cdepressrel.xml"},
    {"name": "US Dept of Education",   "url": "https://www.ed.gov/news/rss"},
    # Research & Policy Think Tanks
    {"name": "Brookings Education",    "url": "https://www.brookings.edu/topic/education/feed/"},
    {"name": "RAND Education",         "url": "https://www.rand.org/topics/education-policy.xml"},
    {"name": "Thomas B. Fordham",      "url": "https://fordhaminstitute.org/national/research/feed"},
    # Teacher & Administrator Perspective
    {"name": "AASA School Leader",     "url": "https://www.aasa.org/rss/schooladministrator.aspx"},
    {"name": "NEA Today",              "url": "https://www.nea.org/rss.xml"},
]


# --- Database Setup ---

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


# --- Utilities ---

def article_id(url):
    return hashlib.md5(url.encode()).hexdigest()

def is_california_relevant(text):
    text_lower = text.lower()
    return any(kw in text_lower for kw in CALIFORNIA_KEYWORDS)

def is_ai_relevant(text):
    text_lower = text.lower()
    return any(kw in text_lower for kw in AI_KEYWORDS)

def is_relevant(title, summary, source):
    title_lower = title.lower()
    # California DOE feed is always California relevant
    if source == "California DOE News":
        return True, True
    ca = is_california_relevant(title_lower)
    ai = is_ai_relevant(title_lower)
    return ca, ai


# --- NewsAPI Collection ---

def collect_newsapi():
    if not NEWSAPI_KEY:
        print("No NEWSAPI_KEY set — skipping NewsAPI.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    new_count = 0

    for query in NEWSAPI_QUERIES:
        print(f"NewsAPI query: {query}...")
        try:
            params = {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 50,
                "apiKey": NEWSAPI_KEY,
            }
            response = requests.get(NEWSAPI_URL, params=params, timeout=15)
            if response.status_code != 200:
                print(f"  NewsAPI error: {response.status_code}")
                continue

            data = response.json()
            for article in data.get("articles", []):
                url = article.get("url", "")
                if not url:
                    continue

                aid = article_id(url)
                c.execute("SELECT id FROM articles WHERE id = ?", (aid,))
                if c.fetchone():
                    continue

                title = article.get("title", "")
                summary = article.get("description", "")
                published = article.get("publishedAt", str(datetime.now()))
                ca_rel, ai_rel = is_relevant(title, summary, "NewsAPI")
                ca_relevant = 1 if ca_rel else 0
                ai_relevant = 1 if ai_rel else 0

                c.execute("""
                    INSERT INTO articles
                    (id, source, title, url, published, summary, california_relevant, ai_relevant, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    aid, "NewsAPI", title, url, published,
                    summary, ca_relevant, ai_relevant,
                    str(datetime.now())
                ))
                new_count += 1

        except Exception as e:
            print(f"  Error with NewsAPI query '{query}': {e}")

    conn.commit()
    conn.close()
    print(f"NewsAPI: {new_count} new articles collected.")


# --- RSS Collection ---

def collect_feeds():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    new_count = 0

    for feed in RSS_FEEDS:
        print(f"Fetching: {feed['name']}...")
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries:
                url = entry.get("link", "")
                if not url:
                    continue

                aid = article_id(url)

                # Skip if already collected
                c.execute("SELECT id FROM articles WHERE id = ?", (aid,))
                if c.fetchone():
                    continue

                title = entry.get("title", "")
                summary = entry.get("summary", "")
                published = entry.get("published", str(datetime.now()))
                ca_rel, ai_rel = is_relevant(title, summary, feed["name"])
                ca_relevant = 1 if ca_rel else 0
                ai_relevant = 1 if ai_rel else 0

                c.execute("""
                    INSERT INTO articles
                    (id, source, title, url, published, summary, california_relevant, ai_relevant, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    aid, feed["name"], title, url, published,
                    summary, ca_relevant, ai_relevant,
                    str(datetime.now())
                ))
                new_count += 1

        except Exception as e:
            print(f"  Error fetching {feed['name']}: {e}")

    conn.commit()
    conn.close()
    print(f"\nCollected {new_count} new articles.")


# --- Multi-Model LLM Callers (from Hallucinations_1_28_26.py) ---

def call_openai(prompt):
    if not openai_client:
        return ("OpenAI", None)
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            temperature=0.5, max_tokens=300
        )
        return ("OpenAI", response.choices[0].message.content.strip())
    except Exception as e:
        return ("OpenAI", None)

def call_claude(prompt):
    if not anthropic_client:
        return ("Claude", None)
    try:
        msg = anthropic_client.messages.create(
            model="claude-3-5-haiku-20241022", max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return ("Claude", msg.content[0].text.strip())
    except Exception:
        return ("Claude", None)

def call_gemini(prompt):
    if not google_key:
        return ("Gemini", None)
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        return ("Gemini", response.text.strip())
    except Exception:
        return ("Gemini", None)

def call_cohere(prompt):
    if not cohere_key:
        return ("Cohere", None)
    try:
        co = cohere.Client(cohere_key)
        response = co.chat(message=prompt, model="command-r-08-2024",
                           max_tokens=300, temperature=0.5)
        return ("Cohere", response.text.strip())
    except Exception:
        return ("Cohere", None)

def call_deepseek(prompt):
    if not deepseek_key:
        return ("Deepseek", None)
    try:
        client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            temperature=0.5, max_tokens=300
        )
        return ("Deepseek", response.choices[0].message.content.strip())
    except Exception:
        return ("Deepseek", None)

def call_openrouter(prompt):
    if not openrouter_key:
        return ("OpenRouter", None)
    try:
        client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")
        response = client.chat.completions.create(
            model="microsoft/wizardlm-2-8x22b",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            temperature=0.5, max_tokens=300
        )
        return ("OpenRouter", response.choices[0].message.content.strip())
    except Exception:
        return ("OpenRouter", None)

def call_perplexity(prompt):
    if not perplexity_key:
        return ("Perplexity", None)
    try:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            json={"model": "sonar", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 300, "temperature": 0.5},
            headers={"authorization": f"Bearer {perplexity_key}",
                     "content-type": "application/json"},
            timeout=30
        )
        if response.status_code == 200:
            return ("Perplexity", response.json()["choices"][0]["message"]["content"].strip())
        return ("Perplexity", None)
    except Exception:
        return ("Perplexity", None)

def call_grok(prompt):
    if not grok_key:
        return ("Grok", None)
    try:
        client = OpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")
        response = client.chat.completions.create(
            model="grok-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5, max_tokens=300
        )
        return ("Grok", response.choices[0].message.content.strip())
    except Exception:
        return ("Grok", None)


# --- H-Score Calculation ---

def calculate_h_score(responses):
    """
    Calculate H-Score (0-10) from agreement across model responses.
    Higher score = more agreement = more reliable.
    """
    valid = [(name, r) for name, r in responses if r is not None]
    if len(valid) < 2:
        return None, {}

    # Use Claude to assess agreement across responses
    if not anthropic_client:
        # Fallback: score based on response count alone
        return round((len(valid) / 8) * 10, 1), {}

    summaries = "\n\n".join([f"{name}: {r[:200]}" for name, r in valid])
    prompt = f"""Rate the consistency of these AI model responses on a scale of 0-10.
10 = all models fully agree. 0 = complete contradiction.
Respond with ONLY a number between 0 and 10.

{summaries}"""

    try:
        msg = anthropic_client.messages.create(
            model="claude-3-5-haiku-20241022", max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )
        score_text = msg.content[0].text.strip()
        score = float(score_text.split()[0])
        score = max(0.0, min(10.0, score))
        return round(score, 1), {name: r[:200] for name, r in valid}
    except Exception:
        return round((len(valid) / 8) * 10, 1), {}


# --- Hallucinations.cloud Verification ---

def verify_articles():
    any_key = any([openai_key, anthropic_key, google_key, cohere_key,
                   deepseek_key, openrouter_key, perplexity_key, grok_key])
    if not any_key:
        print("No LLM API keys set — skipping verification.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT id, title, summary FROM articles
        WHERE ai_relevant = 1 AND h_score IS NULL
        LIMIT 50
    """)
    rows = c.fetchall()

    if not rows:
        print("No new articles to verify.")
        conn.close()
        return

    print(f"Verifying {len(rows)} articles across 8 LLMs...")

    for aid, title, summary in rows:
        prompt = (f"In one paragraph, summarize the key policy claim in this "
                  f"K-12 education article:\n\nTitle: {title}\n\n{summary[:500]}")

        print(f"  Querying models for: {title[:60]}...")
        responses = [
            call_openai(prompt),
            call_claude(prompt),
            call_gemini(prompt),
            call_cohere(prompt),
            call_deepseek(prompt),
            call_openrouter(prompt),
            call_perplexity(prompt),
            call_grok(prompt),
        ]

        h_score, model_data = calculate_h_score(responses)
        model_data["models_available"] = [name for name, r in responses if r is not None]

        if h_score is not None:
            c.execute("""
                UPDATE articles SET h_score = ?, h_response = ? WHERE id = ?
            """, (h_score, json.dumps(model_data), aid))
            print(f"    H-Score: {h_score}/10 ({len(model_data['models_available'])} models)")
        else:
            print(f"    Could not score — insufficient model responses")

        time.sleep(1)

    conn.commit()
    conn.close()


# --- Report ---

def report():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM articles")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM articles WHERE california_relevant = 1 AND ai_relevant = 1")
    relevant = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM articles WHERE h_score IS NOT NULL")
    verified = c.fetchone()[0]

    print(f"\n--- Database Report ---")
    print(f"Total articles:        {total}")
    print(f"CA + AI relevant:      {relevant}")
    print(f"Verified (H-Score):    {verified}")

    print(f"\n--- Recent Verified Articles ---")
    c.execute("""
        SELECT title, source, h_score, published FROM articles
        WHERE h_score IS NOT NULL
        ORDER BY published DESC LIMIT 10
    """)
    for row in c.fetchall():
        print(f"  [{row[2]:.2f}] {row[0][:70]} ({row[1]})")

    conn.close()


# --- Main ---

if __name__ == "__main__":
    print("Initializing database...")
    init_db()

    print("Collecting RSS feeds...")
    collect_feeds()

    print("Collecting from NewsAPI...")
    collect_newsapi()

    print("Scraping California Legislature...")
    try:
        from legislature_scraper import scrape_bills
        scrape_bills()
    except Exception as e:
        print(f"Legislature scraper error: {e}")

    print("Verifying relevant articles...")
    verify_articles()

    report()
