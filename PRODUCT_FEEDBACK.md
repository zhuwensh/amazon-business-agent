# Product Feedback — Amazon Developer Hackathon 2026

Project: BusinessFlow Agent (working title) — a self-hosted MCP server for
natural-language business operations (invoices, payments, team notification).

Track: **Alexa+** · Mini challenges: **AWS Builder**, **Open Source**

Last updated: 2026-09-29

---

## How to fill this in

The submission form requires feedback on **every** tool, API or SDK used, covering
five things: what it was used for, what worked well, what needs work, how
onboarding felt, and whether I would build with it again. One section per tool.
Sections marked `TODO` are filled in as the project is built.

---

## 1. Model Context Protocol (spec + Python SDK + FastMCP)

**Used for:** the entire integration surface. Business operations are exposed as
MCP tools, and both the agent and the web-based simulated Alexa+ front end are MCP
clients. This is the required technology for the Alexa+ track.

**What worked well:** the spec is genuinely portable. The same MCP server serves a
stdio client and a Streamable HTTP client without any change to the tool code, so
the "build once, connect any client" claim holds up in practice. Tool schemas
generated from typed Python functions keep the tool-calling side honest. The
versioned spec (2025-11-25) means a builder can pin behaviour rather than coding
against a moving target. Protocol negotiation is also observable at runtime —
the initialized session reports the version it agreed on (`2025-11-25` here),
which made it possible to prove compliance with a two-line smoke test instead of
arguing from documentation.

**What needs work:** tool *result* conventions are the weak point. The spec is
precise about the wire protocol and much looser about what a good tool result looks
like for a given surface. For a voice assistant, the same tool that returns a rich
JSON payload for a dashboard also needs a short, speakable summary; there is no
guidance or convention for that, so each builder invents one. Error semantics are
similar: raising an exception versus returning a structured error the model can
reason about is left to the author, and the difference matters a lot for agentic
reliability.

**Onboarding:** good for a Python developer — the spec is readable and the SDK's
typed API is easy to pick up. The harder part was confirming *which* SDK versions
implement protocol 2025-11-25; that information had to come from reading the SDK
source rather than from documentation.

**Would I build with it again:** yes. It is the cleanest way I have found to make
one integration reachable from multiple clients, and it keeps the business logic
testable without any chat platform in the loop.

---

## 2. Alexa+ add-on developer tools (Category SDK, MCP Toolkit, CLI, Web Simulator)

**Used for:** nothing — these are not accessible to hackathon participants. The FAQ
states the tools are in preview and available to select partners only, with no way
for participants to apply. The submission therefore targets the MCP-based path the
rules allow, and the Alexa+ experience is demonstrated through a self-built web
front end.

**What worked well:** not applicable; no access was granted, so there is nothing to
evaluate on the tooling itself.

**What needs work:** the access story. The track description invites builders to
"experience how brands in Preview are building and shipping experiences on
Alexa+", which reads as an invitation to use those tools. The limitation is
documented only in the Devpost FAQ, while the obvious Amazon documentation URLs
404. The net effect is that a participant cannot tell whether they are missing an
onboarding step or whether the tools are simply not available.

**Onboarding:** there is no onboarding path to evaluate.

**Would I build with it again:** I would want to. A real Alexa+ add-on path with a
Web Simulator would let a developer validate the voice experience properly, which
is exactly what a self-built simulator cannot do. If a preview opens to
participants, I would apply.

---

## 3. Devpost (submission platform)

**Used for:** registering, reading the rules and FAQ, and submitting the project.

**What worked well:** the rules, track descriptions, FAQ and resources are in one
place, and the FAQ is genuinely specific — it answers the hard questions (physical
hardware, gated tooling, repo hosting, reviewer access, which AWS services qualify
for the mini challenge, and how to keep Bedrock costs down outside the judging
window). The per-track "what to submit" checklist removes real ambiguity.

**What needs work:** the most decision-changing facts live only in the FAQ, while
the track description and the resources page imply something else. The single
biggest planning decision — whether an Alexa+ add-on can be built for real — is
answered in the FAQ and contradicted by the track copy. A short "known
limitations" callout on each track page would prevent builders from designing
around a capability they cannot have.

