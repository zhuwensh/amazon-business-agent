# BusinessFlow Agent — handoff

_Updated 2026-09-30 · HEAD `127e7ec` "Add the Devpost answers and a submission checklist"_

This is the working handoff: what the system is, where the seams are, what was
built, and what is still open. It is also the submission repository for the
**Amazon Developer Hackathon 2026, Alexa+ track** — the submission text lives in
[docs/DEVPOST_SUBMISSION.md](docs/DEVPOST_SUBMISSION.md) and the outstanding work in
[docs/SUBMISSION_CHECKLIST.md](docs/SUBMISSION_CHECKLIST.md).

## What it is

A self-hosted MCP server that turns a spoken business request into a multi-step
workflow across Stripe and Slack: find the customer, read what is overdue, say it
in one sentence, then — only after the user agrees — email the customer a reminder
and notify the finance channel.

Three parts, and the split is the point:

| Part | Path | Role |
|---|---|---|
| MCP server | `mcp_server/` | five business-level tools over Streamable HTTP; the only thing that talks to Stripe and Slack |
| Agent loop | `agent/` | decides which tool to call and in what order; runs on Amazon Bedrock |
| Simulated Alexa+ front end | `web_demo/` | voice-first stand-in for the gated Alexa+ Web Simulator |
| Agent Skill | `skills/cash-collection/` | the track's other sanctioned artifact: the conduct, not the capability |

Five load-bearing rules:

1. **Consequential actions are gated in the tool, not the prompt.**
   `send_payment_reminder` and `notify_finance_team` refuse to run without
   `confirmed=true`. Prompt instructions are advisory; this is a guarantee.
2. **Business arithmetic never goes through the model.** `business_rules.py` is
   stdlib-only and unit-tested with no network and no model.
3. **Every tool returns `data` and `spoken`.** The same result has to serve a
   dashboard and a voice assistant; `messages.py` owns the phrasing.
4. **Stripe reads are scoped to a test clock** when `STRIPE_TEST_CLOCK` is set.
   Unset, they read normally.
5. **Model output is normalised before it is trusted.** See `clean_tool_name` in
   `agent/agent.py` — the reason is not obvious, and it is in "Recent changes".

## Run it

| What | Command |
|---|---|
| MCP server | `python -m mcp_server.server` → `http://127.0.0.1:8000/mcp` |
| Simulator | `python -m web_demo.app` → `http://127.0.0.1:8080` (`WEB_PORT`) |
| Agent, one turn | `python -m agent.agent "Does Acme have anything overdue?"` |
| Offline tests | `python -m unittest discover -s tests -v` — 31 tests, no network |
| End-to-end smoke test | `python scripts/smoke_test.py` (add `SMOKE_TEST_SLACK=1` to post for real) |
| Bedrock configuration check | `python scripts/check_bedrock.py` — three steps, the third is tool calling |
| Refresh demo data | `python -m demo.seed_test_data` |

Everything reads `.env` through `mcp_server.config.bootstrap()`. **Restart the
server after an `.env` change** — nothing re-reads it live.

Status at this handoff: 31 offline tests pass; the smoke test passes end to end;
the agent has been run against Bedrock and completed the full three-turn workflow,
with a real Stripe reminder and a real Slack message.

## Where to look

| Step | File |
|---|---|
| Overdue maths, ageing, money, fuzzy customer matching | `mcp_server/business_rules.py` |
| Spoken phrasing for every tool result | `mcp_server/messages.py` |
| Stripe reads, the write, test-clock scoping | `mcp_server/stripe_tools.py` |
| Slack webhook | `mcp_server/slack_tools.py` |
| The five tools, and the confirmation gate | `mcp_server/server.py` |
| `.env` loading, console encoding | `mcp_server/config.py` |
| Agent loop, tool-name normalisation | `agent/agent.py` |
| System prompt: voice rules, confirmation rule | `agent/prompts.py` |
| OpenAI-compatible and Bedrock backends, error unwrapping | `agent/llm.py` |
| Voice-first UI: states, barge-in, retry, latency | `web_demo/static/app.js` |
| Demo scenario, test clock, reset-on-rerun | `demo/seed_test_data.py` |

## Recent changes

Everything below was found by running the thing, not by reading it.

### 1. `.env` was never loaded (`aeb4c46`, `ff196c2`)

The README told people to copy `.env.example` to `.env`; the code only ever read
`os.environ`. Now every entry point calls `bootstrap()`. If you add an entry point,
call it too.

### 2. A currency symbol could kill the process (`ff196c2`)

Windows consoles here default to cp932. A `print` containing `¥` or an em dash
raised `UnicodeEncodeError` and took the MCP server down *before it bound a port* —
which looks like a network problem, not an encoding one. Banner text is ASCII now
and `prepare_console()` makes stdout forgiving.

### 3. Overdue invoices cannot be created directly on a fresh Stripe account (`251cfd2`)

