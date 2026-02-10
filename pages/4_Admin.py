"""Admin — Manage processors and schemas."""

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from styles import apply_styles, render_header, status_badge
from services import document_ai

st.set_page_config(page_title="Admin", page_icon="📋", layout="wide")
apply_styles()
render_header("Manage Processors", "View and manage Document AI processors")

# --- List existing processors ---
st.subheader("Existing Processors")

try:
    processors = document_ai.list_processors()
except Exception as e:
    processors = []
    st.error(f"Failed to list processors: {e}")

if processors:
    for proc in processors:
        proc_name = proc["name"]
        display_name = proc["display_name"]
        state = proc.get("state", "UNKNOWN")
        create_time = proc.get("create_time")

        # Fetch schema to show field count
        try:
            proc_detail = document_ai.get_processor_with_schema(proc_name)
            field_count = len(proc_detail.get("fields", []))
        except Exception:
            field_count = 0

        # Card layout
        with st.container():
            col_info, col_actions = st.columns([3, 1])

            with col_info:
                st.markdown(
                    f"""
                    <div class="card">
                        <h3>{display_name} {status_badge(state)}</h3>
                        <div class="card-subtitle">
                            {field_count} field(s)
                            {'· Created ' + create_time.strftime('%b %d, %Y') if create_time and hasattr(create_time, 'strftime') else ''}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col_actions:
                # View schema button
                if st.button("View Schema", key=f"schema_{proc_name}"):
                    st.session_state[f"show_schema_{proc_name}"] = not st.session_state.get(
                        f"show_schema_{proc_name}", False
                    )

                # Delete button with confirmation
                if st.button("Delete", key=f"delete_{proc_name}", type="secondary"):
                    st.session_state[f"confirm_delete_{proc_name}"] = True

        # Show schema details
        if st.session_state.get(f"show_schema_{proc_name}"):
            try:
                detail = document_ai.get_processor_with_schema(proc_name)
                fields = detail.get("fields", [])
                if fields:
                    schema_df = pd.DataFrame(fields)
                    st.dataframe(schema_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No schema fields defined for this processor.")
            except Exception as e:
                st.error(f"Failed to load schema: {e}")

        # Delete confirmation
        if st.session_state.get(f"confirm_delete_{proc_name}"):
            st.warning(f"Are you sure you want to delete **{display_name}**?")
            col_yes, col_no, _ = st.columns([1, 1, 4])
            with col_yes:
                if st.button("Yes, delete", key=f"confirm_yes_{proc_name}", type="primary"):
                    try:
                        with st.spinner(f"Deleting {display_name}..."):
                            document_ai.delete_processor(proc_name)
                        st.success(f"Deleted {display_name}")
                        st.session_state.pop(f"confirm_delete_{proc_name}", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete: {e}")
            with col_no:
                if st.button("Cancel", key=f"confirm_no_{proc_name}"):
                    st.session_state.pop(f"confirm_delete_{proc_name}", None)
                    st.rerun()

else:
    st.info("No processors found. Create processors via the Google Cloud Console.")
