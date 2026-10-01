# Stage 5: Master Database

Source: `Outreach agent.pdf`, sections "Layer 5: Google Sheets Master Database", "Google Sheets Master Database Schema (Detailed)", "Metrics & Analysis". Revised by lemon on 2026-10-01: **local SQLite now, Supabase (Postgres) later, Google Sheets maybe even later.** The PDF's Sheets schema is preserved below as the target field list.

Part of the LangGraph agent: this stage is shared state/persistence used by every other node.

> **AMBIGUITY / DISCUSSION NEEDED: the SQLite table structure is not designed yet.** The A-AN column list below is the field inventory, not a table design. Decisions pending: one wide table vs normalized (companies / contacts / mails / follow_ups / prep), how to represent the one-row-per-company+role grain, status enums, and the migration path to Supabase. Tracked in todo.md.

## Goal

Single source of truth for all outreach data, response tracking, and interview prep. Conceptual grain from the PDF: one record = one Company + Role pairing.

## Storage decision timeline (lemon, 2026-10-01)

1. **Now: local SQLite** (stdlib `sqlite3`, no cloud dependency)
2. **Later: migrate to Supabase Postgres** when the project needs a real server DB
3. **Maybe later: Google Sheets** as a human-readable view on top, if wanted

The PDF's original Sheets-only rationale (human-readable, pivot/filter, CSV export) is retained as context for why the schema is flat and readable.

## Target field inventory (from the PDF schema, columns A-AN)

### Identification

- Company Name
- Role Title
- Company URL
- Job Board Link

### Company Intelligence

- Funding Status (e.g. "Series B - $50M, June 2026")
- Company Size (headcount estimate)
- Locations (HQ + offices)
- Growth Signal (hiring velocity, YoY headcount growth)
- Recent News (latest announcement + timestamp)
- Sentiment Score (Glassdoor/Blind aggregate, 1-5)
- Founders/Leadership (names + brief bios)
- Public Valuation / Revenue (if available)

### Contacts

- Hiring Manager Name
- Hiring Manager Title
- HR/TA Email
- Email Validation Status (Valid / Bounce / Unknown) **+ deliverability detail per the Stage 1 revision (verification method result, not just syntax)**
- LinkedIn Profile URL (hiring manager)

### Your Fit

- Match Score (1-10)
- Keyword Gaps (e.g. "Missing: Kubernetes, Docker")
- Resume Customizations Applied (bullet point list)
- Customized Resume Link (was a Google Drive URL; **now a local filesystem path**, revisit on Supabase migration: could become object storage)

### Mail Tracking

- Draft Date (ISO timestamp)
- Mail Status (Draft / Sent / Bounced / No Response / Positive Response)
- Sent Date (ISO timestamp, only if sent) **+ send time logging for analytics per the Stage 4 revision**
- Response Type (No response / Rejection / Interview request / Auto-reply / Forwarded / Not hiring)
- Response Date
- Response Details (copy of response email text)

### Follow-Up Tracking

- Follow-up Due Date (Sent Date + 7 days)
- Follow-up Status (Not Yet / Sent / Response Received / Closed)
- Follow-up Sent Date (if sent)
- Follow-up Response Type

### Interview Prep (only if positive response)

- Company Deep-Dive Summary (was rich text link; **now link to a local prep file**)
- Role Deep-Dive Summary
- Your Fit Analysis
- Interview Structure (number of rounds, types)
- Top 10 Interview Questions
- Prep Plan (link to study guide)
- Interview Schedule (dates if scheduled)

### Notes & Tags

- Notes (internal observations, red flags)
- Tags (e.g. "high-priority", "startup", "well-funded", "needs-follow-up")

## Which stage writes what

| Stage | Fields written |
| --- | --- |
| 1 Discovery | identification, company intelligence, contacts |
| 2 Matching | match score, keyword gaps (+ reasoning) |
| 3 Resume | customizations applied, resume path |
| 4 Mail + Sending | draft date, mail status, sent date (+ send-time analytics log) |
| 6 Tracking/Follow-up | response type/date/details, follow-up fields |
| 7 Interview Prep | prep fields |
| Human (anytime) | notes, tags |

## Derived metrics (PDF "Metrics & Analysis")

- Total companies researched
- Companies passing the quality gate (>=6/10)
- Mails sent (HITL approved)
- Response rate (%)
- Interview request rate (%)
- Average time to response
- Best-performing keywords/skills
- **Plus (lemon, 2026-10-01): send-time analytics, which send times correlate with responses, to optimize scheduling as data accumulates**

## Tools

- `sqlite3` (Python stdlib), no external service
- Migration path to Supabase Postgres: to be planned (see todo.md)
