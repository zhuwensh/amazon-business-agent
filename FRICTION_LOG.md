# Friction Log — Amazon Developer Hackathon 2026

Project: BusinessFlow Agent (working title) — a self-hosted MCP server that turns
natural-language business requests into multi-step invoice, payment and
team-communication workflows. Built on an existing Stripe/Slack integration.

Track: **Alexa+**

Submission target: 2026-10-23

Last updated: 2026-09-29

---

## How this log is maintained

Amazon asks for one entry per friction point, with seven fields. Severity uses the
same scale as the feature-request field: **critical / important / nice-to-have**.

| Field | What it must contain |
|---|---|
| Task attempted | What I was trying to do |
| Steps taken | What I actually did, in order |
| Expected vs. actual | What I expected to happen, and what happened instead |
| Severity | critical / important / nice-to-have |
| Workaround | What I did to keep moving |
| Actionable suggestion | The specific change that would fix it |

Entries are written when the friction happens, not at the end, so the dates are real.

---

## Entry 001 — Alexa+ developer tools are gated, with no application path

**Date:** 2026-09-29
**Severity:** important
**Track:** Alexa+

**Task attempted**

Get access to the Alexa+ add-on developer tools (Category SDK, MCP Toolkit, CLI,
and Web Simulator) so the submission could be a real Alexa+ add-on experience
rather than a simulation.

**Steps taken**

1. Read the Alexa+ track description, which invites builders to "experience how
   brands in Preview are building and shipping experiences on Alexa+".
2. Opened the Alexa+ section of the hackathon Resources page.
3. Tried the obvious Amazon developer doc entry points for an Alexa+ add-on
   program (`developer.amazon.com/en-US/alexa/alexa-plus`,
   `developer.amazon.com/alexa-plus`,
   `developer.amazon.com/en-US/docs/alexa/alexa-plus/overview.html`).
4. Searched for a signup, waitlist, or partner-application form.
5. Read the hackathon FAQ.

**Expected vs. actual**

Expected: an application form, a waitlist, or a documented onboarding path — the
pattern Amazon already uses on other tracks in this same hackathon (Ring is
"create a free account and get API access"; Bee is "connect the CLI").

Actual: there is no path at all. The FAQ states the tools "are in preview and
available to select partners only — there is currently no way for hackathon
participants to apply for or gain access." The three obvious documentation URLs
return HTTP 404, so a builder who has not already found the FAQ has no way to learn
this from Amazon's own docs. Worse, the track description points the opposite
direction by inviting builders to experience what Preview partners are building.

**Workaround**

Followed the FAQ's instruction: build a self-hosted MCP server (protocol 2025-11-25
or later, Streamable HTTP) and demo it through a self-built web front end.
Re-planned the whole submission around the MCP path and treated the voice
experience as a simulation.

**Actionable suggestion**

1. Put the access limitation on the Alexa+ track card itself — one line, next to
   the "brands in Preview" sentence. Right now the only place it appears is deep in
   the FAQ, and the track copy above it implies the opposite. This single sentence
   would have saved hours of searching for a form that does not exist.
2. If a partner-preview path ever opens, publish an application form plus a rough
   review timeline, so builders can choose between waiting and going the MCP route.
3. If the Alexa+ Web Simulator cannot be shared with participants, publish a short
   reference of what an Alexa+ add-on interaction looks like (a screenshot of a
   tool-backed response, the expected response shape and length, and how
   confirmations are surfaced). Without it, every participant invents a different
   simulated UX, and none of them can be checked against the real product.

---

## Entry 002 — No Alexa+-specific build documentation for participants

**Date:** 2026-09-29
**Severity:** important
**Track:** Alexa+

**Task attempted**

Determine exactly what an "Alexa+ compatible" MCP server needs in practice:
required protocol version, transport, any Alexa+-specific conventions, and how tool
results should be shaped for a spoken interface.

**Steps taken**

