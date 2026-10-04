# UAT case list

Acceptance tests for ChaseLine, written so that someone who did not build
it can run them. The **Covered by** column says what already guards each case
automatically; anything marked `manual` is a human check.

## Before you start

| Step | What to do |
|---|---|
| Install | `pip install -r requirements.txt` (this repo ships a `.venv`) |
| Configure | `.env` with `STRIPE_API_KEY` (test mode), `SLACK_WEBHOOK_URL`, Bedrock credentials |
| Seed | `python -m demo.seed_test_data` - creates the test clock and the overdue invoices |
| Run | `run_all.bat`, or `python -m mcp_server.server` and `python -m web_demo.app` |
| Open | http://127.0.0.1:8080 in **Chrome or Edge** (speech recognition is unavailable elsewhere) |

Start each case from a fresh session: press the reset control in the simulator, or
open a new browser tab (each tab is a separate conversation).

Legend: **P1** must pass before submitting, **P2** should pass, **P3** is polish.
Coverage: `auto` = the offline suite or the smoke test asserts it, `manual` = human
eyes only.

## 1. Setup and environment

| ID | P | Steps | Expected | Covered by |
|---|---|---|---|---|
| UAT-01 | P1 | `python -m demo.seed_test_data` | Three customers and their invoices created; `STRIPE_TEST_CLOCK` written to `.env`; exit code 0 | manual |
| UAT-02 | P2 | Run the seeder twice | Previous run is voided first: fresh invoice numbers, no duplicates | manual |
| UAT-03 | P1 | Double-click `run_all.bat` | Two consoles open, one per port; browser opens on :8080; the page header reads "MCP connected - 5 tools" | manual |
| UAT-04 | P2 | Close one console, then run `run_all.bat` again | The port still in use is reused, not started twice | manual |

## 2. MCP protocol contract

| ID | P | Steps | Expected | Covered by |
|---|---|---|---|---|
| UAT-05 | P1 | `python scripts/smoke_test.py` | `PASS: session initialized, protocol 2025-11-25` | auto |
| UAT-06 | P1 | `GET /api/health` | `connected: true` and exactly the five tool names | auto (smoke lists tools) |
| UAT-07 | P2 | Start the server with `MCP_HTTP` unset | Falls back to stdio, so another MCP host can use it | manual |
| UAT-08 | P2 | `netstat -ano` and look at :8000 | Listening on 127.0.0.1 only, never 0.0.0.0 | manual |

## 3. Read-only flows

| ID | P | Steps | Expected | Covered by |
|---|---|---|---|---|
| UAT-10 | P1 | Ask "Does Acme have anything overdue?" | States the answer: two invoices, $3,200.00, oldest 23 days. Does **not** ask "is that the one?" - a single confident match must not trigger a needless question | auto |
| UAT-11 | P2 | Ask "Does the globex people have anything overdue?" and repeat with a typo such as "Acmé" | Resolves to the intended customer without asking, since the score is decisive | auto |
| UAT-12 | P2 | Seed two similarly named customers, then ask about that name | Asks which one is meant. Never guesses between two real companies | manual |
| UAT-13 | P1 | Ask "Which invoices are overdue for Acme?" | Invoice **numbers**, amounts and ages. No ids, no timestamps, no JSON | manual |
| UAT-14 | P1 | Ask "Does Globex owe anything?" | "Globex Corporation has nothing overdue." and no offer to chase | auto + manual |
| UAT-15 | P1 | Ask "Show me every customer whose invoice is overdue" | Names each customer with what they owe, e.g. "Three are overdue, totalling $3,800.00: Acme Corp owes $3,200.00 and Initech LLC owes $600.00". Customers with nothing overdue are absent | auto (phrasing) + manual (live) |
| UAT-16 | P2 | Ask "How much is outstanding overall?" | Open invoice count, outstanding and overdue totals, age of the oldest | manual |
| UAT-17 | P2 | Point the tools at an account with two currencies | Reports each currency separately; never adds USD to JPY | auto |
| UAT-18 | P3 | Ask for the detail of one invoice | Number, amount, days overdue; still no ids | manual |

## 4. Confirmation gate - the safety contract

| ID | P | Steps | Expected | Covered by |
|---|---|---|---|---|
| UAT-20 | P1 | "Send Acme a reminder" | Says what it is about to do and to whom, and waits. Nothing is sent | manual |
| UAT-21 | P1 | Then answer "yes" | Reminder is sent; the reply names customer, invoice number and amount; `invoice.sent` appears in Stripe events | manual |
| UAT-22 | P1 | Say "tell finance" | Asks first. Nothing is posted | manual |
| UAT-23 | P1 | Then answer "yes" | The message appears in the channel the webhook points at; the reply confirms it | manual |
| UAT-24 | P1 | Answer "no" instead | Acknowledges and stops. Does not re-ask in the same turn | manual |
| UAT-25 | P1 | Call `send_payment_reminder` and `notify_finance_team` directly with `confirmed=false`, with no agent in the loop | Both refuse and return a confirmation question. This is the proof the gate is server-side, not prompt-side | auto (smoke test) |
| UAT-26 | P2 | Start a fresh session, then say "yes" with no prior request in it | Nothing happens - agreement does not carry across sessions | manual |
| UAT-27 | P2 | Ask it to void an invoice, issue a refund, or change a price | Says what it can do instead. Does not improvise a tool or claim success | manual |

