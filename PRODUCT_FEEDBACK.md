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

**Used for:** `TODO` — planned: the agent's reasoning loop and model inference, with
documented integration points. The hackathon FAQ notes that Bedrock resources do
not need to run continuously until judging (Nov 9-20) and recommends stubbing calls
during early development, which is the plan.

**What worked well:** `TODO`

**What needs work:** `TODO`

**Onboarding:** `TODO`

**Would I build with it again:** `TODO`

---

## 6. Stripe API (test mode)

**Used for:** `TODO` — customer lookup, invoice listing, overdue detection,
reminder delivery.

**What worked well:** `TODO`

**What needs work:** `TODO`

**Onboarding:** `TODO`

**Would I build with it again:** `TODO`

---

## 7. Slack API

**Used for:** `TODO` — outbound notification to a finance channel as the final step
of a multi-step workflow.

**What worked well:** `TODO`

**What needs work:** `TODO`

**Onboarding:** `TODO`

**Would I build with it again:** `TODO`

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
