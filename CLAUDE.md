# resume_lab — Operating Instructions

Read this file completely before generating any resume. It exists to stop hallucination.

## Hard Constraints

1. **Every claim must trace to a line in `FACTS.md`.** (See below.)
2. **The output PDF is always exactly one page.** Non-negotiable, no exceptions unless
   lemon explicitly asks otherwise. If content overflows, cut the least JD-relevant bullet
   and recompile. Never ship a 1.2-page resume. Verify by reading the compiled PDF, not by
   estimating.

Check it mechanically, every time:

```bash
python tools/pagecount.py out/<name>.pdf   # exits 1 if not exactly one page
```

### Fitting to one page

In rough order of preference when trimming:
- Drop the least JD-relevant project entirely
- Drop the weakest bullet from a multi-bullet entry
- Tighten wording (this is content-preserving, do it before cutting facts)
- Compress the skills block by merging categories
- Last resort only: `\vspace` nudges or `\small`. Do not shrink below 10pt or squeeze
  margins to the point the page looks cramped.

## The One Rule

**Every claim in a generated resume must trace to a line in `FACTS.md`.**

Not "similar to" a line. Not "reasonably implied by" a line. Traceable to one.

If a JD asks for something not in `FACTS.md`, the answer is to leave it out and tell lemon
about the gap. It is never to write a plausible-sounding bullet.

---

## Files

| Path | Role | Editable |
|---|---|---|
| `FACTS.md` | Single source of truth for all content | Only when lemon supplies new facts |
| `main.tex` | Template. Preamble + macros | Preamble frozen; body is rewritten per JD |
| `bases/*.pdf` | Four original resume variants | Read-only, reference |
| `tools/tectonic.exe` | LaTeX compiler (v0.17.0, standalone) | Do not modify |
| `tools/pagecount.py` | One-page gate. Exits 1 unless the PDF is exactly one page | Do not modify |
| `out/` | Generated `.tex` and `.pdf` | Working output |
| `archive/` | Previous generations, `YYYY-MM-DD_<Company>_<Role>.{tex,pdf}` | Append-only |
| `prep/<company>/` | Interview prep: research records, drill files | Per company |

`other_things.txt` was the original raw notes dump. It has been fully absorbed into `FACTS.md`
and deleted. `FACTS.md` is now the only content source.

JD files (PDF/DOCX) arrive in the repo root, get used, and are cleaned up by lemon. Do not
assume any particular one is still present.

### Outputs

- **Resume**: `out/Prajwal_Pandey_<Company>_<Role>.tex` → same-named `.pdf`
- **Cover letter** (when asked): `out/Prajwal_Pandey_<Company>_CoverLetter.tex`.
  Reuse the resume preamble and the same centred name header so they read as a set, then
  `\setlength{\parskip}{7pt}`, `\parindent 0pt`, and plain paragraphs. One page, same gate.
- Copy both `.tex` and `.pdf` into `archive/` with the date prefix after every delivery.

## Build Command

```bash
cd "c:/Users/91626/OneDrive - Manipal Academy of Higher Education/Desktop/resume_lab"
./tools/tectonic.exe out/<name>.tex --outdir out
```

First run downloads packages from the network and takes ~30s. Later runs are ~2s.

### Template constraint, already handled

Tectonic runs **XeTeX**, which has no `\pdfglyphtounicode`. `main.tex` has been patched to
guard the pdfTeX-only lines behind `\ifPDFTeX`. Verified: output is pixel-identical to
`bases/Prajwal_Pandey_CV.pdf`. **Do not remove those guards** or compilation breaks.

---

## Procedure

### 1. Read the JD properly

Extract and write down, before touching LaTeX:
- Role archetype: SDE / AI-ML / Data / Research
- Must-have technologies, named explicitly
- Nice-to-haves
- Seniority and scope signals
- Domain (fintech, health, infra…)
- Anything unusual worth mirroring in wording

### 2. Pick the base variant

