"""
K-12 AI Education Policy Dashboard
Run with: streamlit run dashboard.py
"""

import streamlit as st
import json
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import db

st.set_page_config(page_title="K-12 AI Policy Intelligence", layout="wide")

st.title("K-12 AI Education Policy Intelligence")
st.caption("Powered by hallucinations.cloud multi-model verification")


# --- Sidebar ---

st.sidebar.header("Filters")
filter_verified = st.sidebar.checkbox("Verified only (H-Score)", value=False)
filter_ai       = st.sidebar.checkbox("AI-relevant only", value=False)
search_term     = st.sidebar.text_input("Search titles", "")
sort_by         = st.sidebar.selectbox("Sort by", ["Newest", "H-Score"])

if st.sidebar.button("Refresh"):
    st.cache_data.clear()
    st.rerun()


# --- Stats ---

total, verified, ai_rel, avg_score, sources = db.get_stats()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Articles", total)
c2.metric("AI Relevant", ai_rel)
c3.metric("H-Score Verified", verified)
c4.metric("Avg H-Score", f"{avg_score:.1f}/10")
c5.metric("Sources", sources)

st.markdown("---")


# --- Article Cards ---

sort_field = "h_score" if sort_by == "H-Score" else "published"
articles = db.get_articles(
    verified_only=filter_verified,
    ai_only=filter_ai,
    search=search_term if search_term else None,
    sort_by=sort_field,
    limit=200
)

if not articles:
    st.info("No articles match the current filters.")
else:
    st.subheader(f"{len(articles)} articles")
    for row in articles:
        h_score  = row.get("h_score")
        title    = row.get("title") or "Untitled"
        source   = row.get("source") or ""
        url      = row.get("url") or ""
        summary  = row.get("summary") or ""
        published = row.get("published") or ""

        if h_score is None:
            color, label = "#888888", "Unverified"
        elif h_score >= 8:
            color, label = "#2ecc71", f"H-Score: {h_score}/10"
        elif h_score >= 6:
            color, label = "#f39c12", f"H-Score: {h_score}/10"
        else:
            color, label = "#e74c3c", f"H-Score: {h_score}/10"

        with st.container():
            col_score, col_content = st.columns([1, 8])
            with col_score:
                st.markdown(
                    f"<div style='background:{color};color:white;padding:10px;"
                    f"border-radius:8px;text-align:center;font-weight:bold;"
                    f"font-size:13px'>{label}</div>",
                    unsafe_allow_html=True
                )
            with col_content:
                st.markdown(f"**[{title}]({url})**" if url else f"**{title}**")
                clean = summary.split(">")[-1][:200] if "<" in summary else summary[:200]
                if clean.strip():
                    st.caption(clean)
                st.caption(f"{source}  |  {published[:10]}")
                if h_score is not None and row.get("h_response"):
                    with st.expander("Model responses"):
                        try:
                            data = json.loads(row["h_response"])
                            for model, response in data.items():
                                if model != "models_available" and isinstance(response, str):
                                    st.markdown(f"**{model}:** {response}")
                        except Exception:
                            st.write(row["h_response"])
            st.markdown("---")


# --- Full Article List ---

st.subheader("All Collected Articles")

all_articles = db.get_articles(limit=2000, sort_by="published")

rows = []
for a in all_articles:
    date = a.get("published", "")[:10]
    title = a.get("title", "")
    url = a.get("url", "")
    source = a.get("source", "")
    rows.append({"Date": date, "Title": f"[{title}]({url})" if url else title, "Source": source})

import pandas as pd
df = pd.DataFrame(rows)
if not df.empty:
    df = df.sort_values("Date", ascending=False)
    st.dataframe(df, use_container_width=True, height=600, hide_index=True)
