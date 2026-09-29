# Demo Script

Target length: **2:30**. Judges are not required to watch past 3 minutes, so the
multi-step action has to land early.

Everything spoken in the video should be real interaction with the running
simulator — no mockups.

## Before recording

1. Seed the Stripe **test** account so the numbers are stable:

   ```bash
   python -m demo.seed_test_data
   ```

   This creates `Acme Corp` with two overdue invoices and one current invoice.

2. Start the MCP server, then the simulator:

   ```bash
   python -m mcp_server.server        # terminal 1 — :8000/mcp
   python -m web_demo.app             # terminal 2 — :8080
   ```

3. Open `http://127.0.0.1:8080`, confirm the header shows the MCP server as
   connected, and check that the tool trace panel is visible.

## Scene 1 — the question (0:00-0:25)

Speak into the simulator:

> "Does Acme have anything overdue?"

While it runs, point at the trace panel: `find_customer` then
`get_overdue_invoices`. Say the point out loud — *the agent chose those tools and
that order; nothing was hard-coded.*

## Scene 2 — the answer (0:25-0:45)

The agent speaks:

> "Acme Corp has two overdue invoices totalling $3,200.00. The oldest is 18 days
> overdue."

Show the invoice list in the UI: numbers, amounts, due dates, payment links.

## Scene 3 — the multi-step action (0:45-1:45)

> "Send them a reminder and notify our finance team."

The agent asks for confirmation first. Say "yes". It then calls
`send_payment_reminder` and `notify_finance_team` in sequence.

Cut to the Slack window and show the message arriving in #finance. This is the
proof that the workflow crossed two systems.

## Scene 4 — the confirmation (1:45-2:05)

The agent speaks:

> "I sent Acme Corp a payment reminder for INV-0042, and notified #finance."

## Scene 5 — what it is (2:05-2:30)

Show the architecture diagram and close on the one-line positioning:

> A self-hosted MCP server that turns a spoken request into a payment workflow
> across Stripe and Slack — checkpointed, confirmed, and reported back.

Mention two things judges are scoring:

- the repo contains the MCP server, the agent loop and the simulator — all three
  run locally;
- write actions require confirmation, so the agent is safe to hand a real
  workspace.

## Recording notes

- Record the simulator at a readable zoom; the trace panel is the differentiator.
- If the browser's speech recognition is unavailable, type the same sentences and
  say so on camera once. The MCP and agent behaviour is unchanged.
- Keep the Slack window side by side with the simulator so the cross-system step
  is undeniable.
