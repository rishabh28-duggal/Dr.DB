import re

import streamlit as st

from Analyzer import parse_query, analyze_query
from optimizer import optimize_query
from validator import (
    validate_optimized_query,
    extract_schema,
    validate_tables,
)
from scoring import calculate_health_score, calculate_impact_score


# ============================================================
# BUILT-IN DEMO EXAMPLES
# ============================================================

EXAMPLES = {
    "Correlated Subquery": {
        "query": """SELECT
    u.id,
    u.name,
    (
        SELECT COUNT(*)
        FROM orders o
        WHERE o.user_id = u.id
    ) AS order_count
FROM users u;""",
        "schema": """CREATE TABLE users (
    id INTEGER,
    name TEXT,
    email TEXT
);

CREATE TABLE orders (
    id INTEGER,
    user_id INTEGER,
    amount DECIMAL,
    created_at TIMESTAMP
);""",
    },
    "Leading Wildcard Search": {
        "query": """SELECT
    id,
    name,
    email
FROM users
WHERE name LIKE '%john';""",
        "schema": """CREATE TABLE users (
    id INTEGER,
    name TEXT,
    email TEXT
);""",
    },
    "Function on Filtered Column": {
        "query": """SELECT
    id,
    user_id,
    amount
FROM orders
WHERE DATE(created_at) = '2026-09-15';""",
        "schema": """CREATE TABLE orders (
    id INTEGER,
    user_id INTEGER,
    amount DECIMAL,
    created_at TIMESTAMP
);""",
    },
}


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Dr.DB",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION STATE
# ============================================================

if "input_mode" not in st.session_state:
    st.session_state.input_mode = "write"

if "sql_input" not in st.session_state:
    st.session_state.sql_input = ""

if "schema_input" not in st.session_state:
    st.session_state.schema_input = ""

if "selected_example" not in st.session_state:
    st.session_state.selected_example = list(EXAMPLES.keys())[0]

if "page" not in st.session_state:
    st.session_state.page = "Home"

# Holds the last completed analysis so it stays on screen across reruns
# (editing the schema box, switching tabs, etc.) instead of vanishing
# the moment you touch anything that isn't the Analyze button.
if "result" not in st.session_state:
    st.session_state.result = None


def choose_write_mode():
    st.session_state.input_mode = "write"
    st.session_state.sql_input = ""
    st.session_state.schema_input = ""


def choose_example_mode():
    st.session_state.input_mode = "example"
    example = EXAMPLES[st.session_state.selected_example]
    st.session_state.sql_input = example["query"]
    st.session_state.schema_input = example["schema"]


def load_selected_example():
    example = EXAMPLES[st.session_state.selected_example]
    st.session_state.sql_input = example["query"]
    st.session_state.schema_input = example["schema"]


def go_to(target_page):
    st.session_state.page = target_page


# ============================================================
# VISUAL SYSTEM
#
# One accent hue drives the whole product: teal, running into a
# deeper indigo at the edges (a "clinical + technical" pairing).
# Severity colors (green/amber/red) are kept ONLY for semantic
# status (health score, impact, issue severity) — never for
# generic UI chrome like buttons or nav.
# ============================================================

ACCENT = "#0f766e"        # teal-700 — primary actions, selected states
ACCENT_DARK = "#0b5c56"   # hover/active
ACCENT_SOFT = "rgba(15, 118, 110, 0.10)"
ACCENT_SOFT_BORDER = "rgba(15, 118, 110, 0.28)"
INDIGO = "#4338ca"        # gradient end / secondary brand note

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap');

:root {{
    --drdb-radius: 14px;
    --drdb-accent: {ACCENT};
    --drdb-accent-dark: {ACCENT_DARK};
    --drdb-accent-soft: {ACCENT_SOFT};
    --drdb-accent-border: {ACCENT_SOFT_BORDER};
}}

html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}}

.block-container {{
    max-width: 1120px;
    padding-top: 2.8rem;
    padding-bottom: 1.5rem;
}}

/* Keep typography intentionally limited to three practical sizes. */
h1 {{ font-size: 2rem !important; margin: 0 !important; font-family: 'Sora', sans-serif; }}
h2, h3 {{ font-size: 1.22rem !important; margin-top: 0.45rem !important; font-family: 'Sora', sans-serif; }}
p, label, li, div {{ font-size: 0.95rem; }}

