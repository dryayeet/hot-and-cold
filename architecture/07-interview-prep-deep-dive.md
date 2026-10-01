# Stage 7: Interview Prep Deep-Dive

Sources: `Outreach agent.pdf`, sections "Layer 7: Interview Prep Deep-Dive", "Phase 9: Interview Prep". Grounded in that PDF, as revised by lemon on 2026-10-01 (no Claude API, no Google Sheets, no Google Drive).

Part of the LangGraph agent: this stage is a node/subgraph in the graph.

## Goal

Detailed company, role, and interview research after a positive response. This stage is conditional: it triggers only when a reply classifies as an interview request or a forward to a recruiter.

## Trigger

- Interview request, OR
- Forwarded to recruiter

(Both arrive via Stage 6 classification.)

## Research deliverables

### 1. Company deep-dive

- Web search: company news, recent announcements, funding rounds
- Extract: size, locations, employee count, valuation, growth rate
- Leadership: founder bios, backgrounds, investor profiles
- Products: what they build, market position, recent launches
- Culture: Glassdoor score, Blind reviews, employee sentiment
- Hiring: recent hiring announcements, team expansion
- Red flags: layoffs, scandals, turnover rates
- Timeline: when was funding announced, when did they last hire
- Compile: 2-3 page summary into the Sheet

### 2. Role deep-dive

- Job description deep analysis (if available)
- Similar roles at the company: what do people in this role actually do
- Tech stack: languages, frameworks, tools
- Team structure: who is the manager, team size
- Career progression: where do people move after this role
- Sentiment: Blind/Glassdoor posts about the role
- Growth potential: do people get promoted from it

### 3. Your fit analysis

- Why you fit the company (mission, tech, growth stage)
- Why you fit the role (skills, projects, interests)
- What to emphasize in interviews: strongest selling points
- Gaps to address, if any, and how to talk about them
- Questions to ask them (showing research and interest)

### 4. Interview structure

- Research sources: Glassdoor, Blind, LeetCode company forums
- Extract: number of rounds, round names (screening, coding, design, system design, etc), format (online, in-person, async), what each round asks
- Patterns: common questions, interview style
- Timeline: interview length, spacing between rounds
- Estimated prep time

### 5. Prep plan

- Week-by-week study guide
- Mock interview topics
- Resources: LeetCode problems, system design guides
- Top 10 questions they typically ask

## Output

Research is written to **local markdown files** in a per-company prep folder (e.g. `prep/<company>/...`, mirroring the resume_lab convention; **AMBIGUITY: exact file structure undecided, tracked in todo.md**), with pointers (file paths) recorded in the database (`interview_prep_packs`, `interviews`; see `08-database-schema.md`) under the prep fields: company deep-dive, role deep-dive, fit analysis, interview structure, top 10 questions, prep plan, interview schedule once known.

## HITL gates

None enforced by the agent here beyond logging; prep consumption is human. Interview scheduling dates are recorded in the DB as lemon confirms them.

## Tools

- **OpenRouter API** (lemon's key, model TBD) with web search (native or the `web` plugin / Exa engine, see Stage 1 for grounded plugin details) as the research engine. No Claude API anywhere in this project
- **Supabase Postgres** for the prep field pointers
- **Local markdown files** for the prep content itself. No Google Sheets, no Google Drive (lemon, 2026-10-01)

## Future roadmap items extending this stage

- Interview prep predictor: predict what they'll ask, fine-tuned on Blind/Glassdoor data (Phase 5)
- Interview scheduling: auto-check calendar and suggest times when a request arrives (Phase 6)
- Interview notes: AI transcription highlighting key questions and answers (Phase 6)
- Offer letter analyzer and negotiation drafting (Phases 4 and 6)
- Slack/Discord notifications: "Interview in 3 days" (Phase 4 / v2.0)
