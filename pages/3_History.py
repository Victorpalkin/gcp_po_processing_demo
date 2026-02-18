"""Processing History — browse past extractions from BigQuery."""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from auth import require_auth
from styles import apply_styles, render_header, status_badge
from services import bigquery

st.set_page_config(page_title="History", page_icon="📋", layout="wide")
apply_styles()
require_auth()
render_header("Processing History", "Browse and filter past extraction results")

# --- Filters ---
col_status, col_days, col_search = st.columns(3)

with col_status:
    status_filter = st.selectbox(
        "Status",
        options=["All", "EXTRACTED", "REVIEWED", "SENT", "PROCESSING", "ERROR"],
        index=0,
    )

with col_days:
    days_filter = st.selectbox(
        "Time period",
        options=[
            ("All time", None),
            ("Last 7 days", 7),
            ("Last 30 days", 30),
            ("Last 90 days", 90),
        ],
        format_func=lambda x: x[0],
        index=0,
    )

with col_search:
    filename_search = st.text_input("Search filename", placeholder="e.g. invoice")

# --- Query ---
filter_status = status_filter if status_filter != "All" else None
filter_days = days_filter[1] if days_filter[1] else None
filter_filename = filename_search.strip() if filename_search.strip() else None

# Pagination
page_size = 10
if "history_page" not in st.session_state:
    st.session_state["history_page"] = 0

try:
    total_count = bigquery.get_extraction_count(
        status=filter_status,
        days=filter_days,
        filename_search=filter_filename,
    )
    extractions = bigquery.get_extractions(
        status=filter_status,
        days=filter_days,
        filename_search=filter_filename,
        limit=page_size,
        offset=st.session_state["history_page"] * page_size,
    )
except Exception as e:
    total_count = 0
    extractions = []
    st.error(f"Failed to load history: {e}")

st.divider()

# --- Results table ---
if extractions:
    # Table header
    header_cols = st.columns([3, 2, 1, 1, 2])
    header_cols[0].markdown("**File**")
    header_cols[1].markdown("**Processor**")
    header_cols[2].markdown("**Status**")
    header_cols[3].markdown("**Confidence**")
    header_cols[4].markdown("**Date**")

    for record in extractions:
        cols = st.columns([3, 2, 1, 1, 2])

        cols[0].write(record["filename"])
        cols[1].write(record.get("processor_display_name", "—"))
        cols[2].markdown(
            status_badge(record.get("status", "UNKNOWN")),
            unsafe_allow_html=True,
        )

        confidence = record.get("confidence", 0)
        cols[3].write(f"{confidence:.0%}" if confidence else "—")

        created = record.get("created_at")
        if created and hasattr(created, "strftime"):
            cols[4].write(created.strftime("%b %d, %Y %H:%M"))
        else:
            cols[4].write(str(created) if created else "—")

    # Pagination controls
    st.divider()
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    current_page = st.session_state["history_page"]

    start = current_page * page_size + 1
    end = min((current_page + 1) * page_size, total_count)
    st.caption(f"Showing {start}-{end} of {total_count}")

    page_col1, page_col2, page_col3 = st.columns([1, 2, 1])

    with page_col1:
        if st.button("← Previous", disabled=current_page == 0):
            st.session_state["history_page"] -= 1
            st.rerun()

    with page_col3:
        if st.button("Next →", disabled=current_page >= total_pages - 1):
            st.session_state["history_page"] += 1
            st.rerun()

    # Row click to review
    st.divider()
    st.subheader("View Details")

    view_options = {r["filename"]: r["id"] for r in extractions}
    selected_file = st.selectbox(
        "Select a record to review",
        options=list(view_options.keys()),
        label_visibility="collapsed",
    )

    if st.button("Open in Review"):
        st.session_state["review_record_id"] = view_options[selected_file]
        st.session_state["review_result"] = None  # Will load from BQ
        st.switch_page("pages/2_Review.py")

else:
    st.info("No records found matching your filters.")
