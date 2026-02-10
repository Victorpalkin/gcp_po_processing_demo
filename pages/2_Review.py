"""Review & Send — edit extracted fields and send."""

import json
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from styles import apply_styles, render_header, confidence_html
from services import bigquery

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

# --- Line items editor ---
if line_item_fields:
    st.subheader("Line Items")

    for group_name, items in line_item_fields.items():
        st.write(f"**{group_name}**")

        if isinstance(items, list):
            # Build a DataFrame from line item properties
            item_rows = []
            for item in items:
                if isinstance(item, dict):
                    if "properties" in item:
                        row = {}
                        for prop in item["properties"]:
                            row[prop["name"]] = prop.get("value", "")
                        item_rows.append(row)
                    else:
                        item_rows.append({"Value": item.get("value", "")})

            if item_rows:
                items_df = pd.DataFrame(item_rows)
                edited_items = st.data_editor(
                    items_df,
                    num_rows="dynamic",
                    use_container_width=True,
                    key=f"line_items_{group_name}",
                )
                line_item_fields[group_name] = edited_items.to_dict("records")
        elif isinstance(items, dict) and "properties" in items:
            props = items["properties"]
            row = {p["name"]: p.get("value", "") for p in props}
            items_df = pd.DataFrame([row])
            edited_items = st.data_editor(
                items_df,
                num_rows="dynamic",
                use_container_width=True,
                key=f"line_items_{group_name}",
            )
            line_item_fields[group_name] = edited_items.to_dict("records")

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
        for group_name, items in line_item_fields.items():
            reviewed_data[group_name] = items

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
                st.success("PO sent successfully!")
                st.toast("PO sent!", icon="✅")

                # Update session state
                review_result["status"] = "SENT"
                review_result["reviewed_data"] = reviewed_data

            except Exception as e:
                st.error(f"Failed to send: {e}")
        else:
            # No BigQuery record (shouldn't happen in normal flow)
            st.success("PO reviewed and sent (mock).")
            st.json(reviewed_data)
