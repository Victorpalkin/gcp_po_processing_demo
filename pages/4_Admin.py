"""Admin — Manage processors and schemas."""

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from styles import apply_styles, render_header, status_badge
from services import document_ai

st.set_page_config(page_title="Admin", page_icon="📋", layout="wide")
apply_styles()
render_header("Manage Processors", "Create, configure, and manage Document AI processors")

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
    st.info("No processors found. Create one below.")

st.divider()

# --- Create new processor ---
st.subheader("Create New Processor")

with st.form("create_processor_form"):
    proc_display_name = st.text_input("Name", placeholder="e.g. PO Extractor v1")
    proc_description = st.text_area(
        "Description",
        placeholder="e.g. Extracts purchase order fields from scanned documents",
    )

    st.write("**Extraction Fields**")
    st.caption("Define the fields to extract from documents. Add descriptive descriptions for best zero-shot accuracy.")

    # Default schema template
    default_fields = pd.DataFrame([
        {
            "field_name": "vendor_name",
            "display_name": "Vendor Name",
            "description": "The name of the vendor or supplier on the purchase order",
            "type": "Extract",
            "required": True,
        },
        {
            "field_name": "po_number",
            "display_name": "PO Number",
            "description": "The unique purchase order number or identifier",
            "type": "Extract",
            "required": True,
        },
        {
            "field_name": "total_amount",
            "display_name": "Total Amount",
            "description": "The total monetary amount of the purchase order",
            "type": "Extract",
            "required": True,
        },
    ])

    fields_df = st.data_editor(
        default_fields,
        column_config={
            "field_name": st.column_config.TextColumn(
                "Field Name", help="Internal field name (snake_case)"
            ),
            "display_name": st.column_config.TextColumn(
                "Display Name", help="Human-readable field name"
            ),
            "description": st.column_config.TextColumn(
                "Description",
                help="Detailed description for Document AI (improves accuracy)",
                width="large",
            ),
            "type": st.column_config.SelectboxColumn(
                "Type",
                options=["Extract", "Derive"],
                help="Extract = from document text, Derive = computed/inferred",
            ),
            "required": st.column_config.CheckboxColumn(
                "Required", help="Whether this field is required"
            ),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
    )

    submitted = st.form_submit_button("Create Processor", type="primary")

if submitted:
    if not proc_display_name.strip():
        st.error("Processor name is required.")
    elif fields_df.empty:
        st.error("At least one extraction field is required.")
    else:
        # Convert DataFrame to field list
        fields_list = []
        for _, row in fields_df.iterrows():
            if not row.get("field_name"):
                continue
            fields_list.append({
                "name": row["field_name"],
                "display_name": row.get("display_name", row["field_name"]),
                "description": row.get("description", ""),
                "required": bool(row.get("required", False)),
                "value_type": "string",
            })

        if not fields_list:
            st.error("At least one field with a name is required.")
        else:
            try:
                with st.status("Creating processor...", expanded=True) as status:
                    st.write("Creating processor in Document AI...")
                    st.write("Configuring schema and training zero-shot model...")
                    st.write("This may take a few minutes for version training and deployment...")

                    processor_name = document_ai.create_processor(
                        display_name=proc_display_name.strip(),
                        description=proc_description.strip(),
                        fields=fields_list,
                    )

                    status.update(label="Processor created!", state="complete")

                st.success(f"Processor **{proc_display_name}** created successfully.")
                st.toast("Processor created!", icon="✅")
                st.rerun()

            except Exception as e:
                st.error(f"Failed to create processor: {e}")