/* ---------- Hero: eyebrow + title + subtitle + feature chips ---------- */
.drdb-banner {{
    padding: 1.15rem 1.5rem;
    border-radius: 18px;
    background: linear-gradient(115deg, {ACCENT} 0%, {INDIGO} 100%);
    color: white;
    margin-bottom: 0.65rem;
    box-shadow: 0 16px 34px rgba(15, 118, 110, 0.22);
}}
.drdb-eyebrow {{
    font-size: 0.74rem !important;
    font-weight: 700;
    letter-spacing: 0.11em;
    text-transform: uppercase;
    opacity: 0.82;
    margin-bottom: 0.25rem;
}}
.drdb-banner-title {{
    font-family: 'Sora', sans-serif;
    font-size: 2.05rem !important;
    font-weight: 760;
    line-height: 1.08;
    margin-bottom: 0.2rem;
}}
.drdb-banner-subtitle {{
    font-size: 0.98rem !important;
    opacity: 0.96;
    margin: 0 0 0.55rem 0;
    max-width: 640px;
}}
.drdb-chip-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.drdb-chip {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: 999px;
    background: rgba(255,255,255,0.16);
    border: 1px solid rgba(255,255,255,0.24);
    font-size: 0.8rem !important;
    font-weight: 600;
}}

[data-testid="stMetric"] {{
    background: rgba(127, 127, 127, 0.055);
    border: 1px solid rgba(127, 127, 127, 0.16);
    padding: 14px 16px;
    border-radius: var(--drdb-radius);
}}
[data-testid="stMetricValue"] {{
    font-size: 1.45rem !important;
    font-weight: 700;
}}

textarea {{
    font-family: "JetBrains Mono", "Courier New", monospace !important;
    font-size: 0.9rem !important;
}}

/* ---------- Buttons: accent-driven, not theme-default red ---------- */
.stButton > button {{
    border-radius: 10px;
    font-weight: 650;
    min-height: 2.65rem;
    transition: background-color 0.15s ease, border-color 0.15s ease;
}}

.stButton > button[kind="primary"] {{
    background-color: var(--drdb-accent);
    border-color: var(--drdb-accent);
    color: white;
}}
.stButton > button[kind="primary"]:hover {{
    background-color: var(--drdb-accent-dark);
    border-color: var(--drdb-accent-dark);
}}
.stButton > button[kind="primary"]:focus:not(:active) {{
    color: white;
}}

.stButton > button[kind="secondary"] {{
    background-color: transparent;
    border: 1px solid var(--drdb-accent-border);
    color: var(--drdb-accent);
}}
.stButton > button[kind="secondary"]:hover {{
    background-color: var(--drdb-accent-soft);
    border-color: var(--drdb-accent);
    color: var(--drdb-accent-dark);
}}

/* ---------- Sidebar nav: plain button list, not the default st.radio ---------- */
section[data-testid="stSidebar"] .stButton > button {{
    justify-content: flex-start;
    text-align: left;
    font-weight: 600;
    padding-left: 12px;
    min-height: 2.35rem;
}}
section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
    background-color: transparent;
    border: none;
    color: #4b5563;
}}
section[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {{
    background-color: var(--drdb-accent-soft);
    border: none;
    color: var(--drdb-accent-dark);
}}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background-color: var(--drdb-accent-soft);
    border: none;
    color: var(--drdb-accent-dark);
}}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {{
    background-color: var(--drdb-accent-soft);
    color: var(--drdb-accent-dark);
}}

/* ---------- Links / selectbox focus ring in accent, not red ---------- */
a, a:visited {{ color: var(--drdb-accent); }}
[data-baseweb="select"]:focus-within > div {{
    border-color: var(--drdb-accent) !important;
    box-shadow: 0 0 0 1px var(--drdb-accent) !important;
}}

[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: var(--drdb-radius);
}}

code {{ font-size: 0.86rem !important; }}

