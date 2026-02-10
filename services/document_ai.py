"""Document AI service for processor management and document extraction."""

import os
import time

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
        dataset_name = f"{processor_name}/dataset"
        dataset = doc_client.get_dataset_schema(name=dataset_name)
        if dataset.document_schema and dataset.document_schema.entity_types:
            for entity_type in dataset.document_schema.entity_types:
                for prop in entity_type.properties:
                    field = {
                        "name": prop.name,
                        "display_name": prop.display_name or prop.name,
                        "description": prop.description or "",
                        "occurrence_type": prop.occurrence_type.name
                        if prop.occurrence_type
                        else "OPTIONAL_ONCE",
                        "value_type": prop.value_type or "string",
                    }
                    info["fields"].append(field)
    except Exception:
        # Schema may not exist yet for new processors
        pass

    return info


def create_processor(
    display_name: str,
    description: str,
    fields: list[dict],
) -> str:
    """Create a new Custom Extraction processor with a foundation model schema.

    Args:
        display_name: Human-readable name for the processor.
        description: Description of the processor.
        fields: List of field dicts with keys:
            name, display_name, description, type ("Extract"/"Derive"), required

    Returns:
        The processor resource name.
    """
    client = _get_client()
    parent = _parent()

    # Step 1: Create the processor
    processor = client.create_processor(
        parent=parent,
        processor=documentai.Processor(
            display_name=display_name,
            type_="CUSTOM_EXTRACTION_PROCESSOR",
        ),
    )
    processor_name = processor.name

    # Step 2: Update dataset schema with entity types
    properties = []
    for field in fields:
        occurrence = (
            documentai.DocumentSchema.EntityType.Property.OccurrenceType.REQUIRED_ONCE
            if field.get("required", False)
            else documentai.DocumentSchema.EntityType.Property.OccurrenceType.OPTIONAL_ONCE
        )

        prop = documentai.DocumentSchema.EntityType.Property(
            name=field["name"],
            display_name=field.get("display_name", field["name"]),
            description=field.get("description", ""),
            value_type=field.get("value_type", "string"),
            occurrence_type=occurrence,
        )
        properties.append(prop)

    entity_type = documentai.DocumentSchema.EntityType(
        name="custom_extraction_document_type",
        display_name=display_name,
        properties=properties,
        base_types=["document"],
    )

    schema = documentai.DocumentSchema(
        entity_types=[entity_type],
        description=description,
    )
    dataset_schema = documentai.DatasetSchema(
        name=f"{processor_name}/dataset",
        document_schema=schema,
    )

    try:
        doc_client = _get_doc_service_client()
        doc_client.update_dataset_schema(dataset_schema=dataset_schema)
    except Exception as e:
        raise RuntimeError(f"Failed to update dataset schema: {e}")

    # Step 3: Train processor version with foundation model (GenAI / zero-shot)
    try:
        train_request = documentai.TrainProcessorVersionRequest(
            parent=processor_name,
            processor_version=documentai.ProcessorVersion(
                display_name="v1",
            ),
            foundation_model_tuning_options=documentai.TrainProcessorVersionRequest.FoundationModelTuningOptions(
                train_steps=0,  # Zero-shot: no training data needed
            ),
        )
        operation = client.train_processor_version(request=train_request)
        # Wait for training to complete
        result = operation.result(timeout=600)
        version_name = result.processor_version

        # Step 4: Deploy the trained version
        deploy_operation = client.deploy_processor_version(name=version_name)
        deploy_operation.result(timeout=300)

        # Set as default version
        client.set_default_processor_version(
            processor=processor_name,
            default_processor_version=version_name,
        )
    except Exception as e:
        raise RuntimeError(
            f"Processor created ({processor_name}) but version training/deploy failed: {e}"
        )

    return processor_name


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
            field_data["properties"] = []
            for prop in entity.properties:
                field_data["properties"].append({
                    "name": prop.type_,
                    "value": prop.mention_text or "",
                    "confidence": prop.confidence or 0.0,
                })

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
