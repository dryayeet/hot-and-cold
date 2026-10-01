# Stage 5: Google Sheets Master Database

Sources: `Outreach agent.pdf`, sections "Layer 5: Google Sheets Master Database", "Google Sheets Master Database Schema (Detailed)", "Why Google Sheets (not SQL)", "Metrics & Analysis". Grounded in that PDF. This stage is cross-cutting: every other stage reads from and writes to it.

## Goal

Single source of truth for all outreach data, response tracking, and interview prep. One row = one Company + Role pairing.

## Why Sheets and not SQL (PDF's justification)

- A master database is needed, but so is a human-readable interface
- Sheets = single source of truth, easy to pivot and filter manually
- Backup: exportable to CSV anytime
- Future: if scale grows, migrate to PostgreSQL with Sheets kept in sync

## Full schema (columns A-AN, as specified in the PDF)

### Identification

| Col | Field |
| --- | --- |
| A | Company Name |
| B | Role Title |
| C | Company URL |
| D | Job Board Link |

### Company Intelligence

| Col | Field |
| --- | --- |
| E | Funding Status (e.g. "Series B - $50M, June 2026") |
| F | Company Size (headcount estimate) |
| G | Locations (HQ + offices) |
| H | Growth Signal (hiring velocity, YoY headcount growth) |
| I | Recent News (latest announcement + timestamp) |
| J | Sentiment Score (Glassdoor/Blind aggregate, 1-5) |
| K | Founders/Leadership (names + brief bios) |
| L | Public Valuation / Revenue (if available) |

### Contacts

| Col | Field |
| --- | --- |
| M | Hiring Manager Name |
| N | Hiring Manager Title |
| O | HR/TA Email |
| P | Email Validation Status (Valid / Bounce / Unknown) |
| Q | LinkedIn Profile URL (hiring manager) |

### Your Fit

| Col | Field |
| --- | --- |
| R | Match Score (1-10) |
| S | Keyword Gaps (e.g. "Missing: Kubernetes, Docker") |
| T | Resume Customizations Applied (bullet point list) |
| U | Customized Resume Link (Google Drive shareable URL) |

### Mail Tracking

| Col | Field |
| --- | --- |
| V | Draft Date (ISO timestamp) |
| W | Mail Status (Draft / Sent / Bounced / No Response / Positive Response) |
| X | Sent Date (ISO timestamp, only if sent) |
| Y | Response Type (No response / Rejection / Interview request / Auto-reply / Forwarded / Not hiring) |
| Z | Response Date |
| AA | Response Details (copy of response email text) |

### Follow-Up Tracking

| Col | Field |
| --- | --- |
| AB | Follow-up Due Date (Sent Date + 7 days) |
| AC | Follow-up Status (Not Yet / Sent / Response Received / Closed) |
| AD | Follow-up Sent Date (if sent) |
| AE | Follow-up Response Type |

### Interview Prep (only if positive response)

| Col | Field |
| --- | --- |
| AF | Company Deep-Dive Summary (rich text link to detailed notes) |
| AG | Role Deep-Dive Summary |
| AH | Your Fit Analysis |
| AI | Interview Structure (number of rounds, types) |
| AJ | Top 10 Interview Questions |
| AK | Prep Plan (link to study guide) |
| AL | Interview Schedule (dates if scheduled) |

### Notes & Tags

| Col | Field |
| --- | --- |
| AM | Notes (internal observations, red flags) |
| AN | Tags (e.g. "high-priority", "startup", "well-funded", "needs-follow-up") |

## Which stage writes what

| Stage | Columns written |
| --- | --- |
| 1 Discovery | A-Q |
| 2 Matching | R, S (+ reasoning) |
| 3 Resume | T, U |
| 4 Mail + Sending | V, W, X |
| 6 Tracking/Follow-up | Y, Z, AA, AB, AC, AD, AE |
| 7 Interview Prep | AF-AL |
| Human (anytime) | AM, AN |

## Derived metrics (PDF "Metrics & Analysis")

- Total companies researched
- Companies passing the quality gate (>=6/10)
- Mails sent (HITL approved)
- Response rate (%)
- Interview request rate (%)
- Average time to response
- Best-performing keywords/skills

## Tools

- `gspread` for all read/write
- Google Drive API for resume PDF links (column U)

## Role in the system (PDF summary)

Sheets gives the pipeline a master database for analytics and future optimization, and its human-readable nature is what lets lemon review, pivot, and annotate (columns AM, AN) without any tooling.