| JD archetype | Start from | Anchor |
|---|---|---|
| Backend / SDE / Platform | `CV2.pdf` | Gravity backend bullets, Super Strykez |
| AI / ML Engineer / LLM | `CV.pdf` | Gravity AI bullets, RAG project |
| Data Science / Analytics / DE | `CV1.pdf` | Pipeline + modeling bullets |
| Research / Applied Scientist | `CV_R.pdf` | Skills-high layout, Facial Affect, PEFT |

Mixed JDs: pick the dominant archetype, borrow sections from the others. State the choice
and the reasoning to lemon before building.

### 3. Research the role

Web-search the company and role for real signal: what the team actually builds, the stack,
how they describe the work, vocabulary that recurs in their engineering posts. Use it to
choose **which existing facts to surface and how to phrase them**.

Research informs *selection and wording*. It never becomes a source of content. A keyword
found online that is not backed by `FACTS.md` does not go on the resume.

### 4. Select content

- Lead with the fact that most directly answers the JD's top requirement.
- Prefer bullets carrying real numbers, they are all in `FACTS.md` already.
- Cut anything the JD gives no weight to. One page is the target.
- Skills section: reorder and regroup so JD-relevant categories come first. Never append a
  technology absent from the inventory.

### 5. Write the LaTeX

- Copy the `main.tex` preamble verbatim, every macro, through `\begin{document}`.
- Write only the body.
- Escape: `%` → `\%`, `&` → `\&`, `#` → `\#`, `_` → `\_`, `$` → `\$`.
  ⚠️ `other_things.txt` contains raw `100%` and `89.3%`; these **must** be escaped, an
  unescaped `%` silently comments out the rest of the line.
- Use `\texttt{}` for code identifiers (`asyncio.gather`, `AffectFusionEngine`).
- Save to `out/Prajwal_Pandey_<Company>_<Role>.tex`.

### 6. Compile and verify

Compile, run `tools/pagecount.py`, then **Read the generated PDF** and confirm:
- [ ] Exactly one page (unless lemon asked otherwise)
- [ ] **Project/experience heading lines do not collide with their right-hand date.**
      The `\resumeProjectHeading` row has no wrapping: an over-long title + tech-stack
      string runs into the date and clips at the margin. It compiles without error and
      `pagecount` still passes, so **only reading the PDF catches it.** Seen in the
      SolarWinds build. Keep title + tech stack under roughly 75 characters.
- [ ] No overfull-hbox text bleeding into the margin
- [ ] Every bullet traces to `FACTS.md`
- [ ] All percentages rendered, not swallowed by an unescaped `%`
- [ ] Dates consistent with `FACTS.md`, conflicts resolved per its defaults
- [ ] Contact line intact

Never report success without reading the compiled PDF. Compilation succeeding is not the
same as output being correct.

### When it compiles to 2 pages: READ IT FIRST

The single most expensive mistake in this repo is trimming blind. Every build that took four
or five compile cycles did so because the fix was guessed instead of located.

**Read the PDF the moment `pagecount` says 2.** You need to know two things that only the
rendered page shows: exactly where page 1 breaks, and how much whitespace is left at its
bottom. Then trim that amount, once.

Overflow is almost always one of these, in observed frequency order:

1. **A skills line that wraps.** Each wrapped line silently costs a rendered line, and 2-3
   wrapping at once is the usual cause of a whole spilled Skills block. Shortening the longest
   category is the cheapest possible fix. Check every skills line renders on one line.
2. **A 4-line summary that should be 3.**
3. **Bullets running to 3 lines that could be 2.** Tighten wording first; it preserves content.
4. **One project too many.** Structural, do it last.

### Layout defects `pagecount` cannot catch

Both of these compile cleanly and pass the one-page gate. Only reading the PDF finds them.

- **Heading/date collision.** `\resumeProjectHeading` and `\resumeSubheading` rows do not wrap.
  An over-long left side runs into the right-hand date and clips at the margin. Seen three
  times: a project title + tech stack (SolarWinds), an over-long PoR subtitle (Impact
  Analytics, rendered `Nov 2024 – Oc`), and a full-length degree name against
  `Expected 2027` (Cargill, rendered `CGPA: 8.5Aug. 2023`).
  **Keep the left side under roughly 75 characters.** If the date string is long, shorten the
  left side, e.g. `B.Tech in Computer Science and Engineering` instead of `Bachelor of
  Technology in...`.
