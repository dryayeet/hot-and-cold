# Stage 2: Matching & Quality Gate

Source: `Outreach agent.pdf`, section "Layer 2: Matching & Quality Gate". Grounded in that PDF.

## Goal

Score lemon's fit for each company/role pairing, flag weak matches for review, and prevent spamming weak matches. Output a prioritized list of high-match companies (6/10 or better) ready for personalization.

## Inputs

- Company profiles from Stage 1 (funding, growth signals, sentiment)
- Base resume and parsed projects/exp (technologies, seniority signals)
- The JD or role signal found during discovery for each company

## Scoring algorithm (exactly as specified in the PDF)

For each Company + Role:

1. Parse the JD for: skills, tech stack, seniority level, responsibilities
2. Cross-reference resume + projects against JD keywords
3. Score:

| Component | Points |
| --- | --- |
| Tech stack match | 0-3 |
| Seniority alignment | 0-2 |
| Project relevance | 0-3 |
| Company growth/signal match | 0-2 |
| **Total** | **1-10** |

4. Threshold: if score < 6, flag for manual review before proceeding. This is the mechanism that "prevents spamming weak matches".

## Output

- Prioritized list of high-match companies (>=6/10) ready for resume personalization
- For flagged companies: a hold state pending manual review
- Per company: match score, keyword gaps, reasoning

## Sheet columns touched

- R: Match Score (1-10)
- S: Keyword Gaps, e.g. "Missing: Kubernetes, Docker"
- Match reasoning is logged alongside per the PDF ("Store in Google Sheet: Match score, keyword gaps, reasoning")

## HITL gates

Companies below the threshold stop here until lemon reviews them. This is the first quality gate in the pipeline and the PDF's primary defense against low response rates ("Quality gate (don't send <6/10 matches)").

## Tools

- Claude API for JD parsing and cross-referencing (LLM analysis, per the PDF's tech stack)
- Google Sheets via gspread for persistence

## Risks addressed

- Low response rate: the quality gate is the PDF's named mitigation. Weak matches never reach drafting.
- Keyword honesty: gaps found here are logged (column S), which later constrains Stage 3. A missing keyword is recorded as a gap, never fabricated onto the resume.
