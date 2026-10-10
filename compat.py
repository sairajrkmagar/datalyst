"""
STREAMLIT CHANGES NAMES OVER TIME. This file is the one place that copes with it.

Newer Streamlit replaces `use_container_width=True` with `width="stretch"` and plans to remove
the old name. `STRETCH` holds whichever the installed version understands:

    st.button("Go", **STRETCH)
"""

import inspect

import streamlit as st


def new_width_api():
    """True when this Streamlit understands width="stretch" (it has a `width` option on buttons)."""
    try:
        return "width" in inspect.signature(st.button).parameters
    except (TypeError, ValueError):
        return False


STRETCH = {"width": "stretch"} if new_width_api() else {"use_container_width": True}