- **Swallowed `%`.** An unescaped `%` comments out the rest of the line. The number vanishes
  and nothing errors.

### Shell gotchas when writing `.tex` from Bash

If you write LaTeX through a bash heredoc in this environment, two things bite:

- **`\\` collapses to `\`.** The skills block then renders as one run-on paragraph with no
  line breaks. Workaround: write a placeholder such as `%%BR%%` at those line ends, then
  substitute it in a short Python pass (`s.replace('%%BR%%', chr(92)*2)`). Verify by reading
  the PDF, the failure is silent.
- **Apostrophes abort the heredoc.** `Bachelor's`, `Master's` etc. break quoting and the
  command dies with `unexpected EOF`. For prose-heavy files (markdown, cover letters) use the
  Write tool instead of a heredoc.
- Inside Python string literals, `\r` in `\resumeItem` is read as a carriage return. Build
  such strings with `chr(92) + 'resumeItem'`.

Faster than re-copying `main.tex`: seed a new build from the last one by taking everything down
to the end of the centred name header, then appending a fresh body.

```bash
grep -n "end{center}" out/<previous>.tex        # find the header end, do not assume a number
head -n <that line> out/<previous>.tex > out/<new>.tex
```

Then append the body and rewrite the `% TARGET: / % BASE: / % THEME:` comment block at the top
so the new file records its own reasoning.

### 7. Report

Tell lemon:
1. Which base was chosen and why
2. What was included, what was cut, and the reasoning
3. **Gaps**: JD requirements with no backing in `FACTS.md`, stated plainly
4. Any `FACTS.md` warning that came into play

---

## Anti-Hallucination Checklist

Run before every delivery. Any "no" means stop and fix.

1. Can I point to the `FACTS.md` line behind every bullet?
2. Does every number match `FACTS.md` exactly, no rounding, no upgrading?
3. Have I avoided inflating scope (built → led, contributed → owned)?
4. Are job titles, company names, and dates character-exact?
5. Have I added zero technologies absent from the skills inventory?
6. Did I read the compiled PDF rather than assuming it is fine?
7. Have I told lemon about every gap instead of papering over it?

### Failure modes to watch for

- **Keyword bait.** The JD says Kubernetes; `FACTS.md` has Docker and AWS. Write Docker and
  AWS, flag the gap. Do not write Kubernetes.
- **Metric drift.** "94% accuracy" must not become "~95%" or "over 90%".
- **Merge inflation.** Two separate facts combined into one bigger-sounding claim.
- **Title creep.** "Backend AI Intern" stays "Backend AI Intern".
- **Implied seniority.** No "led a team" anywhere; nothing in `FACTS.md` supports it.

---

## Known Data Conflicts

**`FACTS.md` is authoritative. Read its ⚠️ / ✅ / 🔴 markers directly.** Do not trust a
duplicated list here, an earlier copy of this section went stale and contradicted `FACTS.md`
on the Gravity dates. What follows is orientation only.

Markers used in `FACTS.md`:

| Marker | Meaning |
|---|---|
| ✅ | Confirmed by lemon on a date. Overrides anything in the PDF bases. Use freely. |
| ⚠️ | Unresolved or conditional. Confirm with lemon before putting it on a resume. |
| 🔴 | A claim that was **found to be false**. Never reinstate it. |

Standing cautions as of 2026-08-06 (verify against `FACTS.md`, do not rely on this list):

- **C++ is inventory-only.** It is in the Languages list of all four bases and lemon has
  confirmed it, so it may be listed. But **no bullet or project on record is written in C++**.
  Never imply shipped C++. Pair it with **GATE CSE 2026** and coursework, which is real
  evidence of the fundamentals.
- **Spark / SparkSQL / dbt**: skills-list only, no backing bullet. Confirm before use.
- **Vibe ETL framing**: appears only in `CV1.pdf`, uncorroborated.
- **Composio** on the agent project: in `CV2.pdf`, absent from lemon's own architecture
  account. Confirm before use.
- **The "most human-feeling AI voice" line**: qualitative and self-reported.
- Dates were all resolved by lemon on 2026-08-06 and **supersede every PDF base**. The bases
  are wrong about them. Take dates from `FACTS.md` only.

### The bases can be wrong, not just conflicting

`FACTS.md` was originally consolidated from the four base PDFs, so **an error in a base became
an error in `FACTS.md`**. This is not hypothetical: the RAG project claimed *hybrid retrieval
(BM25 + dense)* and *audio queries*, and reading the actual repository showed the code does
dense-only FAISS retrieval with no audio path anywhere. Both claims were live interview risks.

**Rule: if a project has a source repo, verify the claims against the code before using them.**
Read the actual implementation file, not just the README. Then record the finding in `FACTS.md`
with ✅ or 🔴 so the check is never repeated. Projects verified this way so far: `peterbot`
(two claims false, removed) and `temporal-lemon` (all claims held, and were understated).

---

## Working Preferences

- No em dashes in prose written for lemon.
- **When lemon names a company and supplies or points at a JD, build it.** Research, choose the
  base, build, verify, then report the choice and the gaps. Do not stop to ask permission first.
  Ask only when the JD is genuinely ambiguous about the archetype, or when a decision would
  change the content materially (which roles to include, which dates are correct).
- State gaps directly. A resume that omits a requirement is fixable; one that invents
  experience is a problem in an interview.
- Lemon edits the `.tex` directly, sometimes while you are working. If a pasted version
  conflicts with yours, **keep both sets of changes**: theirs wins on facts (dates, titles,
  naming), yours wins on anything you verified against a source repo. Say which is which.
- Push back is usually about **under-selling a real match**, not about accuracy. If lemon says
  the fit is stronger than the draft shows, re-read `FACTS.md` before rewriting: the material
  is normally already there and simply was not surfaced.

## Read the whole JD, not the job title

Two builds turned on this and both would have gone wrong otherwise:

- A file named `ImpactAnalyticsJDAIAnalyst` had **Title: Business Analyst** and a primary duty
  of *troubleshooting and resolving issues*. The "AI" was the product domain, not the job.
- Procol advertised a plain **Backend Engineer Intern**, but the company builds an agent
  orchestration platform, which made the agentic work a domain match rather than a distraction.

Read the responsibilities, the company's own product description, and the stated seniority
before choosing a base. Check the **required vs preferred** split too: the required list is the
screen, the preferred list is the differentiator, and they often want very different things.

## Assets worth leading with

- **GATE CSE 2026: Qualified.** Independent verification of algorithms, OS, DBMS and networks.
  Lead with it on anything that tests fundamentals (SolarWinds, Amazon, Philips, HyperVerge)
  and on any programme demanding a "strong academic track record". It is the best available
  support for the C++ and CS-foundations claims.
- **IEEE Chair** (45% membership growth). Include whenever a JD names leadership,
  extracurriculars, communication or working across diverse teams. Unilever GDT made it a
  stated entry requirement.
- **Two internships at startups**, both on products in production. Say "commercial product"
  where a JD uses that phrase.

## Interview prep files

When lemon asks for prep material, put it in `prep/<company>/`. Reference pack: `prep/goldmann/`
(built 2026-09-05, eight files). Match its shape.

### Pack structure

| File | Contents |
|---|---|
| `<company>.md` | Master record: role reality, evidence on how rounds ran (table), day-by-day plan sized to the deadline, resume hooks, links by category, one-line verdicts. Index every other file at the top. |
| domain core (e.g. `finance-ops.md`) | The knowledge the role tests, written to be read once and rehearsed aloud. Ends with a spoken self-test and a links section. |
| round-specific (e.g. `gd.md`) | Format, scoring rubric, frameworks, phrase toolkit, a fully worked example, topic bank, mistakes ranked by damage, day-before checklist, links. |
| `interview-questions.md` + `interview-answers.md` | Questions file lists what gets asked, grouped by section. Answers file mirrors the sections with model answers and why they work. Two files, not one. |
| `quiz-<topic>.md` (several) | MCQ drills, one per topic cluster. See format below. |

Do not ship a "bare minimum" pack. Lemon's explicit feedback on the first goldmann draft was
that compressed files are not useful; depth organised under headings beats brevity. A domain
core file should run 12–15KB, a round file 10KB+.

### Quiz format (lemon's rules, 2026-09-05)

- **No correct answer marked in the question body.** No bold, no inline `**B** —` after the
  options. Options on their own lines: `- A.`, `- B.`, `- C.`, `- D.`.
- Each question carries a short topic tag in italics after the number: `**Q7.** *(options)*`.
- Header block: question count, time budget, closed-book note.
- **Answer key at the end only**, as a numbered list where every line has the letter **and a
  one- to two-sentence explanation**. Then a compact `**Key row:**` (`1B 2C 3A ...`), the
  `**Spread:**`, and score bands telling the reader what to reread per band.
- **Balance the correct-answer distribution across A/B/C/D.** A first pass once landed 18 of 30
  on B with D never correct, which trains "guess B". Scenario quizzes drift to B because the
  "best judgment" option gets written second; shuffle option order per question to fix it.
- Verify mechanically before shipping, every quiz, every time. Pattern that works:

```python
qs   = re.findall(r'^\*\*Q(\d+)\.\*\*', s, re.M)                    # question count
expl = re.findall(r'^(\d+)\. \*\*([A-D])\*\*', keysection, re.M)    # explained key
row  = re.findall(r'(\d+)([A-D])', keyrow_line)                     # compact key
# assert len(qs)==len(expl)==len(row); expl letters == row letters; no r'^\*\*[A-D]\*\* ' in body
```

### How to research a company/role for prep

Run the searches in one parallel batch, then fetch the two or three richest hits:

1. `"<company>" <role> interview experience India campus` — GfG, Medium, Quora, Glassdoor,
   NodeFlair, CleverPrep, Prosple. GfG on-campus write-ups are the most reliable anchor for
   round structure and cut ratios.
2. `"<company>" <round name> topics format` (GD, HireVue, OA, case) — hitbullseye, InterviewBit,
   Leland, and the company's own careers "prepare" page.
3. `<domain> interview questions <role>` — for the knowledge core (e.g. trade life cycle,
   system design basics, SQL). Vendor/education blogs are fine for content; cite them.
4. Current-state facts the role could touch, dated: regulator changes, rates, product
   launches. Verify anything numeric against a source dated within the month and tell the
   reader to re-verify the day before.
5. `<topic> group discussion topics 2026` or `<topic> MCQ` for drill material.

Company career portals (GS `higher.gs.com`, Oracle HCM `CandidateExperience` pages) are
JS-rendered and return an empty shell or 403. **Stop and ask lemon to paste the listing** rather
than guessing; state the sourcing caveat in the master file either way. The JD PDF, when
supplied, is authoritative over any listing summary.

### Links sections

Every content file ends with a `## Links` block grouped by purpose (interview experiences,
domain content, current affairs, video). For video, give **YouTube search phrases** in quotes
rather than individual URLs; reel and video links rot within weeks, search phrases do not.
Name the channels that were solid when checked.

### Prep for someone other than lemon

Lemon sometimes asks for prep for a friend (goldmann was for Anushka). In that case:
- Read the friend's resume and the JD first. Anchor resume hooks, STAR skeletons, and model
  answers to **their** material only. Never reference lemon's projects, FACTS.md, or history.
- Keep it "mostly general, their resume as light context" unless lemon says otherwise.
- Ask up front: days until each round, any placement-cell intel on format, and whether the
  round labels (e.g. "Technical Interview" for an Operations role) match what is actually
  tested. Then build without further questions.
