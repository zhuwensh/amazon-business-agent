# Architecture

BusinessFlow Agent is a self-hosted MCP server that exposes business operations as
tools, plus two clients: an agent loop and a browser-based simulated Alexa+
experience.

## System

```mermaid
flowchart TB
    subgraph Clients["MCP clients"]
        SIM["web_demo/<br/>simulated Alexa+ front end<br/>voice in / voice out"]
        CLI["agent/agent.py<br/>CLI"]
    end

    subgraph Agent["Agent layer"]
        LOOP["agent loop<br/>plan -> call tool -> observe -> speak"]
        LLM[("LLM<br/>OpenAI-compatible or Bedrock")]
    end

    subgraph MCP["MCP server (self-hosted)"]
        SRV["mcp_server/server.py<br/>FastMCP, Streamable HTTP"]
        RULES["business_rules.py<br/>overdue maths, matching"]
        MSG["messages.py<br/>voice-friendly phrasing"]
    end

    subgraph Ext["External services"]
        STRIPE[(Stripe API<br/>test mode)]
        SLACK[(Slack incoming webhook)]
    end

    SIM --> LOOP
    CLI --> LOOP
    LOOP --> LLM
    LOOP -->|streamable HTTP| SRV
    SRV --> RULES
    SRV --> MSG
    SRV --> STRIPE
    SRV --> SLACK
```

## Why the split

**Business logic is not in the LLM prompt.** `business_rules.py` owns overdue
detection, money maths and customer matching so those can be unit-tested with no
network, no Stripe key and no model in the loop. The agent decides *which* tool to
call and *in what order*; it does not do arithmetic.

**Voice shaping is a first-class layer.** `messages.py` turns a tool result into a
speakable sentence. A dashboard wants the full JSON; a voice assistant wants
"Acme has two overdue invoices totalling $3,200.00, the oldest 18 days overdue."
Every tool returns both: structured data under `data`, and the spoken line under
`spoken`.

**The MCP server is the only thing that talks to Stripe and Slack.** Both clients
(simulator and CLI) are MCP clients. That is what makes the integration reusable
and keeps the demo honest — the same server would be reachable from any other MCP
host.

## Tool set

| Tool | Kind | Purpose |
|---|---|---|
| `find_customer` | read | Resolve a spoken name to a customer (fuzzy match, returns candidates) |
| `get_overdue_invoices` | read | Overdue invoices for a customer, with amounts, days overdue and payment links |
| `get_cashflow_summary` | read | Workspace-wide outstanding / overdue totals |
| `send_payment_reminder` | write | Email the customer their invoice (Stripe `invoices/{id}/send`) |
| `notify_finance_team` | write | Post the outcome to the finance Slack channel |

Read tools are safe to call unprompted. Write tools are only called after the user
confirms, because the agent's system prompt requires it and because a spoken
assistant that sends customer email on inference would not be shippable.

## Protocol compliance

The Alexa+ track requires a self-hosted MCP server on spec **2025-11-25 or later**
using **Streamable HTTP**.

| Requirement | Implementation | Evidence |
|---|---|---|
| Protocol 2025-11-25+ | pinned `mcp==1.28.1` | that release declares `LATEST_PROTOCOL_VERSION = "2025-11-25"` and `SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]` |
| Streamable HTTP | `server.py` runs `FastMCP.run(transport="http", ...)` | FastMCP's `http` transport is Streamable HTTP; clients connect at `http://<host>:8000/mcp` |
| MCP client in-repo | `mcp.client.streamable_http.streamablehttp_client` | used by both `agent/agent.py` and `web_demo/app.py` |

## Request flow (multi-step action)

```mermaid
sequenceDiagram
    participant U as User (voice)
    participant S as Simulator
    participant A as Agent loop
    participant M as MCP server
    participant St as Stripe
    participant Sl as Slack

    U->>S: "Does Acme have anything overdue?"
    S->>A: transcript text
    A->>M: find_customer("Acme")
    M-->>A: candidate customers
    A->>M: get_overdue_invoices(customer_id)
    M->>St: GET /v1/invoices?customer=...
    St-->>M: invoices
    M-->>A: overdue list + spoken summary
    A-->>S: "Acme has two overdue invoices..."
    U->>S: "Send them a reminder and tell finance"
    A-->>S: confirmation prompt (write action)
    U->>S: "Yes"
    A->>M: send_payment_reminder(invoice_id)
    M->>St: POST /v1/invoices/{id}/send
    A->>M: notify_finance_team(...)
    M->>Sl: webhook post
    A-->>S: "Reminder sent and #finance notified."
```

## Security

| Topic | Approach |
|---|---|
| Secrets | `.env` only, git-ignored; `.env.example` ships with placeholders |
| Stripe | test mode (`sk_test_...`) for the demo; the server warns on non-test keys |
| Slack | incoming webhook URL, no OAuth token and no workspace-wide scope |
| MCP endpoint | binds `127.0.0.1` by default; expose deliberately behind a reverse proxy |
| Write actions | gated behind explicit user confirmation in the agent loop |
