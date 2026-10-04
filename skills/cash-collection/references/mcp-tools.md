# BusinessFlow MCP tools

Reference for the `cash-collection` skill. Five tools, served by the BusinessFlow
MCP server over Streamable HTTP at `MCP_URL` (default
`http://127.0.0.1:8000/mcp`).

Every tool returns an object with:

| Field | Meaning |
|---|---|
| `ok` | whether the call succeeded |
| `data` | the structured result — for a screen, a dashboard, or a log |
| `spoken` | a sentence already phrased for a voice assistant |
| `needs_confirmation` | present and true when a write tool refused to run yet |

Prefer `spoken` for anything the user hears, and `data` when they ask for detail.

---

## `find_customer`

Resolve a spoken company name to a Stripe customer.

| Argument | Type | Notes |
|---|---|---|
| `query` | string | a name, part of a name, or an email |

Returns `data.candidates`, best first, each with `id`, `name`, `email` and
`match_score` (1.0 is an exact match on the normalised name or the email). Legal
suffixes are ignored, so "Acme" matches "Acme Corp", and small typos still match.

Use it before any customer-scoped tool. If the top score is below ~0.95 and there
is more than one candidate, ask the user which customer they meant.

---

## `get_overdue_invoices`

Overdue invoices for one customer, oldest first.

| Argument | Type | Notes |
|---|---|---|
| `customer` | string | the name the user said |
| `customer_id` | string, optional | pass it once the customer is confirmed, to skip matching |

Returns `data.count`, `data.total_minor`, `data.currency`, `data.oldest_days` and
`data.invoices[]`, each with `number`, `amount_minor`, `currency`, `due_date`,
`days_overdue` and `payment_link`.

"Overdue" means: still open, has a due date, and that date has passed.

---

## `get_cashflow_summary`

Account-wide totals, for questions like "how are we doing this month?" or
"who owes us money?" - including the customers behind the overdue balance.

| Argument | Type | Notes |
|---|---|---|
| `limit` | integer, optional | how many open invoices to consider (default 100) |

Returns `data.open_invoice_count`, `data.outstanding_by_currency`,
`data.overdue_count`, `data.overdue_by_currency`, `data.oldest_overdue_days` and
`data.overdue_by_customer` - one row per customer (`customer_id`, `customer`,
`overdue_count`, `oldest_days`, `currency`, `total_minor`,
`totals_by_currency`), largest debt first.

---

## `send_payment_reminder`

Email the customer their invoice. **Consequential — requires confirmation.**

| Argument | Type | Notes |
|---|---|---|
| `invoice_id` | string | the invoice to remind about |
| `confirmed` | boolean | defaults to false |

With `confirmed=false` it returns `needs_confirmation` and a `spoken` question you
can put to the user. With `confirmed=true` it asks Stripe to send the invoice and
returns the invoice number, customer, amount and payment link.

---

## `notify_finance_team`

Post a message to the finance Slack channel. **Consequential — requires
confirmation.**

| Argument | Type | Notes |
|---|---|---|
| `message` | string | the text to post |
| `confirmed` | boolean | defaults to false |

With `confirmed=false` it returns `needs_confirmation`. With `confirmed=true` it
posts through the configured incoming webhook and returns the channel it reached.

---

## Errors

A failed call returns `ok: false` with a human-readable `error` and the same text
in `spoken`. Say what failed in plain language; do not read out the raw message if
it mentions a status code or a parameter name.
