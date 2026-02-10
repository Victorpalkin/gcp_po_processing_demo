"""PO Processing — Home / Dashboard."""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from styles import apply_styles, render_header, status_badge
from services import bigquery

st.set_page_config(
    page_title="PO Processing",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_styles()
render_header("PO Processing", "Purchase Order extraction powered by Document AI")

# --- Stats ---
try:
    stats = bigquery.get_stats()
except Exception as e:
    stats = {"total": 0, "sent": 0, "pending": 0, "processing": 0}
    st.warning(f"Could not load stats: {e}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Processed", stats["total"])
col2.metric("Sent", stats["sent"])
col3.metric("Pending Review", stats["pending"])
col4.metric("Processing", stats["processing"])

st.divider()

# --- Recent Activity ---
st.subheader("Recent Activity")

try:
    recent = bigquery.get_extractions(limit=10)
except Exception as e:
    recent = []
    st.warning(f"Could not load recent activity: {e}")

if recent:
    for record in recent:
        cols = st.columns([3, 2, 1, 2])
        cols[0].write(record["filename"])
        cols[1].write(record.get("processor_display_name", "—"))
        cols[2].markdown(
            status_badge(record.get("status", "UNKNOWN")),
            unsafe_allow_html=True,
        )
        created = record.get("created_at")
        if created:
            cols[3].write(created.strftime("%b %d, %Y %H:%M") if hasattr(created, "strftime") else str(created))
        else:
            cols[3].write("—")
else:
    st.info("No processing history yet. Upload your first PO to get started.")

st.divider()

# --- Navigation ---
col_left, col_right, _ = st.columns([1, 1, 2])

with col_left:
    if st.button("Process New POs", type="primary", use_container_width=True):
        st.switch_page("pages/1_Process.py")

with col_right:
    if st.button("Manage Processors", use_container_width=True):
        st.switch_page("pages/4_Admin.py")
