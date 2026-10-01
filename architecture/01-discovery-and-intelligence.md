# Stage 1: Discovery & Intelligence

Source: `Outreach agent.pdf`, sections "Layer 1: Discovery & Intelligence", "Phase 1: Initialization", "Phase 2: Company Discovery", as revised by lemon on 2026-10-01 (OpenRouter instead of Claude API, SQLite instead of Google Sheets, deliverability-focused email verification).

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

From the three inputs, the LLM drives role-opening search: it searches for companies hiring for the described roles. Two tracks then run, in parallel where possible:

1. **Company intelligence gathering** per company found (funding, growth, news, sentiment, leadership, traffic)
2. **Contact discovery**: find HR / TA / hiring-manager emails, either by the LLM (web search) or via a dedicated email-finder tool such as Hunter.io's Email Finder (name + domain, most likely address) or Domain Search (all addresses for a domain, filterable by department=hr and seniority). **AMBIGUITY: which method, LLM search vs dedicated finder API, or a hybrid, is undecided. See todo.md.**

Then **email validation**, then the outputs feed Stage 2 (matching).

## Email validation: deliverability, not just syntax

Per lemon, the question is "is this email real", because LLM-extracted addresses can be hallucinated or stale (person left, domain dead). Syntax checking alone is insufficient.

Grounded options:

- **SMTP-level ping** (RCPT TO handshake against the MX host): free, no third party, but catch-all domains accept everything and report invalid addresses as valid, and aggressive pinging can get your IP flagged. Treat results as a signal, not truth.
- **Verifier API** (e.g. Hunter.io Email Verifier: returns a deliverability judgment for the address; alternatives in the same category: ZeroBounce, NeverBounce): paid per check, more reliable, catches disposable/role-based/stale signals better.

**AMBIGUITY: verification tool and method undecided (self-hosted SMTP ping vs paid API vs hybrid: cheap ping first, API only for uncertain results). See todo.md.** Syntax checks remain as a free pre-filter regardless.

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

Write the company profile row to the local SQLite database (schema in `05-master-database.md`, which now tracks the target fields; table structure is flagged for discussion). No Google Sheets or Google Drive at this stage; the database migrates to Supabase Postgres later.

## Output

A list of 50 companies with structured data: name, funding round, growth signal, leadership, sentiment, email contacts, each email carrying a validation status.

## Tools

- **OpenRouter API** (lemon's key; specific model TBD, see todo.md). Requirements: web search ability, either a model with native web search or OpenRouter's `web` plugin. Grounded details of the OpenRouter web story:
  - `:online` model-slug suffix or the `plugins: [{id: "web"}]` parameter activates search for any model
  - For models without native search, the plugin is powered by **Exa** (auto mode by default; modes instant/fast/auto/deep-lite/deep/deep-reasoning, from $0.007 per request, 10 results included)
  - Engines: `native`, `exa`, `firecrawl` (BYOK), `parallel`, `perplexity`; domain filtering via `include_domains`/`exclude_domains` (Exa supports both simultaneously)
  - Newer alternative: the `openrouter:web_search` server tool, which lets the model decide when and how often to search rather than one forced search per request
- **Contact discovery**: LLM web search and/or Hunter.io Email Finder / Domain Search (AMBIGUITY, see above)
- **Email verification**: SMTP ping and/or verifier API (AMBIGUITY, see above); `email-validator` kept only as a syntax/DNS pre-filter
- **SQLite** (stdlib `sqlite3`) for persistence

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
