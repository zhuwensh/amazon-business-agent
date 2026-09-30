# Submission checklist

**Deadline: 23 October 2026, 12:00pm PDT** — that is **24 October, 03:00 in
Asia/Shanghai**. Treat the real deadline as the evening of 23 October local time
and submit with a day to spare; the form has several required fields and the video
has to upload first.

Judging runs 9–20 November. Per the hackathon FAQ, nothing needs to be running
during that window — spin Bedrock up when testing and tear it down afterwards.

---

## Done, with evidence

| Item | Evidence |
|---|---|
| Repository public, Apache-2.0 | `github.com/zhuwensh/amazon-business-agent`, no collaborator invitations needed |
| Alexa+ track requirement: self-hosted MCP server, spec 2025-11-25+, Streamable HTTP | `scripts/smoke_test.py` prints the negotiated protocol version |
| Track technology actually used in code | `mcp_server/server.py` runs FastMCP over `transport="http"`; both clients use `mcp.client.streamable_http` |
| Second sanctioned artifact: Agent Skill | `skills/cash-collection/SKILL.md` + tool reference |
| Real Stripe write | a payment reminder was sent in test mode |
| Real Slack delivery | a message arrived in the finance channel |
| Write actions gated on confirmation | enforced in the tool, not the prompt |
| Automated checks | 31 offline unit tests, plus the end-to-end smoke test |
| Demo data reproducible from an empty account | `demo/seed_test_data.py` (test clock) |
| Project description | `docs/DEVPOST_SUBMISSION.md` |
| Product feedback (required, every tool) | `PRODUCT_FEEDBACK.md`, seven sections |
| Friction log (worth up to 10% bonus) | `FRICTION_LOG.md`, three entries |
| Feature requests (optional) | end of `PRODUCT_FEEDBACK.md` |

---

## Blocked on you

**Record the demo video.** Script and shot list in `docs/DEMO_SCRIPT.md`. Under
three minutes, public on YouTube or Vimeo, in English, no third-party music or
footage. Refresh the data first so the numbers are round:

```bash
python -m demo.seed_test_data      # voids the previous run's invoices and rebuilds
python -m mcp_server.server        # terminal 1
python -m web_demo.app             # terminal 2, then open http://127.0.0.1:8080
```

**Check the microphone once, in Chrome or Edge.** Speech recognition is not
available in Safari or Firefox, and it is the only part of this build that has not
been exercised end to end from here. Say one sentence to the orb before you start
recording.

**Confirm where the Slack messages landed.** Two messages were posted while
verifying. If they arrived in a channel other than the one named in
`SLACK_FINANCE_CHANNEL`, fix that line in `.env` first — the assistant speaks the
configured name, and a mismatch is visible on camera.

---

## One decision to make

**Open Source mini challenge.** The rules ask for a *new, additional* open-source
project, or a contribution to a public repository, made during the window. This
repository is public with a licence and was created during the window, but the word
"additional" suggests something alongside the primary submission rather than the
submission itself.

Two ways to be safe, in order of effort:

1. Make a small genuine contribution to something this project actually depends
   on — the MCP Python SDK, FastMCP, or the Agent Skills documentation. We hit
   several real, reproducible rough edges worth reporting, and any of them could
   become an issue plus a documentation or code change.
2. Enter the mini challenge with this repository and explain the reasoning
   explicitly in the submission text.

Option 1 is stronger and cheap. Note that PRs do not need to be merged — a fork or
branch is acceptable.

---

## Worth doing if time allows

Add a screenshot or two from the simulator to the README. Judges read the README
before, and often instead of, watching the video, and the trace panel is the most
persuasive single image in the project.

Keep the `.env` file out of everything. It holds live test credentials for Stripe,
AWS and Slack; it is git-ignored, and it should stay that way.

---

## Submission form, field by field

| Field | Where the answer is |
|---|---|
| Track and mini challenges | `DEVPOST_SUBMISSION.md` → Track and mini challenges |
| Project description | `DEVPOST_SUBMISSION.md` → Project description |
| Pre-existing project explanation | `DEVPOST_SUBMISSION.md` → Did your project exist before… |
| Demo video URL | record, upload, paste |
| Code repository URL | `github.com/zhuwensh/amazon-business-agent` |
| Product feedback | `PRODUCT_FEEDBACK.md` |
| Friction log (optional) | `FRICTION_LOG.md` |
| Feature requests (optional) | end of `PRODUCT_FEEDBACK.md` |
