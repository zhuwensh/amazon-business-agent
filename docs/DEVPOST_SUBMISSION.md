# Devpost submission

Paste-ready answers for the submission form. Everything below is written to be
verifiable against the repository — no claim here should need to be taken on trust.

---

## Track and mini challenges

**Primary track:** Alexa+
**Mini challenges:** AWS Builder, Open Source

---

## Project description (paste into "About the project")

### Inspiration

Small businesses do not lose money because nobody knows what is overdue. They lose
it because chasing the money is a chore that happens after everything else. We
wanted to find out whether a *spoken* request could drive the whole chase — not
"ask a chatbot about invoices", but "say what you want and have it done".

So the test we set was deliberately narrow: someone says a sentence, and a payment
workflow happens across two systems without them touching a UI.

### What it does

Ask "Does Acme have anything overdue?" and the assistant finds the customer, reads
their invoices, works out what is late and by how long, and answers in one
sentence: *"Acme Corp has two overdue invoices totalling $3,200.00. The oldest is
18 days overdue."*

Then say "Send them a reminder and notify our finance team." It repeats back what
it is about to do and who it reaches, waits for agreement, and only then emails the
customer and posts to the finance channel — reporting what it did.

Consequential actions cannot fire by accident: the tools themselves refuse to run
until they are called with `confirmed=true`. The confirmation rule is enforced
server-side, not left to the model's good behaviour.

### How we built it

Three pieces, and the split is the point.

**A self-hosted MCP server** (`mcp_server/`) exposes five business-level tools over
Streamable HTTP: resolve a customer, read what is overdue, summarise the account,
send a reminder, notify finance. Business arithmetic — overdue detection,
ageing, fuzzy customer matching — lives in a module with no third-party imports at
all, so it is tested without a network or a model in the loop. Every tool returns
structured data *and* a sentence already phrased for speech, because the same
result has to serve a dashboard and a voice assistant.

**An agent loop** (`agent/`) runs on Amazon Bedrock — `openai.gpt-oss-20b-1:0`
through the Converse API with `toolConfig`. It decides which tools to call and in
what order. Conversation history is kept per session, so "send *them* a reminder"
resolves without repeating the customer's name.

**A voice-first front end** (`web_demo/`), because the Alexa+ add-on tooling is not
available to hackathon participants. It is not a chat box with a microphone
button: it has listening/thinking/speaking states, talking over it interrupts it
mid-sentence, a misheard request is recoverable in one tap, and the wait time is on
screen because a slow voice assistant is not a voice assistant.

We also ship an **Agent Skill** (`skills/cash-collection/`) — the track accepts an
MCP server *or* an Agent Skill, so we built both. The MCP server carries the
capability; the skill carries the conduct (when to stop and ask, how to phrase an
answer, what never to read aloud). Any skills-compatible host that can reach the
server inherits the same behaviour.

### Challenges we ran into

**The Alexa+ tools are gated with no application path.** The track description
invites builders to see what Preview partners are building; the FAQ says the
Category SDK, MCP Toolkit, CLI and Web Simulator are for select partners only, with
no way for participants to apply. So we designed to the add-on *contract* instead
of the add-on runtime, and wrote the constraint down rather than pretending
otherwise (see `FRICTION_LOG.md`).

**An overdue invoice cannot be created on a fresh Stripe test account.** Stripe
rejects a due date in the past on create *and* on update. The supported route is a
test clock — but clock objects are invisible to the account-wide list endpoints,
and `/v1/invoices` has no `test_clock` filter while `/v1/customers` does. The
seeder now builds the scenario on a test clock and the MCP server scopes its reads
to it, which means anyone who clones the repository can reproduce the demo data
exactly.

**The model leaked its own control tokens into a tool name.** gpt-oss returned
`notify_finance_team<|channel|>commentary`. Converse accepted that on the way out
and rejected it on the way back in, so a single bad name made *every later request
in that conversation* fail validation. Names are now normalised the moment they
arrive, before they reach the history or the server.

**The assistant hesitated on every request.** With one exact customer match, the
tool returned a question — "I found Acme Corp. Is that the one?" — instead of the
answer. Only running it end to end surfaced this; unit tests and a smoke test both
passed while the experience was still wrong.

### Accomplishments we are proud of

The claims we can point at rather than assert:

- the MCP session negotiates **protocol 2025-11-25** and exposes **five tools**
  (`python scripts/smoke_test.py`);
- a reminder was really sent through Stripe, and a message really arrived in Slack;
- write actions refuse to run without confirmation, enforced in the tool;
- **31 offline unit tests** cover the business rules, the spoken phrasing and the
  model-output normalisation, with no network and no model involved;
- the demo scenario is reproducible from an empty test account.

### What we learned

Voice is a different product surface, not a different input device. Barge-in,
recoverable mishearing, and one-sentence answers are not polish — without them the
thing is unusable, and none of them appear in a chat UI's requirements.

And the tool layer is the right place to be strict. Prompt instructions are
advisory; a tool that returns "this needs confirmation" is a guarantee.

### What is next

With add-on runtime access, the work is the interface and nothing else: the MCP
server, the tool contracts and the Agent Skill stay as they are. The obvious next
steps are richer intents ("who should I chase first today?"), a scheduled daily
briefing that surfaces newly overdue invoices without being asked, and a
policy layer for who may authorise sending a customer a demand for money.

### Built with

python · model-context-protocol · fastmcp · amazon-bedrock · boto3 ·
openai-gpt-oss · stripe-api · slack-incoming-webhooks · fastapi · web-speech-api ·
agent-skills

---

## "Did your project exist before the hackathon?"

No. The repository was created during the submission window and everything in it —
the MCP server, the agent loop, the simulator, the Agent Skill and the test data
seeder — was written for this submission.

It shares a *domain* with an earlier project of mine, a Slack app that creates
invoices from chat. It shares no code: the only file reused is the Apache-2.0
`LICENSE`. The earlier project is where the domain knowledge came from (how
invoicing teams actually talk, what "overdue" means in practice); the code here
starts from a blank file and a different premise, which is that the interaction
should be spoken.

---

## Demo video

Under three minutes, public, in English. Script and shot list:
`docs/DEMO_SCRIPT.md`. The video shows a real conversation against the running
simulator, the tool calls as they happen, the Slack message arriving, and the
spoken confirmation. No mockups.

---

## Code repository

`https://github.com/zhuwensh/chaseline` — public, Apache-2.0, so no
collaborator invitations are needed. The track's required technology is visible in
code: `mcp_server/server.py` starts a FastMCP server over Streamable HTTP, and both
`agent/agent.py` and `web_demo/app.py` connect with
`mcp.client.streamable_http.streamablehttp_client`.

---

## Product feedback

Full answers, one section per tool, in [PRODUCT_FEEDBACK.md](../PRODUCT_FEEDBACK.md):
MCP, the gated Alexa+ tooling, Devpost, Amazon developer documentation, AWS
(Bedrock), Stripe, and Slack.

## Friction log

[FRICTION_LOG.md](../FRICTION_LOG.md) — three entries with task, steps, expected
versus actual, severity, workaround and an actionable suggestion each.

## Feature requests

At the end of [PRODUCT_FEEDBACK.md](../PRODUCT_FEEDBACK.md): a participant-facing
Alexa+ sandbox, known-good SDK versions for the required protocol, and per-track
"known limitations" notes.
