# Stage 1: Discovery & Intelligence

Source: `Outreach agent.pdf`, sections "Layer 1: Discovery & Intelligence", "Phase 1: Initialization", "Phase 2: Company Discovery". This doc is grounded in that PDF; nothing here is invented beyond it.

## Goal

Find 50 relevant hiring companies in one workflow run, extract decision-maker contacts, and build a structured company profile for each. This stage feeds every later stage: no company enters the pipeline without a row in the master Google Sheet.

## Inputs (Phase 1: Initialization, user-provided)

1. `base_resume.tex` (LaTeX)
2. `projects_and_exp.md` (projects and experience markdown)
3. `role_interest_prompt` in natural language, e.g. "AI/ML engineer roles at early-stage startups with <500 people"

The agent validates all three before starting:

- Resume: parse the LaTeX, confirm the sections Experience, Skills, Projects exist
- Projects: parse the markdown, extract key technologies
- Prompt: analyze for hiring signals (seniority, company stage, tech)

## Process

### 1. Web search pipeline

Generate searches from the role prompt. The PDF's example queries:

- "AI/ML engineer roles hiring startup <500 employees 2026"
- "Series A/B funding announcements AI startups India 2026"
- "ML engineer job openings early-stage tech startups"

Parse results for company names, job board links, and careers pages.

### 2. Company intelligence gathering (per company, 50 total)

- Funding: recent Series A/B/C announcements
- Growth: headcount trends, hiring velocity (roles posted per week)
- News: recent launches, layoffs, product announcements, with timestamps
- Sentiment: Glassdoor and Blind scores, public perception
- Leadership: founder backgrounds, investor profiles
- Traffic: Similarweb or Crunchbase metrics

Deep web search per company covers: company site, LinkedIn, Crunchbase, news. Each company also gets a relevance score (1-10) against the role prompt; keep only companies scoring 6 or higher.

### 3. Email extraction

- LinkedIn scraping: HR, TA, and hiring managers, with titles and profile links
- Careers page parsing for contact info
- Validation: syntax check on every address, optional bounce detection where possible

### 4. Persist

Write one company profile row to the master Google Sheet (schema in `05-sheets-master-database.md`).

## Output

A list of 50 companies with structured data: name, funding round, growth signal, leadership, sentiment, email contacts.

## Tools (from the PDF tech stack)

- Claude API with its built-in web search tool (primary research engine)
- Email validation: `email-validator`
- Optional, can stay manual or semi-manual per the PDF: BeautifulSoup / Scrapy for careers pages and LinkedIn, RapidAPI email finders (Hunter.io, Clearbit)

## HITL gates

None in this stage. The first human decision point is the matching quality gate (Stage 2) and mail approval (Stage 4).

## Sheet columns touched

- Identification: A (Company Name), B (Role Title), C (Company URL), D (Job Board Link)
- Company intelligence: E (Funding Status), F (Company Size), G (Locations), H (Growth Signal), I (Recent News), J (Sentiment Score), K (Founders/Leadership), L (Public Valuation/Revenue)
- Contacts: M (Hiring Manager Name), N (Hiring Manager Title), O (HR/TA Email), P (Email Validation Status), Q (LinkedIn Profile URL)

## Risks and mitigations (from the PDF)

- Hiring manager doesn't exist: validate the LinkedIn profile is real before extracting an email; fall back to the general HR email if the lookup fails.
- Blacklisting prevention starts here: only extracted personal email addresses are ever used, never company domains.

## Future roadmap items that extend this stage (Phase 2 features)

- Investor tracking: map investors to portfolio companies to recent funding, as a hiring signal
- Hiring momentum scoring: track companies posting new roles daily, hiring fast correlates with responding
- Response time patterns: log which companies reply in 24 hours vs 2 weeks
