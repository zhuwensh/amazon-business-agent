"""BusinessFlow Agent — self-hosted MCP server.

Business-level tools, not a raw API wrapper: the agent decides which tool to call
and in what order. Every tool returns the structured result under `data` and a
speakable sentence under `spoken`, so the same call can feed a dashboard or a
voice assistant.

Transport:
    MCP_HTTP=1  -> Streamable HTTP at http://<MCP_HOST>:<MCP_PORT>/mcp
    otherwise   -> stdio (Cursor, Claude Desktop, ...)
"""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP

from . import business_rules as rules
from . import config
from . import messages
from . import slack_tools as slack
from . import stripe_tools as stripe

mcp = FastMCP("businessflow-agent")


def _ok(data: dict[str, Any], spoken: str) -> dict[str, Any]:
    return {"ok": True, "data": data, "spoken": spoken}


def _error(message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": message, "spoken": message, **extra}


def _resolve_customer(customer: str, customer_id: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve a spoken name (or an explicit id) to one Stripe customer.

    Returns (customer, None) on success, or (None, payload) when the caller has to
    ask the user which customer they meant.
    """
    if customer_id:
        try:
            return stripe.get_customer(customer_id), None
        except stripe.StripeError as exc:
            return None, _error(f"Could not load customer {customer_id}: {exc}")

    candidates = stripe.search_customers(customer, limit=5)
    if not candidates:
        return None, _error(
            f"I could not find a customer matching '{customer}'.",
            data={"candidates": []},
        )

    top = candidates[0]
    if top["match_score"] >= 0.95 or len(candidates) == 1:
        return top, None

    return None, _ok(
        {
            "needs_disambiguation": True,
            "candidates": [
                {
                    "id": c["id"],
                    "name": rules.customer_display_name(c),
                    "email": c.get("email"),
                    "match_score": c["match_score"],
                }
                for c in candidates
            ],
        },
        messages.spoken_disambiguation(candidates),
    )


@mcp.tool
def find_customer(query: str) -> dict[str, Any]:
    """Look up a customer by name or email.

    Use this first when the user names a company. Returns ranked candidates with a
    match score; ask the user to choose when the best match is not close.
    """
    try:
        candidates = stripe.search_customers(query, limit=5)
    except stripe.StripeError as exc:
        return _error(f"Stripe lookup failed: {exc}")

    if not candidates:
        return _ok({"candidates": []}, f"I could not find a customer matching '{query}'.")

    payload = {
        "candidates": [
            {
                "id": c["id"],
                "name": rules.customer_display_name(c),
                "email": c.get("email"),
                "match_score": c["match_score"],
            }
            for c in candidates
        ]
    }
    confident = candidates[0]["match_score"] >= 0.95 or len(candidates) == 1
    spoken = (
        messages.spoken_customer_found(candidates)
        if confident
        else messages.spoken_disambiguation(candidates)
    )
    return _ok(payload, spoken)


@mcp.tool
def get_overdue_invoices(customer: str, customer_id: str | None = None) -> dict[str, Any]:
    """List the overdue invoices for one customer, oldest first.

    Returns each invoice with its amount, days overdue, due date and payment link,
    plus a total. Pass `customer_id` when the user has already chosen from
    `find_customer` candidates.
    """
    resolved, problem = _resolve_customer(customer, customer_id)
    if problem is not None:
        return problem

    try:
        invoices = stripe.list_customer_invoices(resolved["id"])
    except stripe.StripeError as exc:
        return _error(f"Stripe lookup failed: {exc}")

    summary = rules.summarize_overdue(invoices)
    name = rules.customer_display_name(resolved)
    payload = {
        "customer": {"id": resolved["id"], "name": name, "email": resolved.get("email")},
        "count": summary["count"],
        "total_minor": summary["total_minor"],
        "currency": summary["currency"],
        "oldest_days": summary["oldest_days"],
        "invoices": [
            {
                "id": inv["id"],
                "number": rules.invoice_reference(inv),
                "amount_minor": rules.amount_due_minor(inv),
                "currency": inv.get("currency"),
                "due_date": inv.get("due_date"),
                "days_overdue": rules.days_overdue(inv.get("due_date")),
                "payment_link": inv.get("hosted_invoice_url"),
            }
            for inv in summary["invoices"]
        ],
    }
    return _ok(payload, messages.spoken_overdue_summary(name, summary))


@mcp.tool
def get_cashflow_summary(limit: int = 100) -> dict[str, Any]:
    """Account-wide outstanding and overdue totals, and who owes the money.

    Use this when the user asks how the business is doing, or who owes them,
    rather than about a specific customer. The per-customer rollup is the only way
    into the data for a user who has not been told any customer names.
    """
    try:
        invoices = stripe.list_open_invoices(limit=limit)
    except stripe.StripeError as exc:
        return _error(f"Stripe lookup failed: {exc}")

    summary = rules.summarize_overdue(invoices)
    outstanding: dict[str, int] = {}
    for inv in invoices:
        code = (inv.get("currency") or "usd").lower()
        outstanding[code] = outstanding.get(code, 0) + rules.amount_due_minor(inv)

    by_customer: list[dict[str, Any]] = []
    if summary["count"]:
        try:
            customers = stripe.customers_by_id(stripe.list_customers(limit=100))
        except stripe.StripeError as exc:
            return _error(f"Stripe customer lookup failed: {exc}")
        by_customer = rules.group_overdue_by_customer(invoices, customers)

    payload = {
        "open_invoice_count": len(invoices),
        "outstanding_by_currency": outstanding,
        "overdue_count": summary["count"],
        "overdue_by_currency": summary["totals_by_currency"],
        "oldest_overdue_days": summary["oldest_days"],
        "overdue_by_customer": by_customer,
    }
    return _ok(payload, messages.spoken_cashflow_summary(len(invoices), summary, by_customer))


@mcp.tool
def send_payment_reminder(invoice_id: str, confirmed: bool = False) -> dict[str, Any]:
    """Email a customer their invoice as a payment reminder.

    This is a consequential action: it contacts the customer. It will not run
    unless `confirmed=True`, and it returns needs_confirmation first so the agent
    can ask the user in their own words.
    """
    try:
        invoice = stripe.get_invoice(invoice_id)
    except stripe.StripeError as exc:
        return _error(f"Could not load invoice {invoice_id}: {exc}")

    reference = rules.invoice_reference(invoice)
    amount = rules.amount_due_minor(invoice)
    currency = invoice.get("currency")

    if not confirmed:
        return {
            "ok": False,
            "needs_confirmation": True,
            "data": {"invoice_id": invoice_id, "number": reference, "amount_minor": amount, "currency": currency},
            "spoken": (
                f"That will email the customer a reminder for {reference} "
                f"({rules.format_money(amount, currency)}). Should I send it?"
            ),
        }

    try:
        stripe.send_invoice(invoice_id)
    except stripe.StripeError as exc:
        return _error(f"Stripe refused to send invoice {reference}: {exc}")

    try:
        customer = stripe.get_customer(invoice["customer"]) if invoice.get("customer") else None
    except stripe.StripeError:
        customer = None
    name = rules.customer_display_name(customer)

    payload = {
        "invoice_id": invoice_id,
        "number": reference,
        "customer": name,
        "amount_minor": amount,
        "currency": currency,
        "payment_link": invoice.get("hosted_invoice_url"),
    }
    return _ok(payload, messages.spoken_reminder_sent(name, reference, amount, currency))


@mcp.tool
def notify_finance_team(message: str, confirmed: bool = False) -> dict[str, Any]:
    """Post a message to the finance Slack channel.

    Consequential action: it is visible to the whole team. Requires
    `confirmed=True`; without it the tool returns needs_confirmation.
    """
    channel = slack.finance_channel()
    if not confirmed:
        return {
            "ok": False,
            "needs_confirmation": True,
            "data": {"channel": channel, "message": message},
            "spoken": f"Should I post that to {channel}?",
        }

    try:
        result = slack.post_message(message)
    except slack.SlackError as exc:
        return _error(f"Slack notification failed: {exc}")

    return _ok(
        {"channel": result["channel"], "message": message},
        messages.spoken_finance_notified(str(result["channel"])),
    )


def main() -> None:
    # Windows consoles default to a legacy code page; a non-ASCII character in a
    # print call would abort startup before the server binds. Keep the banner ASCII
    # and make stdout forgiving anyway.
    config.bootstrap()

    use_http = (os.environ.get("MCP_HTTP") or "").strip().lower() in {"1", "true", "yes"}
    print("BusinessFlow Agent - MCP server")
    print("Tools: find_customer, get_overdue_invoices, get_cashflow_summary,")
    print("       send_payment_reminder, notify_finance_team")

    if use_http:
        host = (os.environ.get("MCP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
        port = int((os.environ.get("MCP_PORT") or "8000").strip() or "8000")
        print(f"Streamable HTTP endpoint: http://{host}:{port}/mcp")
        mcp.run(transport="http", host=host, port=port, path="/mcp")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
