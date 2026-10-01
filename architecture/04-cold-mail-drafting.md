# Stage 4: Cold Mail Drafting (and Scheduled Sending)

Sources: `Outreach agent.pdf`, sections "Layer 4: Cold Mail Drafting", "Phase 4: Cold Mail Drafting", "Phase 5: HITL Approval Gate", "Phase 6: Sending", "Risk Mitigation", "Why Gmail API (not SMTP)", "Why 8:30 AM Mon-Fri". Grounded in that PDF, as revised by lemon on 2026-10-01 (OpenRouter instead of Claude API; send-time logging for analytics).

Part of the LangGraph agent: this stage is a node/subgraph in the graph. Gmail API stays, per lemon.

## Goal

Write personalized, conversational cold mails that prove research, attach the customized resume, and park everything as Gmail drafts. Nothing is ever sent without HITL approval.

## Inputs

- Company research from Stage 1 (funding, news, products, sentiment)
- Match score and reasoning from Stage 2
- Customized resume PDF from Stage 3 (page-count validated)
- Contact data: hiring manager name, title, HR/TA email, validation status

## Research snippets to gather per mail (PDF examples)

- Recent funding: "Acme AI raised Series B ($50M) last month"
- Product milestone: "Just launched their new product X"
- Role context: "Hiring for ML engineers to scale their recommendation engine"
- Your connection: "Your background in recommendation systems aligns perfectly"

## Mail template structure (as specified)

- **Greeting:** "Hi [Hiring Manager Name]," (personalized, never "Dear Hiring Team")
- **Hook:** 1-2 sentences on why this company specifically, showing research, e.g. "I saw you just closed Series B and are scaling the data platform team..."
- **Body (conversational, not formal):**
  - Para 1: brief intro, who you are, current role/student status
  - Para 2: relevant experience, 2-3 bullets connecting to their JD
  - Para 3: why interested in them specifically (mission, tech stack, growth stage)
  - Para 4: what you'd contribute, specific value prop for this role
- **CTA:** e.g. "Open to a quick chat about the role, happy to hop on a call whenever works best." or "Would love to learn more about the team. Let me know if my background is a fit!"
- **Sign-off:** name, LinkedIn URL, GitHub link, phone number

## Tone rules

Do: natural and conversational (like talking to a peer), show research (company detail, recent news, product), be specific to the role.
Don't: corporate jargon, overselling, flowery language, length. 8-10 sentences max, 150-200 words max.

## Gmail draft creation

- To: hiring manager / HR/TA email
- From: lemon's Gmail
- Subject: "[Role Name] Application - Prajwal Pandey"
- Body: the cold mail text
- Attachment: `Prajwal_Pandey_[CompanyName].pdf`
- Status: DRAFT, explicitly not sent

## HITL approval gate (Phase 5)

Lemon reviews all drafts before anything leaves the account:

- Read the mail: does it make sense, is it personalized
- Check the resume: formatting issues
- Decision: approve to send, or edit/reject
- Rejected drafts: the agent can revise, or lemon edits manually

## Scheduled sending (Phase 6)

1. Schedule check: is it Mon-Fri, 8:30 AM IST? If not, queue for the next available slot
2. Spread sends: never all 50 at once. 5-10 per day across the week; the spam mitigation caps any day at 20
3. Send via Gmail API (draft converts to sent)
4. Log: sent date/time (ISO), status "Sent", follow-up due = sent date + 7 days
5. **Send-time analytics (lemon, 2026-10-01): every send is logged with its exact timestamp so that, as responses accumulate, the data can be analyzed for which send times correlate with replies, and the 8:30 AM default can be optimized over time**

## Why these choices (PDF's own justifications)

- Gmail API over SMTP: drafts are a built-in HITL gate sitting in the inbox awaiting review; easier reply/open tracking through Gmail thread context; no sending infrastructure to manage
- 8:30 AM Mon-Fri IST: cold mails during work hours get higher open rates; future A/B tests (9 AM, 6 PM) will find the optimal window

## DB fields touched (formerly Sheet columns; schema discussion pending, see `05-master-database.md`)

- Draft Date (ISO timestamp)
- Mail Status (Draft / Sent / Bounced / No Response / Positive Response)
- Sent Date (ISO timestamp, only if sent), kept precise for send-time analytics

## Tools

- **Gmail API** via `google-api-python-client` (drafting, sending, scheduling)
- **OpenRouter API** (lemon's key, model TBD): drafting and tone checking. No Claude API anywhere in this project (lemon, 2026-10-01)
- Scheduling: APScheduler / cron per the PDF tech stack
- **SQLite** for the send log and status fields

## Risks (from the PDF)

- Marked as spam: personalize heavily (generic equals spam), never more than 20 sends in one day, send from the legitimate personal Gmail, monitor the spam folder weekly and adjust volume
- Blacklisted: only extracted personal addresses, one follow-up only, email validation before sending

## Future roadmap items for this stage (Phase 3 features)

- Template variants: 3 drafts per mail (personal touch, data-driven, humble), A/B send 50/50
- Timing experiments: 8:30 AM vs 6 PM, measured response rates
- Subject line testing: "Following up + question" vs "Quick Question"
- Resume format tests: ATS-optimized vs design-heavy, measured callbacks