## 5. Voice behaviour and the front end

| ID | P | Steps | Expected | Covered by |
|---|---|---|---|---|
| UAT-30 | P1 | Tap the orb, ask a question out loud (Chrome or Edge) | Transcript appears, answer is spoken and written once | manual |
| UAT-31 | P1 | Listen to every answer in this list | No ids, no field names, no timestamps, no raw error codes are ever read out | manual |
| UAT-32 | P2 | Listen to the length of the answers | One or two sentences, no bullet lists read aloud | manual |
| UAT-33 | P2 | Talk over the assistant while it is speaking | It stops speaking and starts listening again | manual |
| UAT-34 | P2 | Cover the microphone and mumble | "I did not catch that" plus a one-tap retry | manual |
| UAT-35 | P1 | Watch the latency pill on a simple read question | Shows the elapsed seconds; a one-customer read stays in single digits | manual |
| UAT-36 | P3 | Open the page in a browser without speech recognition | Falls back to the type-instead box instead of failing silently | manual |
| UAT-37 | P1 | Ask who owes money, then follow with "send them a reminder" | Resolves "them" from the conversation; does not ask for the customer name again | manual |

## 6. Multi-action turns and the turn budget

These are the paths that used to fail silently, so they carry the most weight.

| ID | P | Steps | Expected | Covered by |
|---|---|---|---|---|
| UAT-40 | P1 | "Chase Acme and tell finance", then confirm | Both actions happen, and the reply reports both | manual |
| UAT-41 | P1 | "Chase both and send it to the channel", then confirm | Either both customers are handled, or the reply says exactly what was done and what is left. It must never report nothing after a write went out | manual |
| UAT-42 | P1 | Force a turn past its budget (a request needing many steps) | The reply lists the actions that completed and says it stopped there, rather than discarding them | auto |
| UAT-43 | P2 | Make a write fail repeatedly with the same arguments | The turn stops early instead of spending every remaining round on it | auto |
| UAT-44 | P1 | Point `SLACK_WEBHOOK_URL` at a URL that is not a webhook, then confirm a finance post | The assistant reports that Slack refused the post. It must not claim success - a non-webhook path answers HTTP 200 with an HTML page | manual (verified by hand, no automated test yet) |
| UAT-45 | P1 | After any write, check Stripe events and the channel | What the assistant said matches what actually happened, one to one | manual |

## 7. Errors and recovery

| ID | P | Steps | Expected | Covered by |
|---|---|---|---|---|
| UAT-50 | P1 | Remove `STRIPE_API_KEY` and restart | A plain-language configuration message, not a stack trace | auto (error unwrapping) + manual |
| UAT-51 | P1 | Break the Bedrock credentials in `.env` | An actionable message naming the credential or region; no traceback read aloud | manual |
| UAT-52 | P2 | Break the Slack webhook and run a chase | The failure is spoken plainly, and the earlier reminder is still reported as sent | manual |
| UAT-53 | P2 | Break the Stripe key mid-session | The turn explains what failed; the MCP server stays up and the next turn still answers | manual |
| UAT-54 | P2 | Trigger an answer containing a currency symbol such as ¥ | The server keeps running - this is the cp932 console regression | auto (startup path) + manual |
| UAT-55 | P2 | Stop the MCP server while the simulator is open | The page reports it is not connected instead of spinning forever | manual |

## 8. Data, secrets and submission hygiene

| ID | P | Steps | Expected | Covered by |
|---|---|---|---|---|
| UAT-60 | P1 | `git status` and a search of the tree for keys | `.env` and `.aws` are untracked; no key, webhook or secret appears in any committed file | manual |
| UAT-61 | P1 | Inspect the Stripe key in use | Test mode (`sk_test_`), and the server warns if it is not | manual |
| UAT-62 | P2 | Compare a tool result with the Stripe dashboard | Reads are scoped to the test clock, so the numbers agree | manual |
| UAT-63 | P2 | Skim every transcript captured today | No customer id, invoice id or session identifier was spoken aloud | manual |

## Coverage summary

| Area | Cases | Automated |
|---|---|---|
| Setup and environment | 4 | 0 |
| MCP protocol contract | 4 | 2 |
| Read-only flows | 9 | 5 |
| Confirmation gate | 8 | 1 |
| Voice and front end | 8 | 0 |
| Multi-action and turn budget | 6 | 2 |
| Errors and recovery | 6 | 2 |
| Hygiene | 4 | 0 |
| **Total** | **49** | **12** |

The offline suite (`python -m unittest discover -s tests`, 46 tests) and
`python scripts/smoke_test.py` are the automated half. Everything else needs a
person, a browser and a channel to watch.

## Known gaps at the time of writing

Carried from the handoff, so nobody mistakes these for passes:

| Gap | Effect on UAT |
|---|---|
| Voice input has never been exercised from a browser | UAT-30, UAT-33, UAT-34 are unverified end to end |
| The simulator has no automated test | Section 5 is manual by definition |
| Only one Bedrock model has been verified | A model swap invalidates UAT-10 to UAT-18 for that model |
| Slack body verification has no unit test | UAT-44 stays manual until one exists |
| Demo data ages | Re-seed before a recorded run, or UAT-10 numbers drift |
| `SLACK_FINANCE_CHANNEL` is a display label | UAT-23 must be checked in the channel the webhook actually points at |
