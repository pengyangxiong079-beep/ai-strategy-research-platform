from __future__ import annotations

import json
from pathlib import Path
import streamlit as st


@st.cache_data(ttl="30s", max_entries=128, show_spinner=False)
def read_json_cached(path_text, modified_ns):
    del modified_ns
    return json.loads(Path(path_text).read_text(encoding="utf-8"))


@st.cache_data(ttl="30s", max_entries=128, show_spinner=False)
def read_text_cached(path_text, modified_ns):
    del modified_ns
    return Path(path_text).read_text(encoding="utf-8")


def read_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default if default is not None else {}
    try:
        return read_json_cached(str(path.resolve()), path.stat().st_mtime_ns)
    except (OSError, ValueError, TypeError):
        return default if default is not None else {}


def read_text(path, default=""):
    path = Path(path)
    if not path.is_file():
        return default
    try:
        return read_text_cached(str(path.resolve()), path.stat().st_mtime_ns)
    except OSError:
        return default


def invalidate_file_cache():
    read_json_cached.clear()
    read_text_cached.clear()

