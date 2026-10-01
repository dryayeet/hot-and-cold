# Stage 6: Response Tracking & Follow-Up Orchestration

Sources: `Outreach agent.pdf`, sections "Layer 6: Response Tracking & Follow-Up Orchestration", "Phase 7: Response Tracking", "Phase 8: Follow-Up Workflow", scheduling rules. Grounded in that PDF.

## Goal

Automate smart follow-ups, respect boundaries, avoid spam. Every draft this stage produces again requires HITL approval.

## Response classification (manual + automated)

Runs as a background job, daily or on-demand. It only inspects emails from contacts already in the Sheet.

Automated detection:

- Auto-reply: "I'm out of office", "auto-generated"
- Forwarded to recruiter: email arrives from a different sender than the one contacted
- Interview request: email contains "interview", "call", "next steps"

Manual classification (for ambiguous emails): lemon flags as no response, rejection, "not hiring", forwarded, or interview request. Rejections in particular go to manual review per Phase 7.

On every classification, log: response type, response date, response details (relevant text copied from the email), update the Sheet.

## Follow-up workflow (only if "No Response")

- **Day 0:** mail sent (HITL approved). Follow-up due date set to sent date + 7 days
- **Day 7:** check for a response
  - Response exists: log the response type, stop
  - No response: create exactly one follow-up nudge
    - Subject: "Following up on [Role] at [Company]"
    - Body: brief natural reminder, 2-3 sentences max, casual not pushy, with CTA
    - Attachment: the same customized resume
    - Created as a Gmail draft, HITL approval required again (same gate as Stage 4)
- **Day 14+:** still no response: mark "no response after 14 days", close the loop

## No follow-up if (boundary rules)

- Explicit rejection received
- "We're not hiring" response
- Interview request (move to Stage 7 prep instead)
- 3 or more follow-ups already sent (spam avoidance)

Auto-reply detected: check again in 5 days rather than following up immediately.

## Scheduling rules

- Mails only sent Mon-Fri, 8:30 AM IST
- Follow-ups respect the same scheduling rule
- Timezone: IST (lemon's location)
- Future A/B test: different send times and templates

## Trigger actions after classification

- Interview request: start Stage 7 (interview prep research)
- No response + day 7 passed: queue the follow-up draft
- Rejection: close the loop, no follow-up
- Auto-reply: recheck in 5 days

## Output

Automated reminders for follow-ups; all follow-up drafts sitting in Gmail awaiting HITL approval.

## Sheet columns touched

- Y: Response Type
- Z: Response Date
- AA: Response Details
- AB: Follow-up Due Date
- AC: Follow-up Status (Not Yet / Sent / Response Received / Closed)
- AD: Follow-up Sent Date
- AE: Follow-up Response Type

## Tools

- Gmail API for inbox checks and draft creation
- Claude API for classification assist
- APScheduler / python-cron for the daily background job and 8:30 AM IST sending window

## Success metric this stage feeds

Response rate and average time to response roll up into the Sheet metrics; response time patterns per company are a named Phase 2 future feature.
