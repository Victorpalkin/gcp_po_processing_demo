"""Review & Send — edit extracted fields and send."""

from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from styles import apply_styles, render_header, confidence_html
from services import bigquery, document_ai, sap, storage

st.set_page_config(page_title="Review Extraction", page_icon="📋", layout="wide")
apply_styles()
render_header("Review Extraction", "Edit extracted values and send when ready")

# --- Load results ---
results = st.session_state.get("results", [])
review_result = st.session_state.get("review_result")

# Also allow loading from BigQuery by record ID
review_record_id = st.session_state.get("review_record_id")

if review_record_id and not review_result:
    try:
        review_result = bigquery.get_extraction(review_record_id)
        if review_result:
            st.session_state["review_result"] = review_result
    except Exception as e:
        st.error(f"Failed to load extraction: {e}")

# Build selectable list from session results
if not results and not review_result:
    st.info("No extraction results to review. Process some documents first.")
    if st.button("Go to Process"):
        st.switch_page("pages/1_Process.py")
    st.stop()

# --- Document selector ---
valid_results = [r for r in results if r.get("status") != "ERROR"] if results else []

if valid_results:
    st.subheader("Select Document")
    doc_options = {
        f"{r['filename']} ({r.get('confidence', 0):.0%} confidence)": i
        for i, r in enumerate(valid_results)
    }
    selected_label = st.selectbox(
        "Document",
        options=list(doc_options.keys()),
        label_visibility="collapsed",
    )
    review_result = valid_results[doc_options[selected_label]]
    st.session_state["review_result"] = review_result

if not review_result:
    st.warning("No document selected for review.")
    st.stop()

# --- Document viewer toggle ---
gcs_uri = review_result.get("gcs_uri", "")
filename = review_result.get("filename", "")

show_viewer = st.toggle("Show document", key="show_document_viewer")

# Widen layout when viewer is active
if show_viewer:
    st.markdown(
        "<style>.block-container { max-width: 1800px !important; }</style>",
        unsafe_allow_html=True,
    )

