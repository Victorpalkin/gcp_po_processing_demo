"""Document AI service for processor management and document extraction."""

import os

from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1beta3 as documentai


def _get_client() -> documentai.DocumentProcessorServiceClient:
    location = os.environ.get("DOCAI_LOCATION", "us")
    opts = ClientOptions(
        api_endpoint=f"{location}-documentai.googleapis.com"
    )
    return documentai.DocumentProcessorServiceClient(client_options=opts)


def _get_doc_service_client() -> documentai.DocumentServiceClient:
    location = os.environ.get("DOCAI_LOCATION", "us")
    opts = ClientOptions(
        api_endpoint=f"{location}-documentai.googleapis.com"
    )
    return documentai.DocumentServiceClient(client_options=opts)


def _parent() -> str:
    project = os.environ["PROJECT_ID"]
    location = os.environ.get("DOCAI_LOCATION", "us")
    return f"projects/{project}/locations/{location}"


def list_processors() -> list[dict]:
    """List all CUSTOM_EXTRACTION_PROCESSOR processors in the project."""
    client = _get_client()
    parent = _parent()

    processors = []
    for processor in client.list_processors(parent=parent):
        if processor.type_ == "CUSTOM_EXTRACTION_PROCESSOR":
            processors.append({
                "name": processor.name,
                "display_name": processor.display_name,
                "state": processor.state.name,
                "type": processor.type_,
                "create_time": processor.create_time,
                "default_processor_version": processor.default_processor_version,
            })

    return processors


def get_processor_with_schema(processor_name: str) -> dict:
    """Get processor info including its dataset schema (field definitions)."""
    client = _get_client()

    processor = client.get_processor(name=processor_name)
    info = {
        "name": processor.name,
        "display_name": processor.display_name,
        "state": processor.state.name,
        "type": processor.type_,
        "create_time": processor.create_time,
        "default_processor_version": processor.default_processor_version,
        "fields": [],
    }

    # Get dataset schema for field definitions
    try:
        doc_client = _get_doc_service_client()
        dataset_name = f"{processor_name}/dataset/datasetSchema"
        dataset = doc_client.get_dataset_schema(name=dataset_name)
        if dataset.document_schema and dataset.document_schema.entity_types:
            for entity_type in dataset.document_schema.entity_types:
                is_root = "document" in list(entity_type.base_types)
                for prop in entity_type.properties:
                    field = {
                        "name": prop.name,
                        "display_name": prop.display_name or prop.name,
                        "description": prop.description or "",
                        "occurrence_type": prop.occurrence_type.name
                        if prop.occurrence_type
                        else "OPTIONAL_ONCE",
                        "value_type": prop.value_type or "string",
                        "parent": "" if is_root else entity_type.name,
                    }
                    info["fields"].append(field)
    except Exception:
        pass

    return info


def _parse_entity_properties(properties):
    """Recursively parse entity properties into nested dicts."""
    parsed = []
    for prop in properties:
        entry = {
            "name": prop.type_,
            "value": prop.mention_text or "",
            "confidence": prop.confidence or 0.0,
        }
        if prop.properties:
            entry["properties"] = _parse_entity_properties(prop.properties)
        parsed.append(entry)
    return parsed


def delete_processor(processor_name: str) -> None:
    """Delete a processor."""
    client = _get_client()
    operation = client.delete_processor(name=processor_name)
    operation.result(timeout=120)


def process_document(
    processor_name: str,
    file_bytes: bytes,
    mime_type: str,
) -> dict:
    """Process a document and extract structured fields.

    Args:
        processor_name: Full resource name of the processor.
        file_bytes: Raw document bytes.
        mime_type: MIME type (e.g., "application/pdf", "image/png").

    Returns:
        Dict with:
            fields: { field_name: { value, confidence, type } }
            confidence: overall average confidence
            raw_text: full OCR text
    """
    client = _get_client()

    raw_document = documentai.RawDocument(
        content=file_bytes,
        mime_type=mime_type,
    )

    request = documentai.ProcessRequest(
        name=processor_name,
        raw_document=raw_document,
    )

    result = client.process_document(request=request)
    document = result.document

    # Parse entities into structured fields
    fields = {}
    total_confidence = 0.0
    entity_count = 0

    for entity in document.entities:
        field_name = entity.type_
        confidence = entity.confidence or 0.0

        field_data = {
            "value": entity.mention_text or entity.normalized_value.text
            if entity.normalized_value
            else entity.mention_text or "",
            "confidence": confidence,
            "type": entity.type_,
        }

        # Handle nested properties (line items, etc.)
        if entity.properties:
            field_data["properties"] = _parse_entity_properties(entity.properties)

        # Handle multiple entities of the same type (e.g., line items)
        if field_name in fields:
            if isinstance(fields[field_name], list):
                fields[field_name].append(field_data)
            else:
                fields[field_name] = [fields[field_name], field_data]
        else:
            fields[field_name] = field_data

        total_confidence += confidence
        entity_count += 1

    overall_confidence = (
        total_confidence / entity_count if entity_count > 0 else 0.0
    )

    return {
        "fields": fields,
        "confidence": overall_confidence,
        "raw_text": document.text or "",
    }


def get_mime_type(filename: str) -> str:
    """Determine MIME type from filename extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_map = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "tiff": "image/tiff",
        "tif": "image/tiff",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "webp": "image/webp",
    }
    return mime_map.get(ext, "application/octet-stream")
