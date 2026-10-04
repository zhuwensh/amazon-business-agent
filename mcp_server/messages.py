"""Voice-friendly phrasing.

A dashboard wants the full JSON. A voice assistant wants one short sentence that
can be read aloud and understood without looking at a screen. This module is the
translation layer between them, kept separate so it can be unit-tested.
"""

from __future__ import annotations

from typing import Any, Sequence

from . import business_rules as rules

NUMBER_WORDS = {
    0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}


MAX_SPOKEN_CUSTOMERS = 3


def number_word(count: int) -> str:
    return NUMBER_WORDS.get(count, str(count))


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    if count == 1:
        return singular
    return plural_form or f"{singular}s"


def total_phrase(summary: dict[str, Any]) -> str:
    """Money phrase, handling the (rare) mixed-currency case honestly."""
    currency = summary.get("currency")
    if currency:
        return f"totalling {rules.format_money(summary.get('total_minor'), currency)}"
    totals = summary.get("totals_by_currency") or {}
    if not totals:
        return "with no outstanding balance"
    parts = [rules.format_money(amount, code) for code, amount in sorted(totals.items())]
    return "totalling " + " and ".join(parts)


def owed_phrase(entry: dict[str, Any]) -> str:
    """One customer debt in money form, for example "$3,200.00"."""
    currency = entry.get("currency")
    if currency:
        return rules.format_money(entry.get("total_minor"), currency)
    totals = entry.get("totals_by_currency") or {}
    if not totals:
        return "nothing"
    return " and ".join(rules.format_money(amount, code) for code, amount in sorted(totals.items()))


def _and_list(items: Sequence[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def spoken_cashflow_summary(
    open_invoice_count: int, summary: dict[str, Any], by_customer: Sequence[dict[str, Any]]
) -> str:
    """The sentence read aloud after `get_cashflow_summary`.

    Naming the customers is the point. A user cannot name a company they were
    never told about, so an account-wide answer that only reports totals leaves
    them with nowhere to go. Three names is as much as reads well aloud; the rest
    stay in `data` and in the follow-up question.
    """
    open_count = int(open_invoice_count or 0)
    overdue_count = int(summary.get("count") or 0)
    open_label = plural(open_count, "invoice")
    open_verb = plural(open_count, "is", "are")
    opens = f"{open_count} {open_label} {open_verb} open."
    if not overdue_count:
        return opens[:-1] + ", and nothing is overdue."

    overdue_verb = plural(overdue_count, "is", "are")
    # The count starts this sentence, so it is capitalised: "Three are overdue".
    sentence = f"{opens} {number_word(overdue_count).capitalize()} {overdue_verb} overdue, {total_phrase(summary)}"
    debts = [
        f"{entry.get('customer') or 'a customer'} owes {owed_phrase(entry)}" for entry in by_customer
    ]
    if not debts:
        return sentence + "."
    visible = debts[:MAX_SPOKEN_CUSTOMERS]
    hidden = len(debts) - len(visible)
    if hidden > 0:
        visible = visible + [f"{number_word(hidden)} more"]
    return sentence + ": " + _and_list(visible) + "."


def spoken_overdue_summary(customer_name: str, summary: dict[str, Any]) -> str:
    """The sentence read aloud after `get_overdue_invoices`."""
    count = int(summary.get("count") or 0)
    if count == 0:
        return f"{customer_name} has nothing overdue."

    oldest = int(summary.get("oldest_days") or 0)
    sentence = (
        f"{customer_name} has {number_word(count)} overdue "
        f"{plural(count, 'invoice')} {total_phrase(summary)}."
    )
    if count == 1:
        sentence += f" It is {oldest} {plural(oldest, 'day')} overdue."
    else:
        sentence += f" The oldest is {oldest} {plural(oldest, 'day')} overdue."
    return sentence


def spoken_disambiguation(candidates: Sequence[dict[str, Any]]) -> str:
    """Ask which customer was meant, without reading a list of ids aloud."""
    names = [rules.customer_display_name(c) for c in candidates[:3]]
    if not names:
        return "I could not find that customer."
    if len(names) == 1:
        return f"I found {names[0]}. Is that the one?"
    return f"I found more than one match: {' or '.join(names)}. Which one did you mean?"


def spoken_customer_found(candidates: Sequence[dict[str, Any]]) -> str:
    """A statement when the match is unambiguous; only ask when it is not.

    Asking "is that the one?" after an exact, single match makes the assistant
    hesitate on every request — the user said a name, and the name was found.
    """
    if not candidates:
        return "I could not find that customer."
    if len(candidates) == 1:
        return f"Found {rules.customer_display_name(candidates[0])}."
    return spoken_disambiguation(candidates)


def spoken_reminder_sent(
    customer_name: str, invoice_reference: str, amount_minor: int | None, currency: str | None
) -> str:
    amount = rules.format_money(amount_minor, currency or "usd")
    return f"I sent {customer_name} a payment reminder for {invoice_reference}, {amount}."


def spoken_finance_notified(channel: str) -> str:
    return f"and notified {channel}."


def spoken_action_summary(
    customer_name: str,
    invoice_reference: str,
    amount_minor: int | None,
    currency: str | None,
    channel: str,
) -> str:
    return (
        f"{spoken_reminder_sent(customer_name, invoice_reference, amount_minor, currency)} "
        f"{spoken_finance_notified(channel).capitalize()}"
    )


def overdue_detail_lines(summary: dict[str, Any]) -> list[str]:
    """One line per overdue invoice, for the text panel next to the voice answer."""
    lines = []
    for invoice in summary.get("invoices") or []:
        amount = rules.format_money(rules.amount_due_minor(invoice), invoice.get("currency"))
        days = rules.days_overdue(invoice.get("due_date"))
        lines.append(
            f"{rules.invoice_reference(invoice)} — {amount}, {days} {plural(days, 'day')} overdue"
        )
    return lines


# ---------------------------------------------------------------------------
# Slack payloads
# ---------------------------------------------------------------------------


def slack_overdue_text(
    customer_name: str, summary: dict[str, Any], heading: str = "Overdue invoices"
) -> str:
    lines = [f"*{heading} — {customer_name}*", spoken_overdue_summary(customer_name, summary)]
    for line in overdue_detail_lines(summary):
        lines.append(f"\u2022 {line}")
    return "\n".join(lines)


def slack_action_text(
    customer_name: str,
    invoice_reference: str,
    amount_minor: int | None,
    currency: str | None,
    note: str | None = None,
) -> str:
    amount = rules.format_money(amount_minor, currency or "usd")
    lines = [
        f"*Payment reminder sent — {customer_name}*",
        f"Invoice {invoice_reference} for {amount}.",
    ]
    if note:
        lines.append(note)
    return "\n".join(lines)
