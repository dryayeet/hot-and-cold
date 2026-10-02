# Email Discovery Research

## Goal

Build a practical India-only contact discovery path that can keep working when paid enrichment APIs are rate-limited.

## What We Learned

- Hunter is useful when quota is available, but the current plan can hard-stop contact discovery.
- SerpApi is a search layer, not an email finder.
- The best SerpApi use here is discovery of public company-owned pages, ATS pages, and careers surfaces.
- Open-source tools can do most of the crawling and extraction work, but they do not replace contact quality controls.

## SerpApi Tuning For This Repo

Use SerpApi to seed URLs, then scrape the pages locally.

Recommended search parameters:

- `engine=google`
- `gl=in`
- `hl=en`
- `location=India`
- `cr=countryIN`
- `safe=active`
- `filter=0` when you want broader coverage
- `no_cache=false` to reuse cached searches when possible
- `output=json`

Recommended query patterns:

- `site:{domain} "{company}" India careers`
- `site:{domain} "{company}" India recruiter`
- `site:{domain} "{company}" India talent acquisition`
- `site:{domain} "{company}" India contact`
- `site:{domain} "{company}" India team`
- `site:{domain} "{company}" India people`
- `site:{domain} (careers OR jobs OR hiring OR recruiter OR "talent acquisition" OR contact OR team OR people) India`

Practical filter rules:

- Keep `site:` scoped to the company domain.
- Accept ATS hosts such as Greenhouse, Lever, Ashby, SmartRecruiters, Workable, iCIMS, Jobvite, Taleo, BambooHR, and Recruitee.
- Do not rely only on pages whose path contains `career` or `jobs`, because many contact pages live under `contact`, `team`, `about`, or `people`.
- Prefer company-owned pages first, ATS pages second.

## Open-Source Stack

Best general-purpose stack:

- `Scrapy` for crawling
- `scrapy-playwright` for JS-heavy pages
- `lxml` or `selectolax` for fast HTML parsing
- `extruct` for JSON-LD, microdata, RDFa, and Open Graph
- `Trafilatura` for text extraction and boilerplate removal
- `email-validator` for syntax checks

Useful OSINT tools:

- `theHarvester`
- `SpiderFoot`
- `Photon`

Best browser automation tool:

- `Playwright`

## Recommended Pipeline

1. Seed URLs from SerpApi.
2. Crawl company-owned site surfaces, careers pages, team pages, contact pages, and ATS pages.
3. Extract:
   - `mailto:` links
   - visible email addresses
   - JSON-LD `ContactPoint` and `Person`
   - names, titles, and page metadata
4. Normalize and deduplicate emails.
5. Score contacts with India and hiring relevance.
6. Verify only after extraction, and keep the verification result separate from the source evidence.

## Extraction Heuristics

- Search raw HTML, not only rendered text, because many pages hide addresses in `mailto:` links.
- Parse `<title>`, page headings, and page snippets.
- Treat email patterns as hypotheses, not facts.
- Infer title from page context, but keep the inferred title separate from the source page.
- Prefer clearly hiring-related pages, but do not require the word `career` in the URL.

## Verification

Validation options, from lightest to heaviest:

- syntax check
- domain MX lookup
- optional SMTP probe

Notes:

- SMTP probing can be noisy and unreliable.
- Deliverability checks do not prove mailbox ownership.
- If the goal is safe contact enrichment, confidence scoring is better than aggressive probing.

## Risks

- Publicly visible does not mean safe to bulk collect.
- Many sites hide contacts behind JavaScript, PDFs, images, or anti-bot defenses.
- Pattern inference can produce false positives.
- ATS pages vary a lot by vendor, so one generic scraper will miss edge cases.

## Repo-Specific Recommendation

For this repo, the best path is:

- Use SerpApi only as a URL discovery layer.
- Crawl the discovered pages locally.
- Extract emails from raw HTML and page text.
- Add site-specific adapters for common ATS platforms later.
- Keep Hunter as a best-effort enrichment source, not a dependency for contact discovery.

## Next Implementation Step

Add a local crawler fallback that can run when Hunter is exhausted and SerpApi returns too few useful pages.
