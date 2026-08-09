import streamlit as st

TOKENS = {
    "space": 8, "content_max": 1360, "radius": 8,
    "complete": "#237A45", "running": "#1F5A94", "awaiting": "#9A6700",
    "blocked": "#B42318", "stale": "#6B4FA3", "pending": "#667085",
}


def apply_design_tokens():
    st.html(
        f"""<style>
        .stMainBlockContainer {{max-width:{TOKENS['content_max']}px; padding-top:1.5rem;}}
        [data-testid="stDataFrame"] {{font-variant-numeric: tabular-nums;}}
        [data-testid="stMarkdownContainer"] p {{line-height:1.55;}}
        code {{overflow-wrap:anywhere;}}
        @media (max-width: 800px) {{
          .stMainBlockContainer {{padding-left:1rem; padding-right:1rem;}}
          [data-testid="stHorizontalBlock"] {{flex-wrap:wrap;}}
        }}
        </style>"""
    )

