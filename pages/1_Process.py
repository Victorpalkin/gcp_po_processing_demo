"""Process Purchase Orders — upload, extract, view results."""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from styles import apply_styles, render_header, confidence_html, status_badge
from services import document_ai, storage, bigquery

st.set_page_config(page_title="Process POs", page_icon="📋", layout="wide")
apply_styles()
render_header("Process Purchase Orders", "Select a processor, upload documents, and extract data")

# --- Processor selector ---
st.subheader("Processor")

try:
    processors = document_ai.list_processors()
except Exception as e:
    processors = []
    st.error(f"Failed to list processors: {e}")

if not processors:
    st.warning("No processors available. Create one in the Admin page first.")
    if st.button("Go to Admin"):
        st.switch_page("pages/4_Admin.py")
    st.stop()

processor_options = {p["display_name"]: p["name"] for p in processors}
selected_display = st.selectbox(
    "Select processor",
    options=list(processor_options.keys()),
    label_visibility="collapsed",
)
selected_processor = processor_options[selected_display]

# --- File upload ---
st.subheader("Upload Documents")

uploaded_files = st.file_uploader(
    "Drag and drop files here",
    accept_multiple_files=True,
    type=["pdf", "png", "jpg", "jpeg", "tiff", "tif"],
    help="PDF, PNG, JPG, TIFF — up to 20 MB each",
)

if uploaded_files:
    st.caption(f"{len(uploaded_files)} file(s) selected")

# --- Process button ---
if uploaded_files and st.button("Process Documents", type="primary"):
    results = []

    with st.status(
        f"Processing {len(uploaded_files)} document(s)...", expanded=True
    ) as status_container:
        progress = st.progress(0)

        for i, uploaded_file in enumerate(uploaded_files):
            filename = uploaded_file.name
            file_bytes = uploaded_file.read()
            mime_type = document_ai.get_mime_type(filename)

            st.write(f"Processing **{filename}**... ({i + 1}/{len(uploaded_files)})")
            progress.progress((i) / len(uploaded_files))

            try:
                # Upload to GCS
                gcs_uri = storage.upload_file(file_bytes, filename, mime_type)

                # Extract with Document AI
                extraction = document_ai.process_document(
                    selected_processor, file_bytes, mime_type
                )

                # Save to BigQuery
                record_id = bigquery.save_extraction({
                    "filename": filename,
                    "gcs_uri": gcs_uri,
                    "processor_name": selected_processor,
                    "processor_display_name": selected_display,
                    "status": "EXTRACTED",
                    "extracted_data": extraction["fields"],
                    "confidence": extraction["confidence"],
                })

                results.append({
                    "id": record_id,
                    "filename": filename,
                    "gcs_uri": gcs_uri,
                    "processor_name": selected_processor,
                    "processor_display_name": selected_display,
                    "extracted_data": extraction["fields"],
                    "confidence": extraction["confidence"],
                    "status": "EXTRACTED",
                })

                st.write(f"  {filename} — confidence: {extraction['confidence']:.0%}")

            except Exception as e:
                st.error(f"Failed to process {filename}: {e}")
                results.append({
                    "filename": filename,
                    "error": str(e),
                    "status": "ERROR",
                })

        progress.progress(1.0)
        status_container.update(label="Processing complete!", state="complete")

    # Store results in session state for Review page
    st.session_state["results"] = results
    st.toast("Processing complete!", icon="✅")

# --- Display results ---
if "results" in st.session_state and st.session_state["results"]:
    st.divider()
    st.subheader("Results")

    for result in st.session_state["results"]:
        if result.get("status") == "ERROR":
            with st.expander(f"❌ {result['filename']} — Error", expanded=False):
                st.error(result.get("error", "Unknown error"))
            continue

        confidence = result.get("confidence", 0)
        conf_display = confidence_html(confidence)

        with st.expander(
            f"{result['filename']}  —  Confidence: {confidence:.0%}",
            expanded=True,
        ):
            fields = result.get("extracted_data", {})

            if fields:
                def _display_properties(properties, indent=0):
                    prefix = "&nbsp;" * (indent * 4)
                    for prop in properties:
                        col1, col2, col3 = st.columns([1, 2, 1])
                        col1.markdown(
                            f"{prefix}**{prop['name']}**",
                            unsafe_allow_html=True,
                        )
                        col2.write(prop.get("value", "—"))
                        col3.markdown(
                            confidence_html(prop.get("confidence", 0)),
                            unsafe_allow_html=True,
                        )
                        if prop.get("properties"):
                            _display_properties(prop["properties"], indent + 1)

                def _display_entity(field_name, field_data):
                    col1, col2, col3 = st.columns([1, 2, 1])
                    col1.write(f"**{field_name}**")
                    col2.write(field_data.get("value", "—"))
                    col3.markdown(
                        confidence_html(field_data.get("confidence", 0)),
                        unsafe_allow_html=True,
                    )
                    if field_data.get("properties"):
                        _display_properties(field_data["properties"], indent=1)

                for field_name, field_data in fields.items():
                    if isinstance(field_data, list):
                        st.write(f"**{field_name}** ({len(field_data)} items)")
                        for item in field_data:
                            _display_entity(field_name, item)
                            st.markdown("---")
                    else:
                        _display_entity(field_name, field_data)
            else:
                st.info("No fields extracted.")

            if st.button("Review & Edit", key=f"review_{result.get('id', result['filename'])}"):
                st.session_state["review_record_id"] = result.get("id")
                st.session_state["review_result"] = result
                st.switch_page("pages/2_Review.py")
