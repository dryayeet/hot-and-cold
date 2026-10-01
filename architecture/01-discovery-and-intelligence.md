# Stage 1: Discovery & Intelligence

Source: `Outreach agent.pdf`, sections "Layer 1: Discovery & Intelligence", "Phase 1: Initialization", "Phase 2: Company Discovery", as revised by lemon on 2026-10-01 (OpenRouter instead of Claude API, Supabase Postgres instead of Google Sheets, deliverability-focused email verification).

Part of the LangGraph agent: this stage is a node/subgraph in the graph.

## Goal

Find 50 relevant hiring companies in one workflow run, extract decision-maker contacts, and build a structured company profile for each. No company enters the pipeline without a row in the local database.

## Inputs (Phase 1: Initialization, user-provided)

1. `base_resume.tex` (LaTeX)
2. `projects_and_exp.md` (projects and experience markdown)
3. `role_interest_prompt` in natural language, e.g. "AI/ML engineer roles at early-stage startups with <500 people"

The agent validates all three before starting:

- Resume: parse the LaTeX, confirm the sections Experience, Skills, Projects exist
- Projects: parse the markdown, extract key technologies
- Prompt: analyze for hiring signals (seniority, company stage, tech)

## Revised flow (lemon, 2026-10-01)

From the three inputs, the default LLM (`gpt-5.4-mini`) drives role-opening search: it searches for companies hiring for the described roles. Two tracks then run, in parallel where possible:

1. **Company intelligence gathering** per company found (funding, growth, news, sentiment, leadership, traffic)
2. **Contact discovery**: find HR / TA / hiring-manager emails, either by the LLM (web search) or via a dedicated email-finder tool such as Hunter.io's Email Finder (name + domain, most likely address) or Domain Search (all addresses for a domain, filterable by department=hr and seniority). **AMBIGUITY: which method, LLM search vs dedicated finder API, or a hybrid, is undecided. See todo.md.**

Then **email validation**, then the outputs feed Stage 2 (matching).

## Email validation: deliverability, not just syntax

Per lemon, the question is "is this email real", because LLM-extracted addresses can be hallucinated or stale (person left, domain dead). Syntax checking alone is insufficient.

For now, use **SMTP-level ping** (RCPT TO handshake against the MX host) as the deliverability check: free, no third party, but catch-all domains can still look valid and aggressive pinging can get the IP flagged. Treat results as a signal, not truth.

**AMBIGUITY: verification method is intentionally SMTP-only for now.** Syntax checks remain as a free pre-filter regardless.

## Process (per company)

### 1. Web search pipeline

Generate searches from the role prompt. The PDF's example queries:

- "AI/ML engineer roles hiring startup <500 employees 2026"
- "Series A/B funding announcements AI startups India 2026"
- "ML engineer job openings early-stage tech startups"

Parse results for company names, job board links, and careers pages.

### 2. Company intelligence gathering

- Funding: recent Series A/B/C announcements
- Growth: headcount trends, hiring velocity (roles posted per week)
- News: recent launches, layoffs, product announcements, with timestamps
- Sentiment: Glassdoor and Blind scores, public perception
- Leadership: founder backgrounds, investor profiles
- Traffic: Similarweb or Crunchbase metrics

Each company also gets a relevance score (1-10) against the role prompt; keep only companies scoring 6 or higher.

### 3. Contact extraction

- HR, TA, and hiring managers, with titles and profile links (LinkedIn search, careers pages, or finder API, per the ambiguity above)
- Then run email validation (deliverability) on every candidate address

### 4. Persist

Write the results to Supabase Postgres: global `companies`, `company_snapshots`, `company_news`, `job_postings`; per-user `opportunities`, `contacts`, `contact_emails`, `email_verifications` (full design in `08-database-schema.md`, pending approval). No Google Sheets or Google Drive at this stage.

## Output

A list of 50 companies with structured data: name, funding round, growth signal, leadership, sentiment, email contacts, each email carrying a validation status.

## Tools

- **OpenRouter API** (lemon's key; default model `gpt-5.4-mini`). Use the `openrouter:web_search` server tool for live web search; it is the preferred surface and lets the model decide when to search. For models without native search, OpenRouter falls back to Exa by default (`engine: auto`), with optional `exa`, `parallel`, `firecrawl`, or `perplexity` engines and domain filtering support.
- **Contact discovery**: LLM web search and/or Hunter.io Email Finder / Domain Search (AMBIGUITY, see above)
- **Email verification**: SMTP ping only for now; `email-validator` kept only as a syntax/DNS pre-filter
- **Supabase Postgres** for persistence (via the Supabase Python client or a direct Postgres connection; design in `08-database-schema.md`, pending approval)

## HITL gates

None in this stage. The first human decision point is the matching quality gate (Stage 2) and mail approval (Stage 4).

## DB fields touched (formerly Sheet columns A-Q; schema discussion pending)

- Identification: company name, role title, company URL, job board link
- Company intelligence: funding status, company size, locations, growth signal, recent news, sentiment score, founders/leadership, public valuation/revenue
- Contacts: hiring manager name/title, HR/TA email, email validation status, LinkedIn profile URL

## Risks and mitigations (from the PDF)

- Hiring manager doesn't exist: validate the LinkedIn profile is real before extracting an email; fall back to the general HR email if the lookup fails
- Blacklisting prevention starts here: only extracted personal email addresses are ever used, never company domains

## Future roadmap items that extend this stage (Phase 2 features)

- Investor tracking: map investors to portfolio companies to recent funding, as a hiring signal
- Hiring momentum scoring: track companies posting new roles daily, hiring fast correlates with responding
- Response time patterns: log which companies reply in 24 hours vs 2 weeks
