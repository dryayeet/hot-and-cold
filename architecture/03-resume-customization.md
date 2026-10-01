# Stage 3: Resume Customization

Sources: `Outreach agent.pdf`, sections "Layer 3: Resume Customization", "Phase 3: Resume Customization", "Risk Mitigation: Resume PDF Generation Fails". Plus operating discipline imported from the resume_lab `CLAUDE.md`, per lemon's instruction. Revised by lemon on 2026-10-01: no Google Drive for now; PDF tooling to be validated when this stage is built; `pagecount.py` will be provided by lemon.

Part of the LangGraph agent: this stage is a node/subgraph in the graph.

## Goal

Tailor the resume to each high-match company without breaking format or layout. The output is a customized, guaranteed single-page PDF per company.

## Inputs

- `base_resume.tex` (validated in Phase 1)
- `projects_and_exp.md`
- Match score, keyword gaps, and reasoning from Stage 2 (Sheet columns R, S)

## Process (per high-match company)

### 1. Analyze the JD

- Extract required skills, tech stack, keywords
- Compare against the current resume
- Identify missing keywords and underemphasized skills

### 2. Edit the LaTeX

Strategy per the PDF: preserve structure, nudge content.

- Editable blocks: skill bullets, experience descriptions, projects
- Rewrite to emphasize job-relevant achievements
- Preserve: section headers, formatting, fonts, spacing
- Keep: overall structure (Education, Experience, Projects, Skills)

The PDF's worked example:

- Before: "Built a real-time data pipeline"
- After: "Built a real-time data pipeline in Apache Kafka and Python processing 100k+ events/sec for ML model inference"
- Rule: the specifics are added only if the JD actually mentioned "Kafka" + "real-time"

### 3. Compile and validate

**Toolchain decision (2026-10-01, lemon approved):** the PDF originally specified `pdflatex`/`latexmk` plus a PyPDF2/pdfplumber page-count check. That is superseded by the resume_lab-proven toolchain:

- Compile: `tools/tectonic.exe out/<name>.tex --outdir out` (Tectonic v0.17.0, runs XeTeX; `main.tex` keeps its `\ifPDFTeX` guards, do not remove them)
- One-page gate: `python tools/pagecount.py out/<name>.pdf`, exits 1 unless the PDF is exactly one page. **`pagecount.py` will be provided by lemon** (it is not in this repo yet)

**AMBIGUITY: the PDF toolchain (tectonic binary, pagecount.py) has not been validated inside this repo yet. First task when building this stage: bring the tools in, compile a sample, and verify the gate. Tracked in todo.md.**

If the output exceeds one page, in this order (from resume_lab CLAUDE.md, matching the PDF's condense loop):

1. Tighten wording (content-preserving, do this before cutting facts)
2. Drop the weakest bullet from a multi-bullet entry
3. Drop the least JD-relevant project entirely
4. Compress the skills block by merging categories
5. Last resort: `\vspace` nudges or `\small`, never below 10pt

Recompile and re-run the gate after each change. If still over one page: flag for manual review (per the PDF, "shouldn't happen", and never auto-send a broken PDF).

### 4. Store

- Save PDF as `resume_CompanyName.pdf` (mail stage names the attachment `Prajwal_Pandey_[CompanyName].pdf`)
- Store locally in the repo output area (e.g. `out/resumes/`). No Google Drive upload at this stage (lemon, 2026-10-01); the DB stores the local path, and the Drive/object-storage question is revisited at the Supabase migration
- Log the customizations applied to the database (`resume_versions`, with every bullet traced to a fact in `resume_claims`; see `08-database-schema.md`)

## Anti-hallucination constraints (imported from resume_lab CLAUDE.md)

These govern what the agent may write into a customized resume:

1. **The One Rule:** every claim must trace to a line in `FACTS.md`. Not "similar to", not "reasonably implied by". If a JD asks for something absent from FACTS.md, leave it out and report the gap. Never write a plausible-sounding bullet.
2. **Research informs selection and wording only.** A keyword found online that is not backed by FACTS.md does not go on the resume.
3. **Keyword bait:** JD says Kubernetes, FACTS.md has Docker and AWS: write Docker and AWS, flag the gap (it is already in Sheet column S from Stage 2).
4. **Metric drift:** numbers are copied exactly, "94%" never becomes "~95%" or "over 90%".
5. **No scope inflation:** built stays built, contributed stays contributed, no implied seniority, no "led a team".
6. **Title creep:** job titles character-exact.
7. **Layout traps pagecount cannot catch:** heading/date collisions in `\resumeProjectHeading` and `\resumeSubheading` rows (keep the left side under roughly 75 characters), swallowed `%` from unescaped percentages (escape `%`, `&`, `#`, `_`, `$`). Only reading the compiled PDF catches these, so the verification step must include reading the PDF, not just running pagecount.
8. **Escalation on ambiguity:** if a pasted or edited version conflicts, lemon's version wins on facts, the verified repo version wins on code-verified claims.

## DB fields touched (formerly Sheet columns; schema discussion pending, see `05-master-database.md`)

- Resume Customizations Applied (bullet point list)
- Customized Resume Link (local filesystem path for now)

## Tools

- Parsing/editing: `pylatexenc` / regex
- Compile: `tools/tectonic.exe` (see toolchain decision and validation ambiguity above)
- Validation: `tools/pagecount.py` (to be provided by lemon); PyPDF2/pdfplumber remain available for metadata extraction per the PDF
- Storage: local filesystem (or Supabase Storage, open question in `08-database-schema.md`) + Supabase Postgres. No Google Drive for now

## HITL gates

- Compile failure or persistent overflow: fall back to manual review, never auto-send a broken PDF
- The PDF also requires page-count validation to pass before Gmail draft creation in Stage 4

## Risks (from the PDF)

- Resume PDF generation fails: fallback to manual review, no auto-send of broken PDFs, always validate page count before draft creation
