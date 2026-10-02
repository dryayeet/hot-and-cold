# todo.md

Running checklist for the outreach-agent. Format: `- [ ] item: context`. Check items off as they are done; add new items with context as they come up.

## Decisions needed

- [ ] Pick OpenRouter model(s) for research/drafting/classification: must have web search ability, either native web search or via OpenRouter's `web` plugin (`:online` suffix; Exa-powered for non-native models). One model for everything or different models per stage, TBD. Context: Stage 1, 2, 4, 6, 7 all need it; nothing can be built against a real API until this is chosen
- [ ] Decide contact discovery method: LLM web search vs dedicated email-finder API (Hunter.io Email Finder / Domain Search) vs hybrid. Context: Stage 1; Hunter has department/seniority filters that fit HR/TA lookups well; API costs apply
- [ ] Decide email verification approach: SMTP RCPT TO ping (free, catch-all domains lie, IP reputation risk) vs paid verifier API (Hunter Email Verifier, ZeroBounce, NeverBounce) vs hybrid (cheap ping first, API for uncertain). Context: Stage 1; requirement is "is this email real", not syntax
- [x] Approve DB schema: proposed in `architecture/08-database-schema.md`, all 5 open questions answered 2026-10-01 (per-user company data, embedding model deferred, Supabase Storage, full email text, FACTS stays a file). DONE 2026-10-01: `0001_init.sql` pushed via `supabase db push`, smoke test 15/15 (tables, seed, RLS isolation, buckets, triggers, cascade cleanup)
- [ ] Decide Stage 7 prep output format: file structure of the per-company local markdown prep folder. Context: `architecture/07-interview-prep-deep-dive.md`

## Assets needed from lemon

- [ ] Provide `tools/pagecount.py` (one-page gate from resume_lab): Stage 3 cannot enforce its hard constraint without it
- [ ] Provide/point to `tools/tectonic.exe`, `FACTS.md`, and `main.tex` for this repo (or confirm Stage 3 reads them from the resume_lab directory): Stage 3 toolchain

## Build tasks

- [ ] Repo layout: all Python code lives under `src/outreach_agent/` (lemon, 2026-10-01). Stages map to modules/subpackages there. Exception: `supabase/migrations/` stays put, the Supabase CLI requires that path for schema migrations

- [ ] Validate the LaTeX toolchain inside this repo (tectonic compiles a sample, pagecount gate exits 1 on a 2-page PDF): first task of Stage 3
- [ ] Design LangGraph graph: stage nodes/subgraphs, shared state object, where HITL interrupts live (draft approval, low-match review). Context: the whole pipeline is one LangGraph agent (lemon, 2026-10-01)
- [ ] Gmail API auth setup (OAuth credentials, scopes, draft + read permissions): Stages 4 and 6
- [ ] Send-time analytics: log sends with full timestamps from day one so response-vs-send-time analysis is possible later. Context: lemon, 2026-10-01, Stage 4

## Later / deferred

- [ ] Pick embedding model (OpenRouter embeddings, e.g. text-embedding-3-small 1536d or qwen3-embedding-0.6b), then migration to add `embeddings.embedding vector(N)` + per-entity partial HNSW cosine indexes: required before Stage 2 semantic matching. Decision deferred 2026-10-01
- [ ] FACTS atomization (`candidate_facts` + `resume_claims`, design sketched in `architecture/08-database-schema.md` section 10): revisit when Stage 3 is built. Deferred 2026-10-01
- [x] Create Supabase Storage buckets `resumes` and `prep` (private, `{user_id}/{opportunity_id}/...` path policies): DONE 2026-10-01, created by `0001_init.sql` with per-user prefix policies
- [ ] Optionally add Google Sheets as a human-readable view on top of the DB
- [ ] Resume PDF tools beyond pagecount (PyPDF2/pdfplumber metadata) if needed
