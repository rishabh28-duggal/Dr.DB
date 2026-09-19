import json
import os
import streamlit as st
from groq import Groq


def get_groq_client():
    """
    Load the Groq API key securely.

    Priority:
    1. Streamlit secrets
    2. Environment variable
    """

    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except Exception:
        api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise ValueError(
            "GROQ_API_KEY was not found. "
            "Add it to Streamlit secrets or your environment variables."
        )

    return Groq(api_key=api_key)


def optimize_query(query, issues, schema=None, explain=None):

    client = get_groq_client()

    issue_text = json.dumps(issues, indent=2)

    prompt = f"""
You are Dr.DB, an AI SQL optimization assistant.

Your task is to analyze a PostgreSQL query and suggest a safer, more efficient version.

ORIGINAL QUERY:
{query}

DETECTED ISSUES:
{issue_text}

OPTIONAL SCHEMA:
{schema if schema else "Not provided"}

OPTIONAL EXPLAIN:
{explain if explain else "Not provided"}

Rules:
1. Do not invent tables or columns.
2. Preserve the intent of the original query.
3. Only recommend indexes when structurally justified.
4. Do not claim exact runtime improvement.
5. Return ONLY valid JSON.
6. expected_impact must be one of: LOW, MEDIUM, HIGH.
7. confidence must be one of: LOW, MEDIUM, HIGH.
8. Never change filtering semantics purely for performance.
   For example, do not change LIKE '%text' to LIKE 'text%'
   because these queries return different results.
9. An optimization must preserve the intended result of the original query.
10. If a detected issue cannot be safely optimized without changing
    query semantics, explain the limitation instead of forcing a rewrite.

Return JSON in this format:

{{
    "optimized_query": "...",
    "recommended_indexes": [
        {{
            "sql": "...",
            "reason": "...",
            "tradeoff": "..."
        }}
    ],
    "changes": [
        {{
            "change": "...",
            "reason": "..."
        }}
    ],
    "expected_impact": "LOW",
    "confidence": "LOW"
}}
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2
    )

    raw_output = response.choices[0].message.content

    try:
        return {
            "success": True,
            "data": json.loads(raw_output),
            "raw": raw_output
        }

    except json.JSONDecodeError:
        return {
            "success": False,
            "data": None,
            "raw": raw_output
        }