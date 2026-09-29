"""Pure business logic: overdue detection, money maths, customer matching.

Standard library only, on purpose. The agent decides *which* tool to call; the
arithmetic and the matching rules live here so they can be unit-tested with no
network, no Stripe key and no model in the loop.
"""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Sequence

# Stripe expresses amounts in the smallest currency unit. For these currencies the
# smallest unit *is* the whole unit, so no /100 and no decimals.
ZERO_DECIMAL_CURRENCIES = frozenset(
    {
        "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg",
        "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
    }
)

CURRENCY_SYMBOLS = {"usd": "$", "eur": "\u20ac", "gbp": "\u00a3", "jpy": "\u00a5", "cny": "\u00a5"}

# Legal suffixes stripped before comparing a spoken name to a stored one, so
# "Acme" still matches "Acme Corp".
LEGAL_SUFFIXES = (
    "incorporated", "corporation", "limited", "company",
    "inc", "llc", "ltd", "corp", "co", "gmbh", "pte", "plc", "sa", "ag", "bv",
)

OPEN_STATUSES = frozenset({"open"})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_datetime(when: datetime | int | float | None) -> datetime:
    """Accept a datetime or a Unix timestamp and normalise to aware UTC."""
    if when is None:
        return utcnow()
    if isinstance(when, (int, float)):
        return datetime.fromtimestamp(float(when), tz=timezone.utc)
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def minor_to_decimal(amount_minor: int | None, currency: str = "usd") -> Decimal:
    """Convert a Stripe minor-unit amount to a displayable decimal."""
    value = Decimal(int(amount_minor or 0))
    if (currency or "usd").lower() in ZERO_DECIMAL_CURRENCIES:
        return value
    return (value / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_money(amount_minor: int | None, currency: str = "usd") -> str:
    """Format a minor-unit amount for display, e.g. 320000 -> '$3,200.00'."""
    code = (currency or "usd").lower()
    value = minor_to_decimal(amount_minor, code)
    body = f"{value:,.0f}" if code in ZERO_DECIMAL_CURRENCIES else f"{value:,.2f}"
    symbol = CURRENCY_SYMBOLS.get(code)
    return f"{symbol}{body}" if symbol else f"{code.upper()} {body}"


def amount_due_minor(invoice: dict[str, Any]) -> int:
    """Outstanding amount on an invoice, tolerating Stripe's field variations."""
    for key in ("amount_due", "amount_remaining", "total"):
        value = invoice.get(key)
        if value is not None:
            return int(value)
    return 0


# ---------------------------------------------------------------------------
# Overdue detection
# ---------------------------------------------------------------------------


def days_overdue(due_date: int | float | None, now: datetime | int | float | None = None) -> int:
    """Whole days past the due date. 0 when there is no due date, negative if early."""
    if not due_date:
        return 0
    delta = _as_datetime(now) - _as_datetime(due_date)
    return delta.days


def is_overdue(invoice: dict[str, Any], now: datetime | int | float | None = None) -> bool:
    """An invoice is overdue when it is still open and its due date has passed."""
    if (invoice.get("status") or "").lower() not in OPEN_STATUSES:
        return False
    due = invoice.get("due_date")
    if not due:
        return False
    return days_overdue(due, now) > 0


def select_overdue(
    invoices: Iterable[dict[str, Any]], now: datetime | int | float | None = None
) -> list[dict[str, Any]]:
    """Overdue invoices, oldest first."""
    overdue = [inv for inv in invoices if is_overdue(inv, now)]
    return sorted(overdue, key=lambda inv: inv.get("due_date") or 0)


def summarize_overdue(
    invoices: Iterable[dict[str, Any]], now: datetime | int | float | None = None
) -> dict[str, Any]:
    """Aggregate an invoice collection into the shape the tools and messages need."""
    invoices = list(invoices)
    overdue = select_overdue(invoices, now)

    totals: dict[str, int] = {}
    for inv in overdue:
        code = (inv.get("currency") or "usd").lower()
        totals[code] = totals.get(code, 0) + amount_due_minor(inv)

    single_currency = next(iter(totals)) if len(totals) == 1 else None
    oldest_days = max((days_overdue(inv.get("due_date"), now) for inv in overdue), default=0)

    return {
        "count": len(overdue),
        "oldest_days": oldest_days,
        "currency": single_currency,
        "total_minor": totals[single_currency] if single_currency else None,
        "totals_by_currency": totals,
        "invoices": overdue,
    }


def invoice_reference(invoice: dict[str, Any]) -> str:
    """Human-facing invoice reference: the number if Stripe assigned one."""
    return str(invoice.get("number") or invoice.get("id") or "unknown")


# ---------------------------------------------------------------------------
# Customer matching
# ---------------------------------------------------------------------------


def normalize_name(name: str | None) -> str:
    """Lowercase, strip punctuation and legal suffixes, collapse whitespace."""
    text = (name or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [tok for tok in text.split() if tok]
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def match_customers(
    query: str, customers: Sequence[dict[str, Any]], limit: int = 5, threshold: float = 0.55
) -> list[dict[str, Any]]:
    """Rank stored customers against a spoken name.

    Returns candidates with a `match_score` between 0 and 1, best first. An exact
    match scores 1.0, which lets a caller skip disambiguation entirely.
    """
    wanted = normalize_name(query)
    wanted_email = (query or "").strip().lower()
    if not wanted and not wanted_email:
        return []

    ranked: list[dict[str, Any]] = []
    for customer in customers:
        name = customer.get("name") or customer.get("description") or ""
        haystack = normalize_name(name)
        email = (customer.get("email") or "").lower()

        score = difflib.SequenceMatcher(None, wanted, haystack).ratio() if haystack else 0.0
        if wanted and haystack:
            if wanted == haystack:
                score = 1.0
            elif wanted in haystack or haystack in wanted:
                score = max(score, 0.9)
        if wanted_email and wanted_email == email:
            score = 1.0

        if score >= threshold:
            ranked.append({**customer, "display_name": name, "match_score": round(score, 3)})

    ranked.sort(key=lambda item: item["match_score"], reverse=True)
    return ranked[:limit]


def customer_display_name(customer: dict[str, Any] | None) -> str:
    if not customer:
        return "that customer"
    return customer.get("name") or customer.get("description") or customer.get("email") or customer.get("id") or "that customer"