Stripe rejects a due date in the past on create **and** on update, so an empty test
account cannot be given an overdue invoice at all. The supported route is a test
clock frozen in the past — but clock objects are invisible to the account-wide list
endpoints: `GET /v1/customers` accepts a `test_clock` filter, `GET /v1/invoices`
does not accept one and does not return them either. So `list_open_invoices()`
collects per customer when a clock is configured.

`demo/seed_test_data.py` creates the clock, writes `STRIPE_TEST_CLOCK` into `.env`,
and is re-runnable: it voids the previous run's invoices first. Test clocks hold at
most three customers, which is exactly what the scenario needs.

### 4. An explicit invoice creation produced an empty paid invoice (`251cfd2`)

Adding an invoice item makes Stripe create a draft invoice of its own, so a
following `POST /v1/invoices` produced a second, empty invoice that finalized as a
**zero-amount paid** one. Nothing errored. `create_invoice()` now passes
`pending_invoice_items_behavior=include`.

### 5. The assistant asked a question it had already answered (`801d27e`)

With one exact customer match, `find_customer` still returned a question — "I found
Acme Corp. Is that the one?" — so every request began with a needless confirmation.
`spoken_customer_found` now states the result for a single match and only asks when
the match is genuinely ambiguous. Unit tests and the smoke test both passed while
this was wrong; only a live conversation showed it.

### 6. gpt-oss control tokens poisoned the conversation (`6b42edb`)

gpt-oss returned a tool call named `notify_finance_team<|channel|>commentary` — its
own response format leaking into the name. Converse *accepts* that on the way out
and *rejects* it on the way back in, so once the bad name reached the history every
later request in that conversation failed with a name-pattern ValidationException.
One bad name ends the session, not the turn.

`clean_tool_name()` normalises names the moment they arrive — before history, before
the MCP server. Unknown names are answered with the list of real tools instead of
being forwarded, and an unsalvageable name ends the turn cleanly rather than
writing an invalid block into history. Regression tests: `tests/test_agent.py`.

### 7. Errors arrived as `unhandled errors in a TaskGroup` (`aeb4c46`)

Anything raised inside an MCP client session comes back wrapped in an anyio
ExceptionGroup, which is useless to a user. `describe_error()` unwraps it; the model
is resolved *before* the session opens, so a missing key reads as configuration
rather than a transport failure.

### 8. Bedrock: credential layout and a three-step check (`fd8c012`, `200e27f`)

`BedrockBackend` accepts `AWS_PROFILE`, `AWS_SHARED_CREDENTIALS_FILE` and
`BEDROCK_MODEL_ID`, following the SmartSales-AI project's layout so credentials can
live in the repo folder (`.aws/` is git-ignored). `scripts/check_bedrock.py`
verifies credentials, a plain Converse call, **and tool calling** — the last one
because an agent loop that never receives a `toolUse` block is not an agent.

## Open issues

| # | Issue | Status |
|---|---|---|
| 1 | Demo video not recorded | **open** — the largest remaining item; script is in `docs/DEMO_SCRIPT.md` |
| 2 | Voice input never exercised from a browser | **open** — only the page and its assets were verified from here |
| 3 | `SLACK_FINANCE_CHANNEL` is a display label only | **open by design** — the webhook decides the channel, and nothing can read it back |
| 4 | Open Source mini-challenge qualification | **undecided** — see `docs/SUBMISSION_CHECKLIST.md` |
| 5 | Demo data ages | known — re-run the seeder before recording |
| 6 | Simulator has no automated test | known — `app.js` is syntax-checked with `node --check`, nothing more |
| 7 | Only one Bedrock model verified | known — a `BEDROCK_MODEL_ID` swap is untested |
| 8 | No screenshots in the README | known — worth adding; the trace panel is the most persuasive image |
| 9 | CLI agent is one-shot | known — each invocation is a fresh session, so multi-turn needs the web API or a REPL |

## Before you ship

- Re-run `python -m demo.seed_test_data` — otherwise the ages drift a day per day.
- Record in **Chrome or Edge**; speech recognition is unavailable in Safari and
  Firefox, and the UI only reveals its "Type instead" fallback when it is missing.
- `.env` holds live test credentials for Stripe, AWS and Slack. It is git-ignored.
  Keep it that way, and keep it out of the video.
- Never put a second `AWS_REGION` line in `.env`. The last one wins, and the symptom
  is a bare `AccessDeniedException` that reads like a permissions bug.
- Change `AWS_REGION` and the IAM policy's model ARN must change with it.
- Adding or renaming a tool? Update `EXPECTED_TOOLS` in `scripts/smoke_test.py`, and
  remember `TOOL_NAME_PATTERN` in `agent/agent.py` normalises what the model sends.
- Touching the confirmation flow? The gate is `confirmed` inside the tool. Do not
  move it into the prompt.
- Running the smoke test with `SMOKE_TEST_SLACK=1` posts a real message.
