"""Simple password-based authentication for the app."""

import os

import streamlit as st


def require_auth():
    """Show a login form and block the page if not authenticated.

    Reads the expected password from the APP_PASSWORD env var.
    Call this at the top of every page, after st.set_page_config().
    """
    password = os.getenv("APP_PASSWORD")
    if not password:
        st.error("APP_PASSWORD environment variable is not set.")
        st.stop()

    if st.session_state.get("authenticated"):
        _render_logout_button()
        return

    st.markdown(
        "<h2 style='text-align:center; margin-top:2rem;'>Login</h2>",
        unsafe_allow_html=True,
    )

    with st.form("login_form"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", use_container_width=True)

    if submitted:
        if entered == password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()


def _render_logout_button():
    """Add a logout button to the sidebar."""
    with st.sidebar:
        if st.button("Log out", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()
