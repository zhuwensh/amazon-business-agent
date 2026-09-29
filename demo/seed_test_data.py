"""Seed a Stripe TEST account with a stable demo scenario.

Creates, in test mode only:

* **Acme Corp** — two overdue invoices plus one current invoice. This is the
  customer the demo talks about.
* **Initech LLC** — one overdue invoice, so account-wide totals differ from
  Acme's.
* **Globex Corporation** — nothing overdue, which also exercises the fuzzy
  matching path ("Globex" vs "Globex Corporation").

    python -m demo.seed_test_data
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from mcp_server import stripe_tools as stripe

DEMO_CUSTOMERS = {
    "acme": {"name": "Acme Corp", "email": "billing@acme.example"},
    "initech": {"name": "Initech LLC", "email": "ap@initech.example"},
    "globex": {"name": "Globex Corporation", "email": "finance@globex.example"},
}


def _unix(days_from_now: int) -> int:
    moment = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    return int(moment.replace(hour=12, minute=0, second=0, microsecond=0).timestamp())


def _create_customer(name: str, email: str) -> str:
    # Reuse an existing customer when its id is provided, so re-running the seeder
    # does not pile up duplicates.
    key = name.split()[0].lower()
    handle = os.environ.get(f"DEMO_CUSTOMER_{key.upper()}_ID")
    if handle:
        print(f"  reusing {name} ({handle})")
        return handle

    # Also reuse a customer with the same name and email: a demo account may
    # already contain one, and duplicates would make the agent ask which customer
    # was meant on every run.
    existing = _find_customer_by_name_email(name, email)
    if existing:
        print(f"  reusing existing {name} ({existing})")
        return existing

    customer = stripe.create_customer(name=name, email=email)
    print(f"  created {name} ({customer['id']})")
    return customer["id"]


def _find_customer_by_name_email(name: str, email: str) -> str | None:
    wanted_name = (name or "").strip().lower()
    wanted_email = (email or "").strip().lower()
    for customer in stripe.list_customers(limit=100):
        same_name = (customer.get("name") or "").strip().lower() == wanted_name
        same_email = (customer.get("email") or "").strip().lower() == wanted_email
        if same_name and same_email:
            return customer["id"]
    return None


def _create_invoice(
    customer_id: str, amount_minor: int, description: str, due_in_days: int
) -> dict:
    stripe.create_invoice_item(customer_id, amount_minor, description=description)
    # Stripe rejects a `due_date` in the past at creation, so create and finalize
    # with a future due date and then back-date the invoice. Back-dating is what
    # produces a genuinely overdue invoice.
    lead_time = due_in_days if due_in_days > 0 else 30
    invoice = stripe.finalize_invoice(
        stripe.create_invoice(customer_id, due_date=_unix(lead_time))["id"]
    )
    if due_in_days <= 0:
        invoice = stripe.update_invoice_due_date(invoice["id"], _unix(due_in_days))
    return invoice


def main() -> None:
    load_dotenv()
    key = os.environ.get("STRIPE_API_KEY", "")
    if not key:
        raise SystemExit("STRIPE_API_KEY is not set. Copy .env.example to .env first.")
    if not key.startswith("sk_test_"):
        raise SystemExit(
            "Refusing to seed: STRIPE_API_KEY is not a test key (sk_test_...). "
            "This script creates invoices and sends nothing, but it should never "
            "run against a live account."
        )

    print("Seeding demo data in Stripe test mode...")

    acme = _create_customer(**DEMO_CUSTOMERS["acme"])
    _create_invoice(acme, 180000, "Website redesign — phase 1", due_in_days=-18)
    _create_invoice(acme, 140000, "Website redesign — phase 2", due_in_days=-6)
    _create_invoice(acme, 95000, "Retainer — current month", due_in_days=21)

    initech = _create_customer(**DEMO_CUSTOMERS["initech"])
    _create_invoice(initech, 60000, "Onboarding workshop", due_in_days=-11)

    globex = _create_customer(**DEMO_CUSTOMERS["globex"])
    _create_invoice(globex, 120000, "Support plan", due_in_days=14)

    print("\nDone. Ask the agent:")
    print('  "Does Acme have anything overdue?"        -> 2 overdue, $3,200.00, oldest 18 days')
    print('  "How are we doing this month?"            -> account-wide totals')
    print('  "Anything late for Globex?"               -> nothing overdue')


if __name__ == "__main__":
    main()
