"""
Sentiment Pipeline Dashboard
Streamlit app that displays real-time financial news sentiment
for 10 tracked tickers, powered by the sentiment-pipeline API.
"""

import streamlit as st
import requests
import json
import time
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────
API_BASE = "https://cwf1zzg2o9.execute-api.us-east-1.amazonaws.com"
COGNITO_ENDPOINT = "https://cognito-idp.us-east-1.amazonaws.com"
COGNITO_CLIENT_ID = "6a37hlq5pkgjmem95ldvpj3v7u"

SENTIMENT_COLORS = {
    "positive": "#10b981",
    "negative": "#ef4444",
    "neutral": "#6b7fa3",
}

st.set_page_config(
    page_title="Sentiment Pipeline",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom Styling ────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');

    .block-container { padding-top: 2rem; }

    div[data-testid="stMetric"] {
        background: rgba(20, 26, 35, 0.5);
        border: 1px solid rgba(30, 42, 58, 0.8);
        border-radius: 10px;
        padding: 16px 20px;
    }

    div[data-testid="stMetric"] label {
        font-size: 12px !important;
        color: #8892a4 !important;
    }

    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 24px !important;
    }

    .ticker-btn {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 600;
    }

    .article-card {
        padding: 12px 0;
        border-bottom: 1px solid rgba(30, 42, 58, 0.6);
    }

    .sentiment-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 8px;
    }

    .pos-dot { background: #10b981; }
    .neg-dot { background: #ef4444; }
    .neu-dot { background: #6b7fa3; opacity: 0.5; }
</style>
""", unsafe_allow_html=True)


# ── Auth Functions ────────────────────────────────────
def authenticate(email: str, password: str) -> str | None:
    """Authenticate with Cognito and return an ID token."""
    try:
        res = requests.post(
            COGNITO_ENDPOINT,
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            },
            json={
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": COGNITO_CLIENT_ID,
                "AuthParameters": {"USERNAME": email, "PASSWORD": password},
            },
        )
        data = res.json()
        if "AuthenticationResult" in data:
            return data["AuthenticationResult"]["IdToken"]
        return None
    except Exception:
        return None


def api_get(path: str) -> dict | None:
    """Make an authenticated GET request to the sentiment API."""
    token = st.session_state.get("token")
    if not token:
        return None
    try:
        res = requests.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if res.status_code == 401:
            st.session_state.token = None
            st.rerun()
        return res.json()
    except Exception as e:
        st.error(f"API request failed: {e}")
        return None


# ── Visualization Helpers ─────────────────────────────
def sentiment_bar(positive_pct, negative_pct, neutral_pct):
    """Render a horizontal stacked sentiment bar."""
    total = positive_pct + negative_pct + neutral_pct
    if total == 0:
        return
    st.markdown(f"""
    <div style="display:flex; height:8px; border-radius:4px; overflow:hidden; gap:2px; margin:8px 0;">
        <div style="flex:{max(positive_pct, 0.5)}; background:#10b981; border-radius:2px;"></div>
        <div style="flex:{max(negative_pct, 0.5)}; background:#ef4444; border-radius:2px;"></div>
        <div style="flex:{max(neutral_pct, 0.5)}; background:#6b7fa3; opacity:0.4; border-radius:2px;"></div>
    </div>
    """, unsafe_allow_html=True)


def render_history_chart(history_data):
    """Render a stacked bar chart of daily sentiment counts."""
    if not history_data or not history_data.get("history"):
        st.info("No historical data available yet.")
        return

    days = list(reversed(history_data["history"]))  # oldest first

    # Filter to last 14 days to avoid old scattered data stretching the x-axis
    cutoff = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    days = [d for d in days if d["day"] >= cutoff]

    if not days:
        st.info("No recent historical data available.")
        return

    dates = [d["day"] for d in days]
    pos = [d["positive"] for d in days]
    neg = [d["negative"] for d in days]
    neu = [d["neutral"] for d in days]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Positive", x=dates, y=pos,
                         marker_color="rgba(16,185,129,0.75)",
                         hovertemplate="%{x}<br>Positive: %{y}<extra></extra>"))
    fig.add_trace(go.Bar(name="Negative", x=dates, y=neg,
                         marker_color="rgba(239,68,68,0.75)",
                         hovertemplate="%{x}<br>Negative: %{y}<extra></extra>"))
    fig.add_trace(go.Bar(name="Neutral", x=dates, y=neu,
                         marker_color="rgba(107,127,163,0.35)",
                         hovertemplate="%{x}<br>Neutral: %{y}<extra></extra>"))

    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8892a4", family="JetBrains Mono, monospace"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=40, b=40),
        height=320,
        xaxis=dict(gridcolor="rgba(30,42,58,0.5)", dtick="D1", tickformat="%b %d"),
        yaxis=dict(gridcolor="rgba(30,42,58,0.5)", title="Articles"),
        hoverlabel=dict(
            bgcolor="#1e293b",
            font_size=13,
            font_family="JetBrains Mono, monospace",
            font_color="#f1f5f9",
            bordercolor="#334155",
        ),
    )

    st.plotly_chart(fig, use_container_width=True)


def format_time_ago(iso_str: str) -> str:
    """Format ISO timestamp as relative time."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo)
        diff = now - dt
        hours = diff.total_seconds() / 3600
        if hours < 1:
            return f"{int(diff.total_seconds() / 60)}m ago"
        if hours < 24:
            return f"{int(hours)}h ago"
        return dt.strftime("%b %d")
    except Exception:
        return iso_str[:10]


# ── Login Screen ──────────────────────────────────────
def render_login():
    """Render the login sidebar and block the main area."""
    st.title("📊 Sentiment Pipeline")
    st.caption("Financial news sentiment dashboard for 10 tracked tickers.")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        if not email or not password:
            st.error("Enter both email and password.")
            return
        with st.spinner("Authenticating..."):
            token = authenticate(email, password)
        if token:
            st.session_state.token = token
            st.rerun()
        else:
            st.error("Invalid credentials. Check your email and password.")


# ── Overview Page ─────────────────────────────────────
def render_overview():
    """Render the 10-ticker overview grid."""
    data = api_get("/sentiment")
    if not data:
        st.error("Failed to load sentiment data.")
        return

    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("📊 Sentiment Pipeline")
    with col2:
        st.caption(f"Updated {datetime.now().strftime('%H:%M')}")
        if st.button("🔄 Refresh"):
            st.rerun()

    # Health check
    try:
        health = requests.get(f"{API_BASE}/health", timeout=15).json()
        if health.get("status") == "healthy":
            st.success("All systems healthy", icon="✅")
        else:
            st.info("System warming up — FinBERT may need a moment on first request", icon="⏳")
    except Exception:
        st.info("Health check timed out — this is normal on first load (cold start)", icon="⏳")

    st.divider()

    # Ticker grid: 5 columns × 2 rows
    tickers = data.get("tickers", [])
    for row_start in range(0, len(tickers), 5):
        row = tickers[row_start:row_start + 5]
        cols = st.columns(len(row))
        for col, t in zip(cols, row):
            with col:
                a = t["aggregate"]
                badge_color = SENTIMENT_COLORS.get(a["label"], "#6b7fa3")

                st.markdown(f"**`{t['ticker']}`**")
                st.markdown(
                    f'<span style="background:{badge_color}22; color:{badge_color}; '
                    f'padding:2px 10px; border-radius:12px; font-size:12px; font-weight:600;">'
                    f'{a["label"].capitalize()}</span>',
                    unsafe_allow_html=True,
                )
                sentiment_bar(a["positive_pct"], a["negative_pct"], a["neutral_pct"])
                st.caption(f'{a["article_count"]} articles · {a["avg_confidence"]*100:.0f}% conf')

                if st.button("View details", key=f"btn_{t['ticker']}", use_container_width=True):
                    st.session_state.selected_ticker = t["ticker"]
                    st.rerun()


# ── Detail Page ───────────────────────────────────────
def render_detail(ticker: str):
    """Render the detail view for a single ticker."""
    # Back button
    if st.button("← All tickers"):
        st.session_state.selected_ticker = None
        st.rerun()

    # Load data in parallel (Streamlit is sync, so sequential)
    ticker_data = api_get(f"/sentiment/{ticker}")
    history_data = api_get(f"/sentiment/{ticker}/history")

    if not ticker_data:
        st.error("Failed to load ticker data.")
        return

    a = ticker_data["aggregate"]
    badge_color = SENTIMENT_COLORS.get(a["label"], "#6b7fa3")

    # Header
    st.markdown(
        f'# `{ticker}` &nbsp; '
        f'<span style="background:{badge_color}22; color:{badge_color}; '
        f'padding:4px 14px; border-radius:14px; font-size:16px; font-weight:600; '
        f'vertical-align:middle;">{a["label"].capitalize()}</span>',
        unsafe_allow_html=True,
    )

    # Stats row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Positive", f'{a["positive_pct"]}%')
    c2.metric("Negative", f'{a["negative_pct"]}%')
    c3.metric("Neutral", f'{a["neutral_pct"]}%')
    c4.metric("Avg Confidence", f'{a["avg_confidence"]*100:.1f}%')
    c5.metric("Articles", a["article_count"])

    st.divider()

    # History chart
    st.subheader("Daily sentiment breakdown")
    render_history_chart(history_data)

    st.divider()

    # Recent articles
    st.subheader("Recent articles")
    articles = ticker_data.get("recent_articles", [])
    if not articles:
        st.info("No recent articles.")
        return

    for art in articles:
        s = art.get("sentiment", "neutral")
        dot_class = "pos-dot" if s == "positive" else "neg-dot" if s == "negative" else "neu-dot"
        color = SENTIMENT_COLORS.get(s, "#6b7fa3")
        conf = art.get("confidence", 0) * 100
        time_ago = format_time_ago(art.get("published_at", ""))

        url = art.get("url", "")
        headline = art.get("headline", "")
        source = art.get("source", "")

        # Make headline a clickable link if URL exists
        if url:
            headline_html = f'<a href="{url}" target="_blank" style="color:inherit; text-decoration:none; border-bottom:1px dotted #4a5568;">{headline}</a>'
            source_html = f'<a href="{url}" target="_blank" style="color:#4a5568; text-decoration:none;">🔗 {source}</a>'
        else:
            headline_html = headline
            source_html = source

        st.markdown(
            f'<div class="article-card">'
            f'<span class="sentiment-dot {dot_class}"></span>'
            f'<strong>{headline_html}</strong>'
            f'<br><span style="font-size:12px; font-family:JetBrains Mono,monospace;">'
            f'{source_html} · {time_ago} · '
            f'<span style="color:{color};">{conf:.0f}% {s}</span>'
            f'</span></div>',
            unsafe_allow_html=True,
        )


# ── Main ──────────────────────────────────────────────
def main():
    # Init session state
    if "token" not in st.session_state:
        st.session_state.token = None
    if "selected_ticker" not in st.session_state:
        st.session_state.selected_ticker = None

    # Auth gate
    if not st.session_state.token:
        render_login()
        return

    # Sidebar
    with st.sidebar:
        st.markdown("**📊 Sentiment Pipeline**")
        st.caption("Financial news sentiment for 10 tickers, scored by FinBERT.")
        st.divider()
        st.caption("Refreshes every 5 minutes.")
        st.caption(f"Session active since {datetime.now().strftime('%H:%M')}")
        if st.button("Sign out", use_container_width=True):
            st.session_state.token = None
            st.session_state.selected_ticker = None
            st.rerun()

    # Route
    if st.session_state.selected_ticker:
        render_detail(st.session_state.selected_ticker)
    else:
        render_overview()


if __name__ == "__main__":
    main()
