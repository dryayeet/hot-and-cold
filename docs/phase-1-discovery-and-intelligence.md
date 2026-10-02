# Phase 1: Discovery & Intelligence

This document explains the current Phase 1 implementation in `src/outreach_agent/phase_1/__main__.py`.

## Purpose

Phase 1 turns three inputs into a first-pass outreach pipeline:

- `base_resume.tex`
- `projects_and_exp.md`
- a natural-language role prompt

It produces:

- a campaign row
- an agent run row
- company rows
- company snapshot rows
- company news and job posting rows
- contact rows
- contact email rows
- email verification rows
- event rows

## Runtime

Run it with:

```bash
out/Scripts/python.exe src/outreach_agent/phase_1/__main__.py \
  --role-prompt "..." \
  --resume base_resume.tex \
  --projects projects_and_exp.md
```

## Environment

Required env vars:

- `OPENROUTER_API_KEY`
- `HUNTER_API_KEY`
- `DATABASE_URL`
- `OUTREACH_USER_ID`

Optional:

- `OPENROUTER_MODEL` defaults to a free model when set in `.env`

## Execution flow

1. Load `.env` through `src/outreach_agent/devtools/db.py`.
2. Validate the resume file by checking for the expected LaTeX sections.
3. Read `projects_and_exp.md` and pass the raw text into the LLM without pre-extracting technologies or job fields.
4. Create a `campaigns` row and an `agent_runs` row.
5. Insert a `run.started` event.
6. Run an LLM pre-pass over the role prompt plus raw resume/project text, then use the model's titles and keywords as structured Hunter filters, including enterprise engineering titles when they plausibly own the AI work, but avoiding generic catch-all titles unless strongly justified by the text.
7. Call Hunter discovery to get hiring companies in India only.
8. For each company:
   - normalize the company name and domain
   - upsert the company row
   - ask OpenRouter to research the company
   - store a `company_snapshots` row
   - store any news and job postings returned by the model
   - keep only India-based roles or roles explicitly open to India/remote India
   - skip the company if the relevance score is below 6
   - upsert an `opportunities` row
   - discover HR/TA and hiring-manager contacts through Hunter domain search
   - verify emails with SMTP ping
   - persist contacts, emails, verification rows, and opportunity-contact links
   - emit events for the important state changes
9. Mark the run as succeeded and write `run.finished`.

## Main code paths

### `main()`

Owns the orchestration. It wires together input validation, database writes, Hunter discovery, OpenRouter research, and contact persistence.

### `validate_resume_tex()`

Checks that the LaTeX contains the expected sections. The current implementation accepts either `\section{Work Experience}` or `\section{Experience}` for the experience section.

### `discover_companies()`

Calls Hunter `Discover People` with India headquarters plus recent hiring/job-title filters, so the pipeline stays narrow and does not rely on broad keyword OR matching.

### `enrich_company()`

Calls OpenRouter with `openrouter:web_search` enabled. The model returns JSON with:

- relevance score
- funding and company size hints
- recent news
- sentiment
- leadership
- traffic
- candidate job postings

The code clamps the score and sentiment before storing them.

### `discover_contacts()`

Uses Hunter `Domain Search` to find people at the company domain. It filters for India-based HR, TA, and hiring-manager titles, with no broad fallback to random people.

### `smtp_ping()`

Checks deliverability through MX lookup plus `RCPT TO`. It returns one of:

- `valid`
- `risky`
- `invalid`
- `unknown`

## Database writes

The CLI writes directly to Supabase Postgres using `psycopg`.

Important tables touched in Phase 1:

- `campaigns`
- `agent_runs`
- `companies`
- `company_snapshots`
- `company_news`
- `job_postings`
- `opportunities`
- `contacts`
- `contact_emails`
- `email_verifications`
- `opportunity_contacts`
- `events`

## Current behavior choices

- OpenRouter default model is set from `OPENROUTER_MODEL`, and `.env` currently points it at a free model.
- Email verification uses SMTP ping only.
- Company discovery is limited to India.
- Contact discovery is restricted to India and biased toward HR / TA / hiring-manager titles, not generic employees.
- Serper is used as a fallback search layer for public careers and ATS pages when Hunter returns too few contacts.
- The Serper fallback only runs when `SERPER_API_KEY` is set.
- The CLI is still monolithic on purpose, so Phase 1 can be split into files later without changing behavior.

The LLM pre-pass produces a `search_plan` with:

- `query`
- `keywords`
- `job_titles`
- `rationale`

The query comes from the LLM and is sanitized before being sent to Hunter, alongside the India filter. The raw resume and project files are only used as LLM input, not as hardcoded signal extractors.

## Output shape

The CLI prints one JSON object with:

- `role_prompt`
- `search_plan`
- `filters`
- `campaign_id`
- `run_id`
- `discovery_meta`
- `results`

Each item in `results` includes:

- the normalized company record
- the raw Hunter discovery row
- the full company intelligence payload
- the India-only role postings
- the filtered HR/TA contacts with emails and verification detail
- the `opportunity_id`

## Known caveats

- Hunter plan limits can change what query parameters are accepted.
- SMTP ping is only a signal, not a guarantee.
- The OpenRouter output is expected to be JSON, but the code still has fallback handling if the model returns extra text.