.drdb-impact {{
    padding: 14px 16px;
    border-radius: var(--drdb-radius);
    border: 1px solid rgba(127,127,127,0.16);
    min-height: 92px;
}}
.drdb-impact-label {{
    font-size: 0.9rem !important;
    opacity: 0.72;
    margin-bottom: 0.45rem;
}}
.drdb-impact-value {{
    font-size: 1.45rem !important;
    font-weight: 750;
}}
/* Semantic severity colors — intentionally NOT the brand accent */
.impact-low {{ background: rgba(34, 197, 94, 0.12); }}
.impact-medium {{ background: rgba(234, 179, 8, 0.14); }}
.impact-high {{ background: rgba(239, 68, 68, 0.12); }}

.health-wrap {{
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 12px 14px;
    border: 1px solid rgba(127,127,127,0.16);
    border-radius: var(--drdb-radius);
    min-height: 92px;
}}
.health-donut {{
    width: 58px;
    height: 58px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    position: relative;
    flex: 0 0 58px;
}}
.health-donut::after {{
    content: "";
    width: 42px;
    height: 42px;
    border-radius: 50%;
    background: var(--background-color, white);
    position: absolute;
}}
.health-number {{
    position: relative;
    z-index: 1;
    font-size: 0.88rem !important;
    font-weight: 750;
}}
.health-copy strong {{ font-size: 1.1rem !important; }}
.health-copy span {{ font-size: 0.86rem !important; opacity: 0.7; }}

