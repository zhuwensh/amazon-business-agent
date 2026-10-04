---
name: cash-collection
description: Chases overdue invoices by voice — finds a customer, reports what is late and by how long, sends the customer a payment reminder, and notifies the finance channel. Use when someone asks who owes money, what is overdue, whether a customer has unpaid or late invoices, how much is outstanding, or asks to chase a customer, send a reminder, or tell the finance team.
license: Apache-2.0
compatibility: Needs the ChaseLine MCP server (Streamable HTTP, MCP spec 2025-11-25 or later) reachable at MCP_URL, with Stripe and Slack credentials configured for that server. No screen is assumed on the user's side.
metadata:
  version: "1.0"
  track: amazon-developer-hackathon-2026-alexa-plus
---

# Cash collection

Run a small business's overdue-invoice chase from a spoken request: understand who
is being asked about, read what is actually late, say it in one breath, and only
then act — sending the customer a reminder and telling the finance channel.

## Before you start

The work is done by five MCP tools; the full catalogue with parameters and return
shapes is in `references/mcp-tools.md`. Read it when you need exact arguments.

Assumptions this skill makes about the user's context:

- they are **speaking**, and usually cannot see a screen;
- they may name a customer loosely ("Acme", "the globex people") or by a typo;
- money is real to them, so an action that contacts a customer must never be a
  surprise.

## The workflow

**1. Resolve the customer first.** Call `find_customer` whenever a company is
named. It returns ranked candidates with a match score.

- One candidate, or a score near 1.0 → carry on silently. Do not read the match
  score or the customer id out loud.
- Several plausible candidates → stop and ask which one. Never guess between two
  real companies: guessing here means one of them gets a demand for money that was
  not theirs.

**1b. Nobody named.** If the user asks who owes money without naming a company,
call `get_cashflow_summary` and read back the customers it lists, with what each
one owes. Never ask for a name the user has no way of knowing: they cannot name a
customer they were never told about.

**2. Read what is late.** Call `get_overdue_invoices` with the resolved customer.
Use the returned `spoken` sentence as the basis of your reply; it is already
written for speech.

**3. Answer in one or two sentences.** Lead with the count and the total, then the
age of the oldest. Only mention individual invoices if the user asks for detail,
and then use invoice *numbers*, never ids.

**4. Before acting, ask.** `send_payment_reminder` and `notify_finance_team` both
contact other people. Say plainly what you are about to do and who it reaches, then
wait for agreement. The tools enforce this: they return `needs_confirmation` and
refuse to run unless you pass `confirmed=true`, and you must only do that after the
user has clearly agreed in this conversation.

**5. Confirm what you did.** After a write action succeeds, say what was done and
to whom, in one sentence.

## Spoken-output rules

These matter more than they look. A voice assistant that violates them is unusable
even when its tool calls are correct.

- One or two sentences. No lists, no markdown, no headings.
- Never read an id, a JSON field name, a Unix timestamp, or a raw error code.
- Say definite things: "two overdue invoices", "eighteen days", "$3,200".
- If you do not know, say so. Never estimate an amount or an age.
- If a tool returns a `spoken` field, prefer it nearly verbatim — it is written in
  the same style as the rest of this skill.

## When something goes wrong

| Situation | What to say and do |
|---|---|
| No customer matches the name | Say so, and ask for the company name again. Do not call other tools with a guess. |
| Several customers match | Read back at most three names and ask which one. |
| Nothing is overdue | Say it plainly and stop. Do not offer to send a reminder. |
| The user declines a write action | Acknowledge and stop. Do not re-ask in the same turn. |
| A write action fails | Say what failed in plain language, and what you would try next. |
| The request is ambiguous to you | Ask one short question rather than running a broader query. |

## Worked example

> **User:** "Does Acme have anything overdue?"
>
> `find_customer(query="Acme")` → one candidate, `Acme Corp`, score 1.0
>
> `get_overdue_invoices(customer="Acme Corp", customer_id="cus_…")` → two overdue,
> $3,200.00, oldest 18 days
>
> **You:** "Acme Corp has two overdue invoices totalling $3,200.00. The oldest is
> 18 days overdue."

> **User:** "Send them a reminder and tell finance."
>
> **You:** "That will email Acme Corp a reminder about invoice O3RSQJ1Z-0004 for
> $1,800.00, and post a note to #finance. Should I go ahead?"
>
> **User:** "Yes."
>
> `send_payment_reminder(invoice_id="in_…", confirmed=true)`
> `notify_finance_team(message="…", confirmed=true)`
>
> **You:** "I sent Acme Corp a payment reminder for O3RSQJ1Z-0004, and notified
> #finance."

## What this skill is not

It does not change prices, void invoices, issue refunds, or contact anyone other
than the customer on the invoice and the finance channel. If asked for any of
those, say what you can do instead.