Cross-references are also one-directional: the resources page links to the MCP
spec, but nothing on the Alexa+ side says "participants build MCP servers and their
own front end; the Preview tools are out of scope".

**Onboarding:** registration is quick. Finding the *answer* to a specific
eligibility question took longer than it should have, because the FAQ is organized
as a flat question list rather than grouped by track.

**Would I build with it again:** yes. The information quality is high once found.

---

## 4. Amazon Developer documentation and developer community

**Used for:** researching the Alexa+ add-on path and the available developer
programs for this hackathon's tracks.

**What worked well:** the documentation for the tracks that are open (Ring, Bee,
Fire TV) is reachable and specific — Ring in particular documents account setup and
API access clearly, and Bee documents its CLI and MCP server.

**What needs work:** Alexa+ has no participant-facing build documentation at all.
The three natural entry points return 404. For an external developer, there is no
way to tell whether Alexa+ add-ons are a public developer surface yet.

**Onboarding:** uneven across tracks. Open tracks onboard well; the gated track has
no entry point.

**Would I build with it again:** yes for the open tracks.

---

## 5. AWS (Bedrock / Strands Agents SDK / AgentCore) — AWS Builder mini challenge

**Used for:** the agent's reasoning loop. Every turn — which tool to call, in what
order, how to phrase the spoken answer — goes through Amazon Bedrock's Converse API
with `toolConfig`, from a local boto3 client (`bedrock-runtime`,
`ap-northeast-1`, `openai.gpt-oss-20b-1:0`, IAM permissions scoped to that single
model's ARN).

**What worked well:** Converse is the right surface for an agent. Tool definitions
and the `toolUse` / `toolResult` round trip use the same request shape as any other
message, so swapping models is a config change rather than a code change — which
is exactly what an agent loop needs. Tool calling worked on the first attempt once
the configuration was right: the model asked for `get_overdue_invoices` with
correct arguments, unprompted. Multi-turn orchestration also held up — a follow-up
"send them a reminder and tell finance" was carried out over two further turns,
with the write action gated behind an explicit confirmation. Credentials through
boto3's standard chain plus `AWS_SHARED_CREDENTIALS_FILE` made the project
self-contained. When something was wrong, the error text named the exact action and
resource ARN, which is what made the problem findable.

**What needs work:** the model card is the wrong granularity for the decision that
matters most. "Does this model support tool calling?" is answered by a features
table organised by endpoint, where tool calling appears under `bedrock-mantle` and
is absent from `bedrock-runtime` — even though `bedrock-runtime` + Converse does
support it. We could not settle that question from the documentation and had to
establish it empirically with a test call. A per-model, per-API capability matrix
(model × API × feature) would remove the guesswork.

Second, one error type covers three unrelated causes. `AccessDeniedException` is
returned for (a) no identity-based policy covering the action, (b) model access not
granted, and (c) the account still being verified — each needing a completely
different fix. A stable `reason` field, or a distinct error code per cause, would
have saved a diagnostic cycle.

Third, the region is encoded in three places that must agree — the console where
model access was granted, the resource ARN in the IAM policy, and the client's
region — and nothing checks that they do. In our case a duplicated region setting
silently overrode the intended one, and the resulting denial was indistinguishable
from a permissions mistake. Model access is also still a per-region console step,
which is easy to do in the wrong region.

**Onboarding:** the console path — model access, then an IAM user with
`bedrock:InvokeModel`, then an access key — is short and needed no documentation.
Getting the first successful call took a while, but almost none of it was spent on
the SDK: it went to the account verification wait and to resolving the
region-versus-policy-ARN mismatch. Installing boto3 and calling Converse was a
one-step experience.

**Would I build with it again:** yes. Converse with tool use is a clean substrate
for an agent, and for a demo this size the cost is negligible. Two things would
make it materially faster next time: the per-API capability matrix, and distinct
error codes for the three flavors of `AccessDeniedException`. Note also that the
hackathon FAQ's advice to stub model calls during early development was correct and
worth following — the first working configuration is not needed until the agent
behaviour is settled.

---

## 6. Stripe API (test mode)

**Used for:** reading (customer lookup, invoice listing, overdue detection) and
one write — emailing a customer their invoice as a payment reminder. Test mode
only.

**What worked well:** test mode is a real sandbox rather than a simulation: the
same objects, the same validation, the same error shapes, so a demo built on it is
honest about what it proves. `hosted_invoice_url` hands you a payable link for
free, which is what makes a reminder useful without building any payment UI.
Invoice numbers are human-friendly, which matters more than expected for a voice
assistant — the model can say "invoice O3RSQJ1Z-0004" and it means something. And
the errors name the offending parameter precisely: being told that `due_date`
"expects a unix timestamp representing a date and time in the future, you specified
1789128000, which is in the past" is a complete diagnosis in one line.

**What needs work:** three things cost real time here.

First, an invoice cannot be created *or* updated with a due date in the past, which
means a fresh test account cannot be given an overdue invoice at all. "Show me what
is late" is a natural first question for a collections tool, and there is no
straightforward way to make that state exist. The supported answer is test clocks,
which brings the second problem.

Second, objects on a test clock are invisible to the account-wide list endpoints.
`GET /v1/customers` accepts a `test_clock` filter, but `GET /v1/invoices` does not
accept one and does not return clock invoices either — so the only way to read them
is customer by customer. That inconsistency is what makes the workaround expensive.

Third, adding an invoice item implicitly creates a draft invoice. Calling
`POST /v1/invoices` afterwards therefore produces a *second*, empty invoice which
finalizes as a zero-amount **paid** one. Nothing errors; the only symptom is a
strange paid invoice in the account, and the real invoice silently has no lines.
`pending_invoice_items_behavior=include` is the fix, but it has to be discovered.

**Onboarding:** excellent. A test key and a few calls, and the dashboard is the
same interface as live mode, so there was nothing new to learn.

**Would I build with it again:** yes. Being able to reach a real, correct, payable
invoice from a few lines of code is what makes this project's workflow plausible
rather than a mock.

---

## 7. Slack API

**Used for:** one outbound action — posting the outcome of a chase to the finance
channel as the final step of a multi-step workflow — through an Incoming Webhook.

**What worked well:** an Incoming Webhook is the right shape for this job. It needs
no OAuth install, no bot user, no scopes and no OAuth scopes screen; the app can be
a blank app with every other feature switched off, and the whole thing is one URL.
That keeps the permission story trivial to explain: this integration can post to
one channel and can do nothing else. Onboarding took minutes, and the message
arrived in the channel on the first attempt.

**What needs work:** the webhook is bound to whichever channel was chosen when it
was created, and the API gives you no way to read that back — a successful post
returns `ok` and nothing else. Any application that *speaks* the destination has to
keep its own copy of the channel name in configuration, which can silently drift
from the truth: the assistant would cheerfully say "I posted to #finance" while the
message landed somewhere else, and no error would ever surface. We ended up
treating the webhook as the source of truth and the configured name as a display
label only, documented in the code — but a `channel` field in the response, or a
read-only way to ask a webhook where it points, would remove that whole class of
bug.

**Onboarding:** fast and uneventful. Creating a blank app, enabling Incoming
Webhooks, and picking a channel was the entire setup.

**Would I build with it again:** yes for one-way notifications, which is most of
what a notification is. Anything that needs to read messages or respond to events
would need the full app and OAuth flow, and that trade-off is worth making
explicitly rather than by default.

---

## Feature requests (optional)

| Feature | Why it matters | Urgency |
|---|---|---|
| Participant-facing Alexa+ add-on sandbox (even without the full Preview tools) | A voice assistant cannot be validated properly without one; today every submission invents its own approximation | important |
| Known-good SDK version list for the required protocol | Removes a source-reading step for every builder | nice-to-have |
| Per-track "known limitations" callout on the hackathon page | Prevents architecture decisions based on capabilities that are not actually available | important |

## Notes on AWS Promotional Credits

The $150 AWS promotional credit is requested per individual, not per team, and the
hackathon FAQ documents the request form. Credits are applied to the AWS services
used for the AWS Builder mini challenge.
