"""BigQuery service for extraction results storage."""

import json
import os
import uuid
from datetime import datetime

from google.cloud import bigquery


def _get_client() -> bigquery.Client:
    return bigquery.Client(project=os.environ["PROJECT_ID"])


def _table_id() -> str:
    project = os.environ["PROJECT_ID"]
    dataset = os.environ["BQ_DATASET"]
    return f"{project}.{dataset}.extractions"


def save_extraction(record: dict) -> str:
    """Insert an extraction result row. Returns the record ID."""
    client = _get_client()
    table = _table_id()
    record_id = record.get("id", uuid.uuid4().hex)

    query = f"""
        INSERT INTO `{table}`
        (id, filename, gcs_uri, processor_name, processor_display_name,
         status, extracted_data, confidence, created_at)
        VALUES
        (@id, @filename, @gcs_uri, @processor_name, @processor_display_name,
         @status, PARSE_JSON(@extracted_data), @confidence, @created_at)
    """
    params = [
        bigquery.ScalarQueryParameter("id", "STRING", record_id),
        bigquery.ScalarQueryParameter("filename", "STRING", record["filename"]),
        bigquery.ScalarQueryParameter("gcs_uri", "STRING", record["gcs_uri"]),
        bigquery.ScalarQueryParameter("processor_name", "STRING", record["processor_name"]),
        bigquery.ScalarQueryParameter("processor_display_name", "STRING", record.get("processor_display_name", "")),
        bigquery.ScalarQueryParameter("status", "STRING", record.get("status", "EXTRACTED")),
        bigquery.ScalarQueryParameter("extracted_data", "STRING", json.dumps(record["extracted_data"])),
        bigquery.ScalarQueryParameter("confidence", "FLOAT64", record.get("confidence", 0.0)),
        bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", datetime.utcnow().isoformat()),
    ]

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    client.query(query, job_config=job_config).result()

    return record_id


def update_extraction(record_id: str, updates: dict) -> None:
    """Update an extraction record (reviewed_data, status, timestamps)."""
    client = _get_client()
    table = _table_id()

    set_clauses = []
    params = []

    if "reviewed_data" in updates:
        set_clauses.append("reviewed_data = PARSE_JSON(@reviewed_data)")
        params.append(
            bigquery.ScalarQueryParameter(
                "reviewed_data", "STRING", json.dumps(updates["reviewed_data"])
            )
        )

    if "status" in updates:
        set_clauses.append("status = @status")
        params.append(
            bigquery.ScalarQueryParameter("status", "STRING", updates["status"])
        )

    if "reviewed_at" in updates:
        set_clauses.append("reviewed_at = @reviewed_at")
        params.append(
            bigquery.ScalarQueryParameter(
                "reviewed_at", "TIMESTAMP", updates["reviewed_at"]
            )
        )

    if "sent_at" in updates:
        set_clauses.append("sent_at = @sent_at")
        params.append(
            bigquery.ScalarQueryParameter("sent_at", "TIMESTAMP", updates["sent_at"])
        )

    if not set_clauses:
        return

    params.append(
        bigquery.ScalarQueryParameter("record_id", "STRING", record_id)
    )

    query = f"UPDATE `{table}` SET {', '.join(set_clauses)} WHERE id = @record_id"
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    client.query(query, job_config=job_config).result()


def get_extractions(
    status: str | None = None,
    days: int | None = None,
    filename_search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Query extraction history with optional filters."""
    client = _get_client()
    table = _table_id()

    conditions = []
    params = []

    if status:
        conditions.append("status = @status")
        params.append(
            bigquery.ScalarQueryParameter("status", "STRING", status)
        )

    if days:
        conditions.append(
            "created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)"
        )
        params.append(bigquery.ScalarQueryParameter("days", "INT64", days))

    if filename_search:
        conditions.append("LOWER(filename) LIKE LOWER(@filename_search)")
        params.append(
            bigquery.ScalarQueryParameter(
                "filename_search", "STRING", f"%{filename_search}%"
            )
        )

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT id, filename, gcs_uri, processor_name, processor_display_name,
               status, extracted_data, reviewed_data, confidence,
               created_at, reviewed_at, sent_at
        FROM `{table}`
        {where}
        ORDER BY created_at DESC
        LIMIT @limit OFFSET @offset
    """
    params.extend([
        bigquery.ScalarQueryParameter("limit", "INT64", limit),
        bigquery.ScalarQueryParameter("offset", "INT64", offset),
    ])

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    results = client.query(query, job_config=job_config).result()

    rows = []
    for row in results:
        record = dict(row)
        if record.get("extracted_data"):
            record["extracted_data"] = json.loads(record["extracted_data"])
        if record.get("reviewed_data"):
            record["reviewed_data"] = json.loads(record["reviewed_data"])
        rows.append(record)

    return rows


def get_extraction(record_id: str) -> dict | None:
    """Get a single extraction result by ID."""
    client = _get_client()
    table = _table_id()

    query = f"""
        SELECT id, filename, gcs_uri, processor_name, processor_display_name,
               status, extracted_data, reviewed_data, confidence,
               created_at, reviewed_at, sent_at
        FROM `{table}`
        WHERE id = @record_id
    """
    params = [bigquery.ScalarQueryParameter("record_id", "STRING", record_id)]
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    results = list(client.query(query, job_config=job_config).result())

    if not results:
        return None

    record = dict(results[0])
    if record.get("extracted_data"):
        record["extracted_data"] = json.loads(record["extracted_data"])
    if record.get("reviewed_data"):
        record["reviewed_data"] = json.loads(record["reviewed_data"])
    return record


def get_stats() -> dict:
    """Get aggregate stats: total processed, sent, pending."""
    client = _get_client()
    table = _table_id()

    query = f"""
        SELECT
            COUNT(*) AS total,
            COUNTIF(status = 'SENT') AS sent,
            COUNTIF(status IN ('EXTRACTED', 'REVIEWED')) AS pending,
            COUNTIF(status = 'PROCESSING') AS processing
        FROM `{table}`
    """
    results = list(client.query(query).result())
    if results:
        row = dict(results[0])
        return {
            "total": row.get("total", 0),
            "sent": row.get("sent", 0),
            "pending": row.get("pending", 0),
            "processing": row.get("processing", 0),
        }
    return {"total": 0, "sent": 0, "pending": 0, "processing": 0}


def get_extraction_count(
    status: str | None = None,
    days: int | None = None,
    filename_search: str | None = None,
) -> int:
    """Get the total count of extractions matching the filters."""
    client = _get_client()
    table = _table_id()

    conditions = []
    params = []

    if status:
        conditions.append("status = @status")
        params.append(
            bigquery.ScalarQueryParameter("status", "STRING", status)
        )

    if days:
        conditions.append(
            "created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)"
        )
        params.append(bigquery.ScalarQueryParameter("days", "INT64", days))

    if filename_search:
        conditions.append("LOWER(filename) LIKE LOWER(@filename_search)")
        params.append(
            bigquery.ScalarQueryParameter(
                "filename_search", "STRING", f"%{filename_search}%"
            )
        )

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"SELECT COUNT(*) AS cnt FROM `{table}` {where}"
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    results = list(client.query(query, job_config=job_config).result())
    return results[0]["cnt"] if results else 0