/* ---------- Empty state (before the first analysis has run) ---------- */
.drdb-empty {{
    border: 1.5px dashed rgba(127,127,127,0.3);
    border-radius: var(--drdb-radius);
    padding: 2.4rem 1.5rem;
    text-align: center;
    color: #6b7280;
    margin-top: 0.4rem;
}}
.drdb-empty-icon {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
.drdb-empty-title {{ font-weight: 700; color: #374151; font-size: 1rem; margin-bottom: 0.25rem; }}
.drdb-empty-sub {{ font-size: 0.88rem; max-width: 420px; margin: 0 auto; }}

/* ---------- Feature cards (About page) ---------- */
.drdb-feature-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin: 1.1rem 0 0.4rem 0;
}}
.drdb-feature-card {{
    border: 1px solid rgba(127,127,127,0.16);
    border-radius: var(--drdb-radius);
    padding: 16px 16px 18px 16px;
}}
.drdb-feature-icon {{ font-size: 1.35rem; margin-bottom: 8px; }}
.drdb-feature-title {{ font-weight: 700; font-size: 0.96rem; margin-bottom: 4px; color: #1f2937; }}
.drdb-feature-desc {{ font-size: 0.87rem; color: #6b7280; line-height: 1.5; }}

/* ---------- Step timeline (How Dr.DB Works page) ---------- */
.drdb-steps {{ margin: 1.2rem 0 0.6rem 0; }}
.drdb-step {{ display: flex; gap: 16px; position: relative; padding-bottom: 26px; }}
.drdb-step:last-child {{ padding-bottom: 0; }}
.drdb-step-num {{
    flex: 0 0 34px;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: var(--drdb-accent);
    color: white;
    font-weight: 700;
    font-size: 0.92rem;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    z-index: 1;
}}
.drdb-step:not(:last-child) .drdb-step-num::after {{
    content: "";
    position: absolute;
    top: 34px;
    left: 50%;
    transform: translateX(-50%);
    width: 2px;
    height: 26px;
    background: var(--drdb-accent-border);
}}
.drdb-step-title {{ font-weight: 700; font-size: 1rem; margin-bottom: 3px; color: #1f2937; }}
.drdb-step-desc {{ font-size: 0.89rem; color: #6b7280; line-height: 1.55; }}

/* ---------- Callout box (limitations, notes) ---------- */
.drdb-callout {{
    border-left: 3px solid var(--drdb-accent);
    background: var(--drdb-accent-soft);
    border-radius: 0 10px 10px 0;
    padding: 12px 16px;
    font-size: 0.9rem;
    color: #374151;
    margin: 0.9rem 0;
}}

footer {{ visibility: hidden; }}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

NAV_ITEMS = [
    ("Home", "Home"),
    ("About", "About"),
    ("How Dr.DB works", "How Dr.DB works"),
]

with st.sidebar:
    st.markdown("### 🩺 Dr.DB")
    for key, label in NAV_ITEMS:
        st.button(
            label,
            key=f"nav_{key}",
            use_container_width=True,
            type="primary" if st.session_state.page == key else "secondary",
            on_click=go_to,
            args=(key,),
        )
    st.divider()

page = st.session_state.page


# ============================================================
# HELPERS
# ============================================================


def md_escape(text):
    """Neutralize stray markdown characters in AI-generated text.

    The optimizer's output is free-form text from a language model, and it
    sometimes includes its own asterisks/underscores for emphasis. When that
    collides with markdown *we* add (like the "**1. ...**" numbering on the
    Changes Made list), the two sets of markers get tangled and Streamlit
    renders a broken mix of bold/italic with a stray "*" character left over.
    Escaping the model's text makes our own formatting the only formatting
    that's ever applied.
    """
    if not text:
        return ""
    return re.sub(r"([*_`\[\]])", r"\\\1", str(text))


def render_api_error(error):
    message = str(error).lower()

    token_or_context_terms = [
        "token",
        "context_length",
        "context length",
        "maximum context",
        "too large",
        "request too large",
    ]

    rate_or_quota_terms = [
        "rate limit",
        "rate_limit",
        "quota",
        "too many requests",
        "429",
    ]

    if any(term in message for term in token_or_context_terms):
        st.error(
            "This request is too large for the AI optimizer. Shorten the SQL or schema and try again."
        )
    elif any(term in message for term in rate_or_quota_terms):
        st.error(
            "Dr.DB could not connect to the AI optimizer because the Groq API limit or quota was reached. Please try again shortly."
        )
    else:
        st.error(
            "Dr.DB could not connect to the Groq AI optimizer. Please check the API configuration or try again."
        )

    with st.expander("Technical details"):
        st.code(str(error))


def impact_class(impact):
    impact = impact.upper()
    if impact == "LOW":
        return "impact-low"
    if impact == "HIGH":
        return "impact-high"
    return "impact-medium"


def health_color(score):
    if score >= 80:
        return "#22c55e"
    if score >= 55:
        return "#eab308"
    return "#ef4444"


def render_results(result):
    """Render a completed analysis. Reads from a plain dict so the same
    results can be re-displayed on later reruns without re-running the
    pipeline (see the `result` session-state note above)."""

    sql_query = result["sql_query"]
    schema = result["schema"]
    optimized_query = result["optimized_query"]
    issues = result["issues"]
    health_score = result["health_score"]
    expected_impact = result["expected_impact"]
    impact_score = result["impact_score"]
    recommended_indexes = result["recommended_indexes"]
    changes = result["changes"]

    # ====================================================
    # QUERY COMPARISON — FIRST RESULT
    # ====================================================

    st.divider()
    st.subheader("Query Comparison")

    original_col, optimized_col = st.columns(2, gap="medium")
    with original_col:
        st.markdown("**Original Query**")
        st.code(sql_query, language="sql")
    with optimized_col:
        st.markdown("**Optimized Query**")
        st.code(optimized_query, language="sql")

    validation_text = "✓ Optimized SQL passed syntax validation"
    if schema.strip():
        validation_text += "  ·  ✓ Tables match the provided schema"
    st.caption(validation_text)

    # ====================================================
    # ANALYSIS SUMMARY
    # ====================================================

    st.subheader("Analysis Summary")
    metric1, metric2, metric3, metric4 = st.columns(4)

    color = health_color(health_score)
    with metric1:
        st.markdown(
            f"""
            <div class="health-wrap">
                <div class="health-donut" style="background: conic-gradient({color} {health_score}%, rgba(127,127,127,0.18) 0);">
                    <span class="health-number">{health_score}</span>
                </div>
                <div class="health-copy"><strong>Query Health</strong><br><span>out of 100</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with metric2:
        st.metric("Issues Found", len(issues))

    with metric3:
        st.markdown(
            f"""
            <div class="drdb-impact {impact_class(expected_impact)}">
                <div class="drdb-impact-label">Expected Impact</div>
                <div class="drdb-impact-value">{expected_impact}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with metric4:
        st.metric("Indexes Suggested", len(recommended_indexes))

    # ====================================================
    # CHANGES MADE — DROPDOWN IMMEDIATELY AFTER SUMMARY
    # ====================================================

    with st.expander("Changes Made", expanded=True):
        if changes:
            for number, change in enumerate(changes, start=1):
                change_text = md_escape(change.get("change", "Change"))
                reason_text = md_escape(change.get("reason", ""))
                st.markdown(f"**{number}. {change_text}**")
                if reason_text:
                    st.write(reason_text)
        else:
            st.write("No query rewrite changes were required.")

    with st.expander("How is Expected Impact calculated?"):
        st.write(
            "Dr.DB estimates impact using detected SQL anti-patterns and index opportunities."
        )
        st.write(f"**Impact Score:** {impact_score}")
        st.markdown(
            "High-severity issue: +3 · Medium: +2 · Low: +1 · Recommended index: +2 each (capped at +4)."
        )
        st.caption("0–2 = Low · 3–5 = Medium · 6+ = High. This is a heuristic, not an execution-time benchmark.")

    # ====================================================
    # ISSUES
    # ====================================================

    st.subheader("What's Slow?")
    if issues:
        for issue in issues:
            severity = issue.get("severity", "LOW").upper()
            icon = "🔴" if severity == "HIGH" else "🟠" if severity == "MEDIUM" else "🟡"
            issue_title = md_escape(issue.get("issue", "Issue"))
            issue_explanation = md_escape(issue.get("explanation", ""))
            with st.container(border=True):
                st.markdown(f"**{icon} {issue_title}** · {severity}")
                st.write(issue_explanation)
    else:
        st.success("No major static SQL issues detected.")

    # ====================================================
    # INDEXES
    # ====================================================

    if recommended_indexes:
        st.subheader("Recommended Indexes")
        for index in recommended_indexes:
            with st.container(border=True):
                st.code(index.get("sql", ""), language="sql")
                if index.get("reason"):
                    st.write(md_escape(index["reason"]))
                if index.get("tradeoff"):
                    st.caption("Trade-off: " + md_escape(index["tradeoff"]))

    st.caption(
        "Dr.DB estimates optimization impact using static SQL analysis, detected anti-patterns, index opportunities, and AI-assisted optimization. Actual performance depends on data distribution, indexes, hardware, caching, and PostgreSQL's execution plan."
    )


def render_empty_state():
    st.markdown(
        """
        <div class="drdb-empty">
            <div class="drdb-empty-icon">🔬</div>
            <div class="drdb-empty-title">Your results will show up here</div>
            <div class="drdb-empty-sub">
                Paste a query above (or load one of the examples) and hit <strong>Analyze &amp; Optimize</strong>.
                You'll get a health score, the specific issues Dr.DB found, a rewritten query, and any
                indexes worth adding — all validated before you see them.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# ABOUT PAGE
# ============================================================

if page == "About":
    st.markdown(
        """
        <div class="drdb-banner">
            <div class="drdb-banner-title">About Dr.DB</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Why Dr.DB exists")
    st.write(
        "Most query performance problems are boring and repetitive, a correlated subquery that "
        "should be a JOIN, a `LIKE '%value'` that can't use an index, a function wrapped around a "
        "filtered column. Catching these usually means knowing what performance patterns to look for "
        "and manually reviewing query structure. Dr.DB automates the first pass: it runs deterministic checks "
        "against the query's structure, asks an AI model to propose a fix with reasoning, and then re-validates "
        "that fix before ever showing it to you, so you get a second pair of eyes without waiting on one."
    )

    st.subheader("How it's different from just asking a chatbot?")
    st.markdown(
        """
        <div class="drdb-feature-grid">
            <div class="drdb-feature-card">
                <div class="drdb-feature-icon">✅</div>
                <div class="drdb-feature-title">Deterministic first</div>
                <div class="drdb-feature-desc">Anti-patterns are detected with rule-based static analysis on the parsed query tree, not a model's guess, so the same query always flags the same issues.</div>
            </div>
            <div class="drdb-feature-card">
                <div class="drdb-feature-icon">✅</div>
                <div class="drdb-feature-title">AI-assisted rewrites</div>
                <div class="drdb-feature-desc">Once issues are known, the model proposes a rewrite and indexes grounded in your actual schema, with a plain-language reason for every change.</div>
            </div>
            <div class="drdb-feature-card">
                <div class="drdb-feature-icon">✅</div>
                <div class="drdb-feature-title">Validated before you see it</div>
                <div class="drdb-feature-desc">Every optimized query is re-parsed for syntax and checked against your schema's table names before it's ever shown. So that, bad suggestions get caught, not shipped.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Who it's for?")
    st.write(
        "Developers doing a quick self-review before a PR, students learning what actually makes a "
        "query slow, and anyone who wants a sanity check on a query without spinning up a full "
        "profiling setup."
    )

    st.subheader("What it doesn't claim?")
    st.markdown(
        """
        <div class="drdb-callout">
            <strong>Expected Impact is a heuristic classification, not a benchmark.</strong> It's derived from
            issue severity and index opportunities, not a measured execution time. Dr.DB never runs your query —
            it never connects to a live database — so it can't see your actual data distribution, existing
            indexes, hardware, or caching behavior. All of those affect real-world performance, and none of
            them are visible from a query and (optionally) a schema alone.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption("Built with SQLGlot for parsing, Groq for the AI optimization step, and Streamlit for the interface.")
    st.stop()


# ============================================================
# HOW IT WORKS PAGE
# ============================================================

if page == "How Dr.DB works":
    st.markdown(
        """
        <div class="drdb-banner">
            <div class="drdb-banner-title">How Dr.DB works</div>
            <p class="drdb-banner-subtitle">
                Five steps, each one narrowing the room for error before anything reaches your screen.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="drdb-steps">
            <div class="drdb-step">
                <div class="drdb-step-num">1</div>
                <div class="drdb-step-body">
                    <div class="drdb-step-title">Parse</div>
                    <div class="drdb-step-desc">SQLGlot parses your PostgreSQL query into a structured syntax tree. If the query doesn't parse, Dr.DB stops here and tells you exactly why — no guessing at what you "probably" meant.</div>
                </div>
            </div>
            <div class="drdb-step">
                <div class="drdb-step-num">2</div>
                <div class="drdb-step-body">
                    <div class="drdb-step-title">Diagnose</div>
                    <div class="drdb-step-desc">Rule-based checks walk the syntax tree looking for known performance anti-patterns (correlated subqueries, leading wildcards, functions wrapped around filtered columns, and more) each tagged with a severity.</div>
                </div>
            </div>
            <div class="drdb-step">
                <div class="drdb-step-num">3</div>
                <div class="drdb-step-body">
                    <div class="drdb-step-title">Optimize</div>
                    <div class="drdb-step-desc">The detected issues, your original query, and any schema you provided are sent to the AI optimizer, which proposes a rewritten query, candidate indexes, and a plain-language reason for each change.</div>
                </div>
            </div>
            <div class="drdb-step">
                <div class="drdb-step-num">4</div>
                <div class="drdb-step-body">
                    <div class="drdb-step-title">Validate</div>
                    <div class="drdb-step-desc">The optimized SQL is parsed again to confirm it's syntactically valid, and every table it references is checked against your supplied schema. If either check fails, Dr.DB rejects the suggestion rather than showing you something broken.</div>
                </div>
            </div>
            <div class="drdb-step">
                <div class="drdb-step-num">5</div>
                <div class="drdb-step-body">
                    <div class="drdb-step-title">Estimate impact</div>
                    <div class="drdb-step-desc">A deterministic heuristic — issue severity plus index opportunities, each with a fixed weight — classifies the expected impact as Low, Medium, or High, so you know where to focus first.</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="drdb-callout">
            Steps 1, 2, 4, and 5 are fully deterministic — the same query produces the same result every time.
            Only step 3 involves the AI model, and its output never reaches you without passing back through
            validation in step 4.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


# ============================================================
# HOME — HERO
# ============================================================

st.markdown(
    """
    <div class="drdb-banner">
        <div class="drdb-eyebrow">AI-powered PostgreSQL query optimizer</div>
        <div class="drdb-banner-title">🩺 Dr.DB</div>
        <p class="drdb-banner-subtitle">Find what's slow. Understand why. Fix it before you ship.</p>
        <div class="drdb-chip-row">
            <span class="drdb-chip">✅ Deterministic checks</span>
            <span class="drdb-chip">✅ AI-assisted rewrites</span>
            <span class="drdb-chip">✅ Validated output</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# QUERY BUILDER CARD
# One bordered card holds the whole input flow — mode toggle,
# query + context, and the analyze action — so it reads as a
# single step instead of three loose floating sections.
# ============================================================

with st.container(border=True):
    st.markdown("##### Build your query")

    mode_col1, mode_col2 = st.columns(2)

    with mode_col1:
        st.button(
            "Write my own query",
            use_container_width=True,
            type="primary" if st.session_state.input_mode == "write" else "secondary",
            on_click=choose_write_mode,
        )

    with mode_col2:
        st.button(
            "Use an existing example",
            use_container_width=True,
            type="primary" if st.session_state.input_mode == "example" else "secondary",
            on_click=choose_example_mode,
        )

    if st.session_state.input_mode == "example":
        st.selectbox(
            "Choose an example",
            options=list(EXAMPLES.keys()),
            key="selected_example",
            on_change=load_selected_example,
            label_visibility="collapsed",
        )

    query_col, context_col = st.columns([2.15, 1], gap="medium")

    with query_col:
        st.caption("SQL QUERY")
        sql_query = st.text_area(
            "SQL Query",
            key="sql_input",
            height=150,
            placeholder="Paste your PostgreSQL query here...",
            label_visibility="collapsed",
        )

    with context_col:
        st.caption("DATABASE SCHEMA · OPTIONAL")
        schema = st.text_area(
            "Database Schema (Optional)",
            key="schema_input",
            height=150,
            placeholder="Optional: paste CREATE TABLE statements for better grounding...",
            label_visibility="collapsed",
        )

    analyze = st.button(
        "Analyze & Optimize",
        type="primary",
        use_container_width=True,
    )


# ============================================================
# ANALYSIS PIPELINE
# ============================================================

if analyze:
    if not sql_query.strip():
        st.warning("Enter a SQL query first.")
    else:
        st.session_state.result = None

        parsed = parse_query(sql_query)

        if not parsed["valid"]:
            st.error("Invalid PostgreSQL query")
            st.write("Dr.DB could not parse the query.")
            with st.expander("View parsing error"):
                st.code(parsed.get("error", "Unknown parsing error."))
            st.stop()

        tree = parsed["tree"]
        issues = analyze_query(tree)
        health_score = calculate_health_score(issues)

        try:
            with st.spinner("Analyzing and optimizing your query..."):
                optimization = optimize_query(
                    query=sql_query,
                    issues=issues,
                    schema=schema if schema.strip() else None,
                    explain=None,
                )
        except Exception as error:
            render_api_error(error)
            st.stop()

        if not optimization.get("success"):
            raw = optimization.get("raw", "No response received.")
            raw_lower = str(raw).lower()
            if any(term in raw_lower for term in ["token", "context length", "context_length", "too large"]):
                st.error("This request is too large for the AI optimizer. Shorten the SQL or schema and try again.")
            else:
                st.error("The AI optimizer returned an invalid response. Please try again.")
            with st.expander("View raw AI response"):
                st.code(raw)
            st.stop()

        data = optimization["data"]
        recommended_indexes = data.get("recommended_indexes", [])
        impact_result = calculate_impact_score(issues, recommended_indexes)
        expected_impact = impact_result["impact"]
        impact_score = impact_result["score"]
        optimized_query = data.get("optimized_query", "")

        validation = validate_optimized_query(optimized_query)
        schema_tables = extract_schema(schema)
        table_validation = validate_tables(optimized_query, schema_tables)

        if not validation["valid"]:
            st.error("Dr.DB generated an optimized query that failed SQL syntax validation.")
            with st.expander("View validation error"):
                st.code(validation.get("error", "Unknown validation error."))
            st.stop()

        if not table_validation["valid"]:
            st.error(
                "Dr.DB rejected the optimized query because it references tables that are not present in the provided schema."
            )
            unknown_tables = table_validation.get("unknown_tables", [])
            if unknown_tables:
                st.write("**Unknown tables:** " + ", ".join(f"`{table}`" for table in unknown_tables))
            st.stop()

        st.session_state.result = {
            "sql_query": sql_query,
            "schema": schema,
            "optimized_query": optimized_query,
            "issues": issues,
            "health_score": health_score,
            "expected_impact": expected_impact,
            "impact_score": impact_score,
            "recommended_indexes": recommended_indexes,
            "changes": data.get("changes", []),
        }


# ============================================================
# RESULTS — persisted, so they stay visible across reruns
# ============================================================

if st.session_state.result:
    render_results(st.session_state.result)
elif not analyze:
    render_empty_state()