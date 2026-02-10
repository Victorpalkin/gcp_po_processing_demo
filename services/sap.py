"""Mock SAP integration service for sending purchase orders.

This module simulates sending PO data to SAP. To integrate with a real SAP
system, set the following environment variables:

    SAP_API_URL  — SAP API endpoint for creating purchase orders
                   e.g. https://your-sap-instance.com/api/purchase-orders
    SAP_API_KEY  — API key or bearer token for authentication

When both variables are set, the module switches from mock mode to live mode.
See the comments inside send_purchase_order() for the exact lines to change.

Authentication options (pick one and adjust _get_headers()):
  - API key:  Set SAP_API_KEY and pass it in the x-api-key header.
  - OAuth:    Implement a token-fetch step in _get_headers() using client
              credentials and cache the token.
  - Basic:    Pass (user, password) via requests.post(..., auth=(...)).
"""

import logging
import os
import time
import uuid

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_api_url() -> str | None:
    """Return the SAP API URL if configured, else None (mock mode)."""
    return os.environ.get("SAP_API_URL")


def _get_headers() -> dict:
    """Build HTTP headers for the SAP API request.

    Adjust this function when switching to a real SAP integration:
      - For API-key auth:  return {"x-api-key": os.environ["SAP_API_KEY"]}
      - For OAuth:         fetch a bearer token and return
                           {"Authorization": f"Bearer {token}"}
    """
    api_key = os.environ.get("SAP_API_KEY", "")
    return {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def _build_sap_payload(po_data: dict, filename: str) -> dict:
    """Transform reviewed extraction data into an SAP-like payload.

    The returned structure mirrors a typical SAP PO creation request with
    a header section and a list of line items.

    Field mapping notes — adjust the keys on the *right-hand side* to match
    your SAP field catalogue:
      - "vendor"        -> SAP LIFNR (vendor number)
      - "po_number"     -> SAP EBELN (PO number)
      - "po_date"       -> SAP BEDAT (document date)
      - "currency"      -> SAP WAERS (currency key)
      - "total_amount"  -> SAP NETWR (net value)
    Line-item fields:
      - "description"   -> SAP TXZ01 (short text)
      - "quantity"      -> SAP MENGE (quantity)
      - "unit_price"    -> SAP NETPR (net price)
      - "amount"        -> SAP NETWR (item net value)
    """
    # --- header fields ---
    header: dict = {}
    for field_name, field_data in po_data.items():
        if isinstance(field_data, list):
            continue  # line items handled below
        value = field_data.get("value", "") if isinstance(field_data, dict) else field_data
        header[field_name] = value

    # --- line items ---
    line_items: list[dict] = []
    for field_name, field_data in po_data.items():
        if isinstance(field_data, list):
            for item in field_data:
                line_items.append(item if isinstance(item, dict) else {"value": item})

    return {
        "source_filename": filename,
        "header": header,
        "line_items": line_items,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_purchase_order(po_data: dict, filename: str) -> dict:
    """Send a purchase order to SAP (or simulate it in mock mode).

    Returns a dict with keys:
        document_number — SAP document ID (fake in mock mode)
        status          — "CREATED" on success
        message         — human-readable result description

    Raises RuntimeError on failure so callers can handle it.
    """
    payload = _build_sap_payload(po_data, filename)
    api_url = _get_api_url()

    if api_url:
        # -------------------------------------------------------------
        # REAL MODE — replace the mock block below with this:
        #
        #   import requests
        #   response = requests.post(
        #       api_url,
        #       json=payload,
        #       headers=_get_headers(),
        #       timeout=30,
        #   )
        #   response.raise_for_status()
        #   result = response.json()
        #   return {
        #       "document_number": result["document_number"],
        #       "status": "CREATED",
        #       "message": f"SAP document {result['document_number']} created.",
        #   }
        # -------------------------------------------------------------
        raise NotImplementedError(
            "Live SAP integration is not yet implemented. "
            "See the comments in services/sap.py for instructions."
        )

    # ----- MOCK MODE -----
    logger.info("MOCK SAP: sending PO for %s", filename)
    logger.debug("MOCK SAP payload: %s", payload)

    # Simulate network latency
    time.sleep(0.5)

    doc_number = f"SAP-{uuid.uuid4().hex[:8].upper()}"
    logger.info("MOCK SAP: created document %s", doc_number)

    return {
        "document_number": doc_number,
        "status": "CREATED",
        "message": f"Mock SAP document {doc_number} created for {filename}.",
    }
