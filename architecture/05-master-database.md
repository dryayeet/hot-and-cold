# Stage 5: Master Database

Source: `Outreach agent.pdf`, sections "Layer 5: Google Sheets Master Database", "Google Sheets Master Database Schema (Detailed)", "Metrics & Analysis". Revised by lemon on 2026-10-01: **Supabase Postgres from day one** (the earlier SQLite-now plan was dropped the same day), Google Sheets maybe later as a read-only view.

Part of the LangGraph agent: this stage is shared state/persistence used by every other node.

> **The schema is designed.** The full design (tables, RLS, indexes, events, embeddings, analytics views) lives in [`08-database-schema.md`](08-database-schema.md) and is **PROPOSED, awaiting lemon's approval**. This doc keeps the original PDF field inventory (columns A-AN) as the requirements record and maps it to the design.

## Goal

Single source of truth for all outreach data, response tracking, and interview prep. Grain unchanged from the PDF: **one `opportunities` row = one user + Company + Role**.

## Storage decisions (lemon, 2026-10-01)

1. **Supabase Postgres from day one** (multi-user ready, RLS, pgvector, jsonb expansion columns)
2. **Maybe later: Google Sheets** as a human-readable view on top, never a source of truth

The PDF's original Sheets-only rationale (human-readable, pivot/filter, CSV export) survives as the design's readability rules: flat readable tables, lookup vocabularies, analytics views that answer the pivot questions.

## Field inventory (from the PDF schema, columns A-AN)

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
- Customized Resume Link (was a Google Drive URL; now a local path or Supabase Storage, open question in the schema doc)

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

- Company Deep-Dive Summary (now a link to a local prep file)
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

| Stage | Tables written |
| --- | --- |
| 1 Discovery | `companies`, `company_snapshots`, `company_news`, `job_postings`, `opportunities`, `contacts`, `contact_emails`, `email_verifications` |
| 2 Matching | `match_assessments`, `hitl_reviews` (low-match gate) |
| 3 Resume | `resume_versions`, `resume_claims`, `hitl_reviews` (overflow gate) |
| 4 Mail + Sending | `outreach_messages`, `hitl_reviews` (draft approval), `scheduled_actions` |
| 6 Tracking/Follow-up | `inbound_messages`, `outreach_messages` (follow-ups), `scheduled_actions` |
| 7 Interview Prep | `interview_prep_packs`, `interviews` |
| Agent runtime | `agent_runs`, `events` (every state change) |
| Human (anytime) | `opportunities.notes` / `.tags`, `hitl_reviews.decided_at` |

## Derived metrics (PDF "Metrics & Analysis")

- Total companies researched
- Companies passing the quality gate (>=6/10)
- Mails sent (HITL approved)
- Response rate (%)
- Interview request rate (%)
- Average time to response
- Best-performing keywords/skills
- **Plus (lemon, 2026-10-01): send-time analytics, which send times correlate with responses, to optimize scheduling as data accumulates**

Implemented as the analytics views in `08-database-schema.md` section 6 (`v_campaign_funnel`, `v_response_rates`, `v_time_to_response`, `v_send_time_performance`, `v_keyword_performance`, `v_verification_accuracy`, `v_hitl_latency`).

## Tools

- **Supabase Postgres**: design in `08-database-schema.md`, pending approval; then `supabase/migrations/0001_init.sql`
- Agent connects server-side with a role that bypasses RLS; future dashboard clients go through RLS
