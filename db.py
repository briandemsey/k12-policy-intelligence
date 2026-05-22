"""
Database abstraction — wraps Supabase REST API.
Used by both collector.py and dashboard.py.
"""

import os
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://evmqoirorcpkurxlqsed.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def headers():
    return {"apikey": SUPABASE_KEY, "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates"}

def article_exists(aid):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/articles?id=eq.{aid}&select=id",
        headers=headers()
    )
    return len(r.json()) > 0

def insert_article(row):
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/articles",
        headers=headers(),
        json=row
    )
    return r.status_code in (200, 201)

def update_h_score(aid, h_score, h_response):
    import json
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/articles?id=eq.{aid}",
        headers=headers(),
        json={"h_score": h_score, "h_response": json.dumps(h_response)}
    )
    return r.status_code in (200, 204)

def get_articles(verified_only=False, ai_only=False, search=None,
                 sort_by="published", date_from=None, limit=1000):
    params = f"?limit={limit}"
    if verified_only:
        params += "&h_score=not.is.null"
    if ai_only:
        params += "&ai_relevant=eq.1"
    if search:
        params += f"&title=ilike.*{search}*"
    if date_from:
        params += f"&published=gte.{date_from}"
    if sort_by == "h_score":
        params += "&order=h_score.desc.nullslast"
    else:
        params += "&order=published.desc"

    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/articles{params}&select=*",
        headers={**headers(), "Range": f"0-{limit-1}",
                 "Prefer": "count=exact"}
    )
    return r.json() if r.status_code in (200, 206) else []

def get_stats():
    def count(params=""):
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/articles{params}",
            headers={**headers(), "Prefer": "count=exact", "Range": "0-0"}
        )
        cr = r.headers.get("Content-Range", "0/0")
        return int(cr.split("/")[-1]) if "/" in cr else 0

    total    = count()
    verified = count("?h_score=not.is.null")
    ai_rel   = count("?ai_relevant=eq.1")

    # Average h_score
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/articles?h_score=not.is.null&select=h_score",
        headers=headers()
    )
    scores = [x["h_score"] for x in r.json() if x.get("h_score") is not None]
    avg = sum(scores) / len(scores) if scores else 0

    # Source count
    r2 = requests.get(
        f"{SUPABASE_URL}/rest/v1/articles?select=source",
        headers=headers()
    )
    sources = len(set(x["source"] for x in r2.json() if x.get("source")))

    return total, verified, ai_rel, avg, sources
