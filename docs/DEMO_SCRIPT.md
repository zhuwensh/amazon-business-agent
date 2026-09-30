# Demo Script

Target length: **2:30**. Judges are not required to watch past 3 minutes, so the
multi-step action has to land early and the voice behaviour has to be visible.

Everything spoken in the video is a real interaction with the running simulator.

## Before recording

1. Seed the Stripe **test** account so the numbers are stable:

   ```bash
   python -m demo.seed_test_data
   ```

   This creates `Acme Corp` with two overdue invoices and one current invoice, plus
   `Initech LLC` and `Globex Corporation`. Re-running refreshes the ages, so run it
   immediately before recording.

2. Start the server, then the simulator, in two terminals:

   ```bash
   python -m mcp_server.server        # :8000/mcp
   python -m web_demo.app             # :8080
   ```

3. Open `http://127.0.0.1:8080` in **Chrome or Edge** — speech recognition is not
   available in Safari or Firefox. Check that the dot in the top-left is green and
   reads "MCP connected · 5 tools".

4. Open **How it works** (bottom right) so the tool trace stays in frame. It is the
   single most persuasive thing on screen: it shows the agent choosing tools,
   rather than following a script.

5. Say one throwaway sentence to the orb to confirm the microphone works.

## Scene 1 — the question (0:00-0:30)

Tap the orb — or hold the space bar — and speak:

> "Does Acme have anything overdue?"

While it runs, point at the trace: `find_customer`, then `get_overdue_invoices`.
Say the point out loud: *the agent chose those tools and that order; nothing was
hard-coded.*

Point at the "answered in X.X s" pill. A voice assistant that takes eight seconds
is not a voice assistant, so the number is on screen on purpose.

## Scene 2 — the answer (0:30-0:50)

The agent speaks:

> "Acme Corp has two overdue invoices totalling $3,200.00. The oldest is 18 days
> overdue."

Note what it does *not* do: no ids, no JSON, no field names. The caption on screen
is there for the viewer — the answer itself was written to be heard.

## Scene 3 — you can talk over it (0:50-1:10)

Ask a second question, then interrupt it:

> "How are we doing this month?" … (while it answers, tap the orb) … "Anything late
> for Globex?"

The assistant stops mid-sentence and starts listening. Say: *that is barge-in — a
screen-based assistant never needs it, a voice one cannot work without it.*

## Scene 4 — the multi-step action (1:10-2:05)

> "Send them a reminder and notify our finance team."

The agent asks before acting — it names the invoice, the amount and who gets
notified — then waits. Say "yes". It then calls `send_payment_reminder` and
`notify_finance_team` in sequence; both appear in the trace.

Cut to the Slack window and show the message arriving in the finance channel. This
is the proof that one spoken request crossed two systems.

## Scene 5 — the confirmation (2:05-2:20)

The agent speaks:

> "I sent Acme Corp a payment reminder for O3RSQJ1Z-0004, and notified #finance."

## Scene 6 — what it is (2:20-2:30)

Say the one-line positioning over the architecture diagram:

> A self-hosted MCP server — protocol 2025-11-25 over Streamable HTTP — that turns
> a spoken request into a payment workflow across Stripe and Slack, with an Agent
> Skill carrying the conduct.

## Recording notes

- Chrome or Edge only: the Web Speech API is the reason the simulator needs them.
  If recognition is unavailable the UI reveals "Type instead" — say so once, on
  camera, and carry on.
- Keep the Slack window visible beside the simulator so the cross-system step is
  undeniable.
- The Stripe account used here contains only synthetic demo data, so showing the
  dashboard is safe — it is worth one cutaway when the invoices are listed.
