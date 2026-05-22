"""
Simple verifier - uses OpenAI gpt-4o-mini, writes directly to Supabase.
Run: python verify_simple.py
"""

import os, json, time, requests
from openai import OpenAI

SUPABASE_URL = "https://evmqoirorcpkurxlqsed.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

def get_unverified(limit=20):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/articles"
        f"?ai_relevant=eq.1&h_score=is.null&select=id,title,summary&limit={limit}",
        headers={"apikey": SUPABASE_KEY}
    )
    return r.json()

def verify_with_openai(title, summary):
    client = OpenAI(api_key=OPENAI_KEY)
    prompt = (
        f"Rate the factual reliability of this K-12 education article on a scale of 0-10. "
        f"10 = highly factual and specific. 0 = vague or unverifiable. "
        f"Reply with ONLY a number.\n\nTitle: {title}\n\n{summary[:300]}"
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}]
    )
    score = float(response.choices[0].message.content.strip().split()[0])
    return round(max(0.0, min(10.0, score)), 1)

def save_score(aid, score):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/articles?id=eq.{aid}",
        headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"},
        json={"h_score": score, "h_response": json.dumps({"OpenAI": score, "models_available": ["OpenAI"]})}
    )
    return r.status_code in (200, 204)

if __name__ == "__main__":
    articles = get_unverified(limit=20)
    print(f"Verifying {len(articles)} articles with OpenAI...")
    for a in articles:
        try:
            score = verify_with_openai(a["title"], a.get("summary", ""))
            ok = save_score(a["id"], score)
            print(f"  [{score}/10] {'OK' if ok else 'SAVE FAILED'} - {a['title'][:60]}")
            time.sleep(0.5)
        except Exception as e:
            print(f"  ERROR: {a['title'][:50]} - {e}")
    print("Done.")
