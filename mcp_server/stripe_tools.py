"""Stripe REST helpers (test mode).

Talks to https://api.stripe.com directly with `requests` so the demo has no heavy
SDK dependency and every call is readable. Only the operations the agent needs are
implemented, and every write path is a single, explicit function.
"""

from __future__ import annotations

import os
from typing import Any, Sequence

import requests

from . import business_rules as rules

STRIPE_API_BASE = "https://api.stripe.com"
DEFAULT_TIMEOUT = 30


class StripeError(RuntimeError):
    """Raised for configuration problems and non-2xx Stripe responses."""


def _api_key() -> str:
    key = (os.environ.get("STRIPE_API_KEY") or "").strip()
    if not key:
        raise StripeError(
            "STRIPE_API_KEY is not set. Copy .env.example to .env and use a Stripe "
            "TEST key (sk_test_...)."
        )
    if not key.startswith("sk_test_"):
        # Not fatal: the caller may deliberately point at a live account. The demo
        # should not.
        print("WARNING: STRIPE_API_KEY is not a test key (sk_test_...).")
    return key


def _request(
    method: str,
    path: str,
    data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if data is not None:
        data = _encode(data)
    response = requests.request(
        method,
        f"{STRIPE_API_BASE}{path}",
        headers={"Authorization": f"Bearer {_api_key()}"},
        data=data,
        params=params,
        timeout=DEFAULT_TIMEOUT,
    )
    try:
        body = response.json()
    except ValueError:
        raise StripeError(f"Stripe returned a non-JSON response (HTTP {response.status_code})")

    if response.status_code >= 300:
        message = (body.get("error") or {}).get("message") or f"HTTP {response.status_code}"
        raise StripeError(message)
    return body


def _encode(payload: dict[str, Any]) -> dict[str, Any]:
    """Stripe's REST API is form-encoded: booleans become 'true'/'false'."""
    encoded: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, bool):
            encoded[key] = "true" if value else "false"
        else:
            encoded[key] = value
    return encoded


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_customers(limit: int = 100) -> list[dict[str, Any]]:
    body = _request("GET", "/v1/customers", params={"limit": max(1, min(limit, 100))})
    return body.get("data", [])


def get_customer(customer_id: str) -> dict[str, Any]:
    return _request("GET", f"/v1/customers/{customer_id}")


def search_customers(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fuzzy-match a spoken customer name against the stored customers."""
    return rules.match_customers(query, list_customers(limit=100), limit=limit)


def list_customer_invoices(customer_id: str, limit: int = 100) -> list[dict[str, Any]]:
    body = _request(
        "GET",
        "/v1/invoices",
        params={"customer": customer_id, "limit": max(1, min(limit, 100))},
    )
    return body.get("data", [])


def list_open_invoices(limit: int = 100) -> list[dict[str, Any]]:
    body = _request("GET", "/v1/invoices", params={"status": "open", "limit": max(1, min(limit, 100))})
    return body.get("data", [])


def get_invoice(invoice_id: str) -> dict[str, Any]:
    return _request("GET", f"/v1/invoices/{invoice_id}")


# ---------------------------------------------------------------------------
# Writes — every one of these is a consequential action
# ---------------------------------------------------------------------------


def send_invoice(invoice_id: str) -> dict[str, Any]:
    """Email the customer their invoice (Stripe's own reminder delivery)."""
    return _request("POST", f"/v1/invoices/{invoice_id}/send")


def create_customer(name: str | None = None, email: str | None = None) -> dict[str, Any]:
    """Create a test customer. Used by `demo.seed_test_data`."""
    return _request("POST", "/v1/customers", data={"name": name, "email": email})


def create_invoice_item(
    customer_id: str,
    amount_minor: int,
    currency: str = "usd",
    description: str | None = None,
) -> dict[str, Any]:
    """Attach a line item to the customer's next invoice."""
    return _request(
        "POST",
        "/v1/invoiceitems",
        data={
            "customer": customer_id,
            "amount": int(amount_minor),
            "currency": currency,
            "description": description,
        },
    )


def create_invoice(
    customer_id: str,
    currency: str = "usd",
    due_date: int | None = None,
    days_until_due: int | None = None,
    auto_advance: bool = False,
) -> dict[str, Any]:
    """Create an invoice the caller will finalize.

    `send_invoice` collection is what makes an invoice carry a due date, which is
    what makes overdue detection meaningful. `auto_advance=False` keeps it a draft
    until `finalize_invoice` is called.
    """
    return _request(
        "POST",
        "/v1/invoices",
        data={
            "customer": customer_id,
            "currency": currency,
            "collection_method": "send_invoice",
            "due_date": due_date,
            "days_until_due": days_until_due,
            "auto_advance": auto_advance,
        },
    )


def finalize_invoice(invoice_id: str) -> dict[str, Any]:
    """Move a draft invoice to open, so it can be paid or reminded."""
    return _request("POST", f"/v1/invoices/{invoice_id}/finalize")


def enrich_customer(invoice: dict[str, Any], customers_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Attach a readable customer name to an invoice for display purposes."""
    customer_id = invoice.get("customer")
    customer = customers_by_id.get(customer_id) if isinstance(customer_id, str) else None
    return {**invoice, "customer_name": rules.customer_display_name(customer)}


def customers_by_id(customers: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in customers if c.get("id")}
