"""Seed a Stripe TEST account with a stable demo scenario.

Creates, in test mode only:

* **Acme Corp** — two overdue invoices plus one current invoice. This is the
  customer the demo talks about.
* **Initech LLC** — one overdue invoice, so account-wide totals differ from
  Acme's.
* **Globex Corporation** — nothing overdue, which also exercises the fuzzy
  matching path ("Globex" vs "Globex Corporation").

Re-running is safe and is the intended way to refresh the numbers before a
recording: previously seeded invoices are voided first, then re-created with
due dates relative to today.

    python -m demo.seed_test_data

Why a test clock: Stripe refuses to create *or* update an invoice with a due date
in the past, so a fresh test account cannot simply be given overdue invoices. A
test clock freezes a simulated timeline in the past, which is the supported way to
produce invoices that are genuinely overdue. Objects on a clock are invisible to
the account-wide list endpoints, so the script writes `STRIPE_TEST_CLOCK` into
`.env` and the MCP server scopes its reads to that clock. Restart the server after
running this.

A test clock holds at most 3 customers, which is exactly the number of customers
this scenario needs.
"""

from __future__ import annotations

import os
import pathlib
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from mcp_server import business_rules as rules
from mcp_server import messages
from mcp_server import stripe_tools as stripe

CLOCK_NAME = "businessflow-demo"
CLOCK_LOOKBACK_DAYS = 90
DEMO_TAG = {"businessflow_demo": "true"}

DEMO_CUSTOMERS = {
    "acme": {"name": "Acme Corp", "email": "billing@acme.example"},
    "initech": {"name": "Initech LLC", "email": "ap@initech.example"},
    "globex": {"name": "Globex Corporation", "email": "finance@globex.example"},
}

# (customer key, amount in minor units, description, due in N days from today)
DEMO_INVOICES = [
    ("acme", 180000, "Website redesign - phase 1", -18),
    ("acme", 140000, "Website redesign - phase 2", -6),
    ("acme", 95000, "Retainer - current month", 21),
    ("initech", 60000, "Onboarding workshop", -11),
    ("globex", 120000, "Support plan", 14),
]


def _unix(days_from_now: int) -> int:
    moment = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    # Align to UTC midnight: it is always strictly earlier than "now minus N days",
    # so the reported age is exactly N days rather than N-1.
    return int(moment.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def _get_or_create_clock() -> str:
    """One long-lived clock, frozen in the past and never advanced.

    Keeping a single clock frozen means every run can still create invoices with
    due dates between the clock's time and today, so the script stays repeatable.
    """
    configured = (os.environ.get("STRIPE_TEST_CLOCK") or "").strip()
    if configured:
        print(f"  using test clock from .env ({configured})")
        return configured

    for clock in stripe.list_test_clocks():
        if clock.get("name") == CLOCK_NAME and clock.get("status") == "ready":
            print(f"  reusing test clock {clock['id']}")
            _remember_clock(clock["id"])
            return clock["id"]

    clock = stripe.create_test_clock(_unix(-CLOCK_LOOKBACK_DAYS), name=CLOCK_NAME)
    print(f"  created test clock {clock['id']} frozen {CLOCK_LOOKBACK_DAYS} days ago")
    _remember_clock(clock["id"])
    return clock["id"]


def _remember_clock(clock_id: str) -> None:
    """Write STRIPE_TEST_CLOCK into .env so the MCP server reads the same scope."""
    env_path = pathlib.Path(".env")
    if not env_path.exists():
        print(f"  NOTE: .env not found - set STRIPE_TEST_CLOCK={clock_id} yourself")
        return

    lines = env_path.read_text(encoding="utf-8").splitlines()
    entry = f"STRIPE_TEST_CLOCK={clock_id}"
    if any(line.startswith("STRIPE_TEST_CLOCK=") for line in lines):
        lines = [
            entry if line.startswith("STRIPE_TEST_CLOCK=") else line for line in lines
        ]
    else:
        lines.append(entry)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote STRIPE_TEST_CLOCK={clock_id} to .env (restart the MCP server)")


def _reset_previous_demo_invoices() -> int:
    voided = 0
    for invoice in stripe.list_open_invoices(limit=100):
        if (invoice.get("metadata") or {}).get("businessflow_demo") == "true":
            stripe.void_invoice(invoice["id"])
            voided += 1
    return voided


def _find_customer_by_name_email(name: str, email: str) -> dict | None:
    wanted_name = (name or "").strip().lower()
    wanted_email = (email or "").strip().lower()
    for customer in stripe.list_customers(limit=100):
        same_name = (customer.get("name") or "").strip().lower() == wanted_name
        same_email = (customer.get("email") or "").strip().lower() == wanted_email
        if same_name and same_email:
            return customer
    return None


def _get_or_create_customer(name: str, email: str, clock_id: str) -> str:
    key = name.split()[0].lower()
    handle = os.environ.get(f"DEMO_CUSTOMER_{key.upper()}_ID")
    if handle:
        print(f"  reusing {name} ({handle})")
        return handle

    existing = _find_customer_by_name_email(name, email)
    if existing:
        # A customer that is not on the clock cannot hold back-dated invoices, so
        # reusing one would fail later with a confusing Stripe validation error.
        if existing.get("test_clock") != clock_id:
            raise SystemExit(
                f"{name} already exists ({existing['id']}) but is not attached to the "
                f"demo test clock {clock_id}. Delete that customer, or set "
                f"DEMO_CUSTOMER_{key.upper()}_ID to a customer that is attached."
            )
        print(f"  reusing existing {name} ({existing['id']})")
        return existing["id"]

    customer = stripe.create_customer(name=name, email=email, test_clock=clock_id)
    print(f"  created {name} ({customer['id']})")
    return customer["id"]


def _create_invoice(
    customer_id: str, amount_minor: int, description: str, due_in_days: int
) -> dict:
    stripe.create_invoice_item(customer_id, amount_minor, description=description)
    invoice = stripe.create_invoice(
        customer_id, due_date=_unix(due_in_days), metadata=DEMO_TAG
    )
    return stripe.finalize_invoice(invoice["id"])


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
    clock_id = _get_or_create_clock()
    # Scope the rest of this run (customer lookup, invoice reset) to the clock.
    os.environ["STRIPE_TEST_CLOCK"] = clock_id

    voided = _reset_previous_demo_invoices()
    if voided:
        print(f"  voided {voided} invoice(s) from a previous run")

    customers = {
        key: _get_or_create_customer(**details, clock_id=clock_id)
        for key, details in DEMO_CUSTOMERS.items()
    }

    for customer_key, amount, description, due_in_days in DEMO_INVOICES:
        invoice = _create_invoice(customers[customer_key], amount, description, due_in_days)
        print(
            f"  {invoice.get('number')}  {rules.format_money(amount, invoice.get('currency'))}"
            f"  due in {due_in_days} days"
        )

    # Report what the agent will actually say, straight from the same code path
    # the tools use — if this sentence is wrong, the demo is wrong.
    acme_invoices = stripe.list_customer_invoices(customers["acme"])
    summary = rules.summarize_overdue(acme_invoices)
    print()
    print("Done. The agent will answer:")
    print(f'  "Does Acme have anything overdue?"  ->  {messages.spoken_overdue_summary("Acme Corp", summary)}')
    print('  "How are we doing this month?"      ->  account-wide totals')
    print('  "Anything late for Globex?"         ->  nothing overdue')


if __name__ == "__main__":
    main()