# --- Conditional layout: side-by-side or single column ---
if show_viewer and gcs_uri:
    doc_col, editor_col = st.columns([1, 1])
    with doc_col:
        st.subheader("Original Document")
        try:
            mime_type = document_ai.get_mime_type(filename)
            if mime_type == "application/pdf":
                signed_url = storage.get_signed_url(gcs_uri)
                st.markdown(
                    f'<iframe src="{signed_url}" width="100%" height="800" '
                    f'style="border: 1px solid #e0e0e0; border-radius: 8px;">'
                    f"</iframe>",
                    unsafe_allow_html=True,
                )
            else:
                image_bytes = storage.download_file(gcs_uri)
                st.image(image_bytes, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load document: {e}")
    container = editor_col
else:
    container = st.container()

with container:
    # --- Extract fields for editing ---
    fields = review_result.get("extracted_data", {})
    reviewed = review_result.get("reviewed_data")

    # Use reviewed data if available, otherwise extracted data
    edit_source = reviewed if reviewed else fields

    # Separate flat fields from nested/list fields (line items)
    flat_fields = {}
    line_item_fields = {}

    for name, data in edit_source.items():
        if isinstance(data, list):
            line_item_fields[name] = data
        elif isinstance(data, dict) and "properties" in data:
            line_item_fields[name] = data
        else:
            flat_fields[name] = data

    # --- Flat fields editor ---
    st.subheader("Extracted Fields")

    if flat_fields:
        field_rows = []
        for name, data in flat_fields.items():
            if isinstance(data, dict):
                field_rows.append({
                    "Field": name,
                    "Value": data.get("value", ""),
                    "Confidence": f"{data.get('confidence', 0):.0%}",
                })
            else:
                field_rows.append({
                    "Field": name,
                    "Value": str(data),
                    "Confidence": "—",
                })

        df = pd.DataFrame(field_rows)

        edited_df = st.data_editor(
            df,
            column_config={
                "Field": st.column_config.TextColumn("Field", disabled=True),
                "Value": st.column_config.TextColumn("Value"),
                "Confidence": st.column_config.TextColumn("Confidence", disabled=True),
            },
            hide_index=True,
            use_container_width=True,
            key="flat_fields_editor",
        )
    else:
        edited_df = None
        st.info("No flat fields extracted.")

    # --- Helpers for nested property flatten/unflatten ---

    def _flatten_properties(properties, prefix=""):
        """Flatten nested properties into {path: value} dict."""
        flat = {}
        for prop in properties:
            key = prop["name"] if not prefix else f"{prefix}/{prop['name']}"
            flat[key] = prop.get("value", "")
            if prop.get("properties"):
                flat.update(_flatten_properties(prop["properties"], prefix=key))
        return flat


    def _unflatten_to_properties(flat_row):
        """Convert {path: value} back to nested properties list."""
        root = {}
        for path, value in flat_row.items():
            parts = path.split("/")
            node = root
            for part in parts[:-1]:
                if part not in node:
                    node[part] = {"value": "", "children": {}}
                node = node[part]["children"]
            leaf = parts[-1]
            if leaf in node:
                node[leaf]["value"] = value
            else:
                node[leaf] = {"value": value, "children": {}}

        def _build(tree):
            result = []
            for name, data in tree.items():
                entry = {"name": name, "value": data.get("value", "")}
                children = data.get("children", {})
                if children:
                    entry["properties"] = _build(children)
                result.append(entry)
            return result

        return _build(root)


    # --- Line items editor ---
    edited_line_items = {}

    if line_item_fields:
        st.subheader("Line Items")

        for group_name, items in line_item_fields.items():
            st.write(f"**{group_name}**")

            items_list = items if isinstance(items, list) else [items]

            item_rows = []
            for item in items_list:
                if isinstance(item, dict):
                    if "properties" in item:
                        item_rows.append(_flatten_properties(item["properties"]))
                    else:
                        item_rows.append({"value": item.get("value", "")})

            if item_rows:
                items_df = pd.DataFrame(item_rows).fillna("")
                edited_items_df = st.data_editor(
                    items_df,
                    num_rows="dynamic",
                    use_container_width=True,
                    key=f"line_items_{group_name}",
                )
                edited_rows = []
                for _, row in edited_items_df.iterrows():
                    row_dict = row.to_dict()
                    has_nested = any("/" in k for k in row_dict)
                    if has_nested or len(row_dict) > 1 or "value" not in row_dict:
                        edited_rows.append({
                            "properties": _unflatten_to_properties(row_dict),
                        })
                    else:
                        edited_rows.append({"value": row_dict.get("value", "")})
                edited_line_items[group_name] = edited_rows

    # --- Action buttons ---
    st.divider()

    col_back, _, col_send = st.columns([1, 2, 1])

    with col_back:
        if st.button("Back", use_container_width=True):
            st.switch_page("pages/1_Process.py")

    with col_send:
        if st.button("Send", type="primary", use_container_width=True):
            # Build reviewed data from edited fields
            reviewed_data = {}

            if edited_df is not None:
                for _, row in edited_df.iterrows():
                    reviewed_data[row["Field"]] = {
                        "value": row["Value"],
                        "edited": True,
                    }

            # Add line items
            for group_name, items in edited_line_items.items():
                reviewed_data[group_name] = items

            # Send to SAP (mock by default — see services/sap.py)
            filename = review_result.get("filename", "unknown")
            try:
                sap_result = sap.send_purchase_order(reviewed_data, filename)
            except Exception as e:
                st.error(f"Failed to send to SAP: {e}")
                st.stop()

            record_id = review_result.get("id")
            if record_id:
                try:
                    now = datetime.utcnow().isoformat()
                    bigquery.update_extraction(record_id, {
                        "reviewed_data": reviewed_data,
                        "status": "SENT",
                        "reviewed_at": now,
                        "sent_at": now,
                    })
                    doc_num = sap_result["document_number"]
                    st.success(
                        f"PO sent successfully! SAP document: {doc_num}"
                    )
                    st.toast("PO sent!", icon="✅")

                    # Update session state
                    review_result["status"] = "SENT"
                    review_result["reviewed_data"] = reviewed_data

                except Exception as e:
                    st.error(f"Failed to update record: {e}")
            else:
                doc_num = sap_result["document_number"]
                st.success(f"PO sent (SAP document: {doc_num}).")
                st.json(reviewed_data)
