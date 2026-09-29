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


def test_clock() -> str | None:
    """Optional Stripe test clock to scope every read to.

    Stripe does not let you create or back-date an invoice to a due date in the
    past, so a *fresh* test account cannot be given overdue invoices through the
    normal API. The supported way to produce them is a test clock frozen in the
    past — but objects on a clock are invisible to the account-wide list
    endpoints, so reads have to be scoped to it.

    Unset by default: a normal account reads normally. `demo/seed_test_data.py`
    sets it for you when it creates the demo scenario.
    """
    return (os.environ.get("STRIPE_TEST_CLOCK") or "").strip() or None


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
    params: dict[str, Any] = {"limit": max(1, min(limit, 100))}
    clock = test_clock()
    if clock:
        params["test_clock"] = clock
    body = _request("GET", "/v1/customers", params=params)
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
    clock = test_clock()
    if clock:
        # Clock objects are not returned by /v1/invoices, and that endpoint has no
        # test_clock filter, so gather them customer by customer.
        collected: list[dict[str, Any]] = []
        for customer in list_customers(limit=100):
            collected.extend(list_customer_invoices(customer["id"], limit=limit))
        open_invoices = [inv for inv in collected if (inv.get("status") or "") == "open"]
        return open_invoices[: max(1, limit)]

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


def create_customer(
    name: str | None = None,
    email: str | None = None,
    test_clock: str | None = None,
) -> dict[str, Any]:
    """Create a test customer. Used by `demo.seed_test_data`.

    `test_clock` places the customer at the clock's frozen time, which is what
    makes it possible to create invoices that are genuinely overdue in test mode.
    """
    return _request(
        "POST", "/v1/customers", data={"name": name, "email": email, "test_clock": test_clock}
    )


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
    metadata: dict[str, str] | None = None,
    include_pending_items: bool = True,
) -> dict[str, Any]:
    """Create an invoice the caller will finalize.

    `send_invoice` collection is what makes an invoice carry a due date, which is
    what makes overdue detection meaningful. `auto_advance=False` keeps it a draft
    until `finalize_invoice` is called.

    `include_pending_items` matters: adding an invoice item makes Stripe create a
    draft invoice of its own, so without this flag `POST /v1/invoices` produces a
    second, empty invoice that finalizes as a zero-amount *paid* invoice.
    """
    data: dict[str, Any] = {
        "customer": customer_id,
        "currency": currency,
        "collection_method": "send_invoice",
        "due_date": due_date,
        "days_until_due": days_until_due,
        "auto_advance": auto_advance,
    }
    if include_pending_items:
        data["pending_invoice_items_behavior"] = "include"
    for key, value in (metadata or {}).items():
        data[f"metadata[{key}]"] = value
    return _request("POST", "/v1/invoices", data=data)


def finalize_invoice(invoice_id: str) -> dict[str, Any]:
    """Move a draft invoice to open, so it can be paid or reminded."""
    return _request("POST", f"/v1/invoices/{invoice_id}/finalize")


def update_invoice_due_date(invoice_id: str, due_date: int) -> dict[str, Any]:
    """Back-date an open invoice.

    Stripe refuses a `due_date` in the past when the invoice is created, so the
    only way to produce a genuinely overdue invoice on demand is to create it with
    a future due date and then move the due date back.
    """
    return _request("POST", f"/v1/invoices/{invoice_id}", data={"due_date": int(due_date)})


def void_invoice(invoice_id: str) -> dict[str, Any]:
    """Void an open invoice, so a re-run of the seeder starts from a clean slate."""
    return _request("POST", f"/v1/invoices/{invoice_id}/void")


# ---------------------------------------------------------------------------
# Test clocks — the supported way to create genuinely overdue test invoices
# ---------------------------------------------------------------------------


def list_test_clocks(limit: int = 20) -> list[dict[str, Any]]:
    body = _request(
        "GET", "/v1/test_helpers/test_clocks", params={"limit": max(1, min(limit, 100))}
    )
    return body.get("data", [])


def create_test_clock(frozen_time: int, name: str | None = None) -> dict[str, Any]:
    """Freeze a simulated timeline at `frozen_time`."""
    return _request(
        "POST",
        "/v1/test_helpers/test_clocks",
        data={"frozen_time": int(frozen_time), "name": name},
    )


def advance_test_clock(clock_id: str, frozen_time: int) -> dict[str, Any]:
    """Move a clock forward. One-way: time never goes back."""
    return _request(
        "POST",
        f"/v1/test_helpers/test_clocks/{clock_id}/advance",
        data={"frozen_time": int(frozen_time)},
    )


def enrich_customer(invoice: dict[str, Any], customers_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Attach a readable customer name to an invoice for display purposes."""
    customer_id = invoice.get("customer")
    customer = customers_by_id.get(customer_id) if isinstance(customer_id, str) else None
    return {**invoice, "customer_name": rules.customer_display_name(customer)}


def customers_by_id(customers: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in customers if c.get("id")}