1. Read the Alexa+ track requirements, the official rules, and the FAQ.
2. Followed every link in the Alexa+ section of the Resources page: both point to
   the generic Model Context Protocol spec (Streamable HTTP transport) and to MCP
   Apps (`apps.extensions.modelcontextprotocol.io`).
3. Looked for an Alexa+-specific getting-started page, sample add-on, or tool
   naming convention. Found none reachable by a participant.

**Expected vs. actual**

Expected: a build page saying which protocol version and transport are required, a
known-good sample add-on or starter, and a handful of rules about how a tool result
should be shaped for a voice assistant.

Actual: the only enforceable requirements are the general MCP spec (2025-11-25+,
Streamable HTTP) and "your repo must actually call your track's required technology
in code, not just mention it in the README". Everything that actually determines
whether the experience feels like Alexa+ — spoken response length, how a multi-step
or consequential action is confirmed, session and context expectations across
turns, how to disambiguate when the user's intent is wrong — is undocumented. The
MCP Apps extension that is linked is about rendering interactive UI inside chat
clients, which is a different problem from voice.

**Workaround**

Stood on the generic MCP spec, then verified by reading source that the stack
already in use meets it, rather than guessing:

- the pinned MCP Python SDK (`mcp==1.28.1`) exposes
  `LATEST_PROTOCOL_VERSION = "2025-11-25"` and
  `SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]`;
- the existing server exposes its endpoint over Streamable HTTP, and an existing
  client in the same codebase connects with
  `mcp.client.streamable_http.streamablehttp_client`, so the transport requirement
  is already satisfied.

The verification was then repeated as a runtime check rather than a source
reading: a smoke test starts the server, connects over Streamable HTTP and prints
the negotiated version, which came back as `2025-11-25`. It would have been faster
to be told the minimum version than to derive it, and it would have been faster
still to be told that the transport is Streamable HTTP rather than the older SSE
transport, since both appear in MCP tutorials.

Then designed the voice layer by judgement: short spoken summaries instead of raw
JSON, an explicit confirmation step before any consequential action (sending a
customer a payment reminder), and a spoken-friendly outcome sentence naming what
was actually done.

**Actionable suggestion**

Publish a one-page "Alexa+ MCP add-on checklist" for participants: minimum protocol
version and transport, one known-good tool definition, and 3-5 concrete guidelines
for voice-friendly tool results (response length, when to confirm, what a good
success/error phrasing looks like). Even a stub page with a working sample would
remove most of the guesswork, and it would make every submission more comparable
for judges.

---

## Entry 003 — Protocol requirement is stated, but no known-good SDK versions

**Date:** 2026-09-29
**Severity:** nice-to-have
**Track:** Alexa+

**Task attempted**

Confirm the minimum SDK versions that satisfy the "MCP spec 2025-11-25 or later"
requirement before updating an existing MCP server.

**Steps taken**

1. Read the protocol version requirement on the track page and in the rules.
2. Checked the versions already pinned in the existing project.
3. Read the pinned SDK's source to confirm which protocol versions it advertises.

**Expected vs. actual**

Expected: the track resources would name a known-good SDK version, or at least
state that any SDK supporting 2025-11-25 is acceptable.

Actual: the requirement is only stated as a protocol version. Package versions are
left entirely to the builder, and a plausible-looking pin is not obviously
compliant or non-compliant without reading the SDK source.

**Workaround**

Read the SDK source at the pinned version to confirm compliance (see Entry 002).
Documented the verified versions in the project README so a judge can check the
claim quickly.

**Actionable suggestion**

Add a "known-good versions" line to the Alexa+ track resources, for example the
minimum `mcp` and `fastmcp` releases that support protocol 2025-11-25. One line,
and builders stop having to verify this from source.

---

## Template for new entries

```markdown
## Entry NNN — <one-line summary>

**Date:** YYYY-MM-DD
**Severity:** critical | important | nice-to-have
**Track:** Alexa+ | Fire TV | Bee | Ring | AWS Builder | Open Source

**Task attempted**

**Steps taken**

**Expected vs. actual**

**Workaround**

**Actionable suggestion**
```
