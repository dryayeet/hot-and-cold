"""Phase 1 discovery and intelligence CLI.

Run:
    out/Scripts/python.exe -m outreach_agent.phase_1 --help
"""

from __future__ import annotations

import sys
import argparse
import json
import os
import random
import re
import smtplib
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from outreach_agent.devtools.db import connect, load_env


OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
HUNTER_BASE_URL = "https://api.hunter.io/v2"
SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_MIN_INTERVAL = 2.5
_SERPER_NEXT_SEARCH_AT = 0.0
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-5.4-mini")
HUNTER_CONTACTS_UNAVAILABLE = False


@dataclass
class ContactCandidate:
    full_name: str | None
    title: str | None
    role_type: str | None
    linkedin_url: str | None
    email: str | None
    source: str
    source_detail: dict[str, Any]


@dataclass
class CompanyIntelligence:
    relevance_score: int
    website_url: str | None = None
    careers_url: str | None = None
    funding_status: str | None = None
    company_size: str | None = None
    growth_signal: str | None = None
    recent_news: list[dict[str, Any]] = field(default_factory=list)
    sentiment_score: float | None = None
    sentiment_detail: dict[str, Any] | None = None
    leadership: dict[str, Any] | list[Any] | str | None = None
    traffic: dict[str, Any] | str | None = None
    sources: list[str] = field(default_factory=list)
    notes: str | None = None
    job_postings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SearchPlan:
    query: str
    keywords: list[str]
    job_titles: list[str]
    rationale: str | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 discovery and intelligence.")
    parser.add_argument("--role-prompt", required=True, help="Natural-language role interest prompt")
    parser.add_argument("--resume", required=True, type=Path, help="Path to base_resume.tex")
    parser.add_argument(
        "--projects", required=True, type=Path, help="Path to projects_and_exp.md"
    )
    parser.add_argument("--limit", type=int, default=50, help="Max qualified companies to keep")
    parser.add_argument(
        "--discover-limit",
        type=int,
        default=100,
        help="Max companies to request from Hunter discovery",
    )
    parser.add_argument(
        "--max-contacts-per-company",
        type=int,
        default=3,
        help="Max contacts to keep per company",
    )
    parser.add_argument("--smtp-timeout", type=int, default=10, help="SMTP ping timeout")
    parser.add_argument("--dry-run", action="store_true", help="Skip database writes")
    args = parser.parse_args()

    load_env()
    required = ["OPENROUTER_API_KEY", "HUNTER_API_KEY", "OUTREACH_USER_ID", "DATABASE_URL"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"missing env vars: {', '.join(missing)}")

    resume_text = read_text(args.resume)
    projects_text = read_text(args.projects)
    validate_resume_tex(resume_text)
    search_plan = build_hunter_search_plan(args.role_prompt, resume_text, projects_text)

    with connect(autocommit=False) as conn:
        user_id = os.environ["OUTREACH_USER_ID"]
        campaign_id = create_campaign(conn, user_id, args.role_prompt, search_plan)
        run_id = create_agent_run(conn, user_id, campaign_id)
        insert_event(
            conn,
            user_id=user_id,
            event_type="run.started",
            entity_type="agent_run",
            entity_id=run_id,
            campaign_id=campaign_id,
            run_id=run_id,
            actor="agent",
            payload={"stage": "phase_1", "role_prompt": args.role_prompt},
        )
        conn.commit()

        discovery = discover_companies(search_plan, args.discover_limit)
        companies = discovery.get("data", [])[: args.limit]

        results: list[dict[str, Any]] = []
        for raw_company in companies:
            company = normalize_company(raw_company)
            company_id = upsert_company(conn, user_id, company)
            intel = enrich_company(company, args.role_prompt, resume_text, projects_text)
            snapshot_id = insert_snapshot(conn, user_id, company_id, run_id, intel)
            update_latest_snapshot(conn, company_id, snapshot_id)
            insert_news_and_jobs(conn, user_id, company_id, intel)

            if intel.relevance_score < 6:
                conn.commit()
                results.append({"company": company["name"], "kept": False, "score": intel.relevance_score})
                continue

            opportunity_id = upsert_opportunity(
                conn,
                user_id=user_id,
                campaign_id=campaign_id,
                company_id=company_id,
                role_title=args.role_prompt,
                relevance_score=intel.relevance_score,
                job_posting_id=company.get("job_posting_id"),
            )
            contacts = discover_contacts(
                company,
                search_plan,
                max_contacts=args.max_contacts_per_company,
                smtp_timeout=args.smtp_timeout,
            )
            contact_records = persist_contacts(
                conn,
                user_id=user_id,
                company_id=company_id,
                opportunity_id=opportunity_id,
                contacts=contacts,
            )
            conn.commit()
            results.append(
                {
                    "company": company,
                    "discovery": raw_company,
                    "company_details": asdict(intel),
                    "roles": intel.job_postings,
                    "contacts": contact_records,
                    "opportunity_id": str(opportunity_id),
                }
            )

        insert_event(
            conn,
            user_id=user_id,
            event_type="run.finished",
            entity_type="agent_run",
            entity_id=run_id,
            campaign_id=campaign_id,
            run_id=run_id,
            actor="agent",
            payload={
                "stage": "phase_1",
                "qualified_companies": sum(1 for row in results if row.get("contacts") is not None),
                "discovered_companies": len(companies),
            },
        )
        conn.commit()

        conn.execute(
            "update public.agent_runs set status = %s, finished_at = now() where id = %s",
            ("succeeded", run_id),
        )
        conn.commit()

    print(
        json.dumps(
                {
                    "role_prompt": args.role_prompt,
                    "search_plan": asdict(search_plan),
                    "filters": {"headquarters_location": {"include": [{"country": "IN"}]}},
                    "campaign_id": str(campaign_id),
                    "run_id": str(run_id),
                "discovery_meta": discovery.get("meta", {}),
                "results": results,
            },
            indent=2,
        )
    )
    return 0


def read_text(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"missing input file: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def validate_resume_tex(text: str) -> None:
    checks = {
        "Experience": [r"\\section\*?\{\s*Work Experience\s*\}", r"\\section\*?\{\s*Experience\s*\}"],
        "Skills": [r"\\section\*?\{\s*Skills\s*\}"],
        "Projects": [r"\\section\*?\{\s*Projects\s*\}"],
    }
    for label, patterns in checks.items():
        if not any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            raise SystemExit(f"resume check failed: missing section {label!r}")


def build_hunter_search_plan(
    role_prompt: str,
    resume_text: str,
    projects_text: str,
) -> SearchPlan:
    prompt = f"""
You are preparing a Hunter discovery payload.

Use these inputs:
- role prompt: {role_prompt}
- resume text: {resume_text}
- projects text: {projects_text}

Return only valid JSON with this shape:
{{
  "query": "compact comma-separated search terms",
  "keywords": ["keyword1", "keyword2"],
  "job_titles": ["title1", "title2"],
  "rationale": "one short sentence"
}}

Rules:
- keep the query short, concrete, and search-friendly
- use comma-separated noun phrases, not a sentence
- do not repeat the full role prompt verbatim
- avoid company names, filenames, paths, and code tokens
- infer the best terms from the provided inputs without assuming a specific field, industry, or geography
- make keywords and job titles specific and relevant, not broad marketing language
- do not restrict job titles to explicit AI labels, if the text suggests AI delivery is owned by general engineering, platform, backend, or technical lead roles, include those too
- keep the title set broad enough to catch enterprise roles that hide AI work behind traditional engineering titles, while staying tightly related to the role prompt
- avoid generic catch-all titles unless the raw text strongly supports them; prefer titles that still imply ownership of production AI, backend, platform, or leadership work
""".strip()

    response = openrouter_chat(
        system="You optimize search queries for Hunter. Return JSON only.",
        user=prompt,
        tools=[{"type": "openrouter:web_search", "parameters": {"engine": "auto", "max_results": 3, "max_total_results": 5}}],
        max_tool_calls=2,
    )
    try:
        data = parse_json_object(response)
    except Exception:
        data = {}

    keywords = [str(item).strip() for item in (data.get("keywords") or []) if str(item).strip()]
    job_titles = [str(item).strip() for item in (data.get("job_titles") or []) if str(item).strip()]
    query = sanitize_hunter_query(str(data.get("query") or ", ".join([*keywords[:6], *job_titles[:4]])).strip())
    rationale = data.get("rationale")
    return SearchPlan(query=query, keywords=keywords[:12], job_titles=job_titles[:12], rationale=rationale)


def discover_companies(search_plan: SearchPlan, limit: int) -> dict[str, Any]:
    body = {
        "headquarters_location": {"include": [{"country": "IN"}]},
        "job_openings": {"hiring": True, "posted_date": "last90d"},
    }
    if search_plan.job_titles:
        body["job_openings"]["job_title"] = {"include": search_plan.job_titles[:5]}
    return hunter_request("POST", "/discover/people", body=body)


def sanitize_hunter_query(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip().strip('"\'`')
    if not text:
        return text

    parts = [part.strip() for part in re.split(r"[;,|]+", text) if part.strip()]
    cleaned: list[str] = []
    for part in parts:
        if any(sep in part for sep in ("/", "\\", "@", "::")):
            continue
        if re.search(r"\b(https?://|www\.|\.com\b|\.io\b|\.pdf\b|\.tex\b)\b", part, flags=re.IGNORECASE):
            continue
        if len(part.split()) > 5:
            continue
        if len(part) > 60:
            continue
        if part.lower() not in {item.lower() for item in cleaned}:
            cleaned.append(part)

    if not cleaned:
        words = re.findall(r"[A-Za-z0-9+#.-]+", text)
        cleaned = [" ".join(words[:5])] if words else []

    return ", ".join(cleaned[:12])


def normalize_company(raw: dict[str, Any]) -> dict[str, Any]:
    domain = raw.get("domain")
    name = raw.get("organization") or domain or "unknown"
    return {
        "name": name,
        "domain": domain,
        "website_url": f"https://{domain}" if domain else None,
        "careers_url": None,
        "raw": raw,
    }


def enrich_company(company: dict[str, Any], role_prompt: str, resume_text: str, projects_text: str) -> CompanyIntelligence:
    prompt = f"""
Research {company['name']} ({company.get('domain') or 'no domain'}) for a hiring campaign.
Target market: India only.
Role target: {role_prompt}
Resume text: {resume_text}
Projects text: {projects_text}

Return only valid JSON with this shape:
{{
  "relevance_score": 1,
  "website_url": null,
  "careers_url": null,
  "funding_status": null,
  "company_size": null,
  "growth_signal": null,
  "recent_news": [{{"title": "", "url": "", "published_at": "", "summary": ""}}],
  "sentiment_score": null,
  "sentiment_detail": null,
  "leadership": null,
  "traffic": null,
  "sources": [],
  "notes": null,
  "job_postings": [{{"title": "", "url": "", "location": "", "summary": ""}}]
}}

Use web search if needed. Keep the result grounded, concise, and consistent.
Only include job postings that are based in India or explicitly open to India/remote India.
""".strip()

    response = openrouter_chat(
        system="You are a careful research assistant. Return JSON only.",
        user=prompt,
        tools=[{"type": "openrouter:web_search", "parameters": {"engine": "auto", "max_results": 5, "max_total_results": 10}}],
        max_tool_calls=4,
    )
    try:
        data = parse_json_object(response)
    except Exception:
        data = {}
    return CompanyIntelligence(
        relevance_score=max(1, min(10, int(data.get("relevance_score", 6) or 6))),
        website_url=data.get("website_url") or company.get("website_url"),
        careers_url=data.get("careers_url"),
        funding_status=data.get("funding_status"),
        company_size=data.get("company_size"),
        growth_signal=data.get("growth_signal"),
        recent_news=data.get("recent_news") or [],
        sentiment_score=clamp_float(coerce_float(data.get("sentiment_score")), 1.0, 5.0),
        sentiment_detail=data.get("sentiment_detail"),
        leadership=data.get("leadership"),
        traffic=data.get("traffic"),
        sources=data.get("sources") or [],
        notes=data.get("notes"),
        job_postings=[item for item in (data.get("job_postings") or []) if is_india_job_posting(item)],
    )


def discover_contacts(
    company: dict[str, Any],
    search_plan: SearchPlan,
    max_contacts: int,
    smtp_timeout: int,
) -> list[ContactCandidate]:
    domain = company.get("domain")
    if not domain:
        return []

    query = {
        "domain": domain,
        "limit": min(max_contacts * 3, 10),
        "type": "personal",
        "department": "hr,management,executive,operations,product",
        "job_titles": "human resources,recruiter,talent acquisition,people operations,people partner,hr manager,hr business partner,head of people,talent acquisition partner,hr executive,hiring manager,engineering manager,technical lead,head of engineering,people manager",
        "location": {"include": [{"country": "IN"}]},
        "required_field": "full_name,position",
    }

    picked: list[ContactCandidate] = []
    seen_emails: set[str] = set()
    global HUNTER_CONTACTS_UNAVAILABLE
    if not HUNTER_CONTACTS_UNAVAILABLE:
        try:
            response = hunter_request("POST", "/domain-search", body=query)
        except SystemExit:
            HUNTER_CONTACTS_UNAVAILABLE = True
        else:
            candidates = response.get("data", {}).get("emails", [])

            for row in candidates:
                email = row.get("value")
                if not email:
                    continue
                if not is_hr_ta_contact(row):
                    continue
                syntax_ok = is_valid_email_syntax(email)
                syntax_result = "valid" if syntax_ok else "invalid"
                verification_trace = {"syntax": syntax_result, "hunter": row.get("verification", {})}
                if not syntax_ok:
                    add_contact_candidate(
                        picked,
                        seen_emails,
                        ContactCandidate(
                            full_name=join_name(row.get("first_name"), row.get("last_name")),
                            title=row.get("position"),
                            role_type=role_type_from_contact(row),
                            linkedin_url=row.get("linkedin"),
                            email=email,
                            source="hunter",
                            source_detail=verification_trace,
                        ),
                    )
                    continue

                smtp_result, raw = smtp_ping(email, timeout=smtp_timeout)
                verification_trace["smtp"] = {"result": smtp_result, "raw": raw}
                add_contact_candidate(
                    picked,
                    seen_emails,
                    ContactCandidate(
                        full_name=join_name(row.get("first_name"), row.get("last_name")),
                        title=row.get("position"),
                        role_type=role_type_from_contact(row),
                        linkedin_url=row.get("linkedin"),
                        email=email,
                        source="hunter",
                        source_detail=verification_trace,
                    ),
                )
                if len(picked) >= max_contacts:
                    break

    if len(picked) < max_contacts:
        serper_contacts = discover_serper_contacts(
            company,
            search_plan,
            max_contacts=max_contacts - len(picked),
            smtp_timeout=smtp_timeout,
            seen_emails=seen_emails,
        )
        for contact in serper_contacts:
            add_contact_candidate(picked, seen_emails, contact)
            if len(picked) >= max_contacts:
                break

    return picked


def discover_serper_contacts(
    company: dict[str, Any],
    search_plan: SearchPlan,
    *,
    max_contacts: int,
    smtp_timeout: int,
    seen_emails: set[str],
) -> list[ContactCandidate]:
    if not os.environ.get("SERPER_API_KEY") or os.environ["SERPER_API_KEY"].startswith("your-"):
        return []

    domain = company.get("domain")
    if not domain:
        return []

    company_name = company.get("name") or domain
    search_terms = " ".join([*search_plan.job_titles[:2], *search_plan.keywords[:2]]).strip()
    queries = [
        f'site:{domain} "{company_name}" India careers',
        f'site:{domain} "{company_name}" India recruiter',
        f'site:{domain} "{company_name}" India talent acquisition',
        f'site:{domain} "{company_name}" India contact',
        f'site:{domain} "{company_name}" India team',
        f'site:{domain} "{company_name}" India people',
    ]
    if search_terms:
        queries.append(f'site:{domain} "{company_name}" India {search_terms}')
    queries.extend(
        [
            f'site:{domain} (careers OR jobs OR hiring OR recruiter OR "talent acquisition" OR contact OR team OR people) India',
            f'site:{domain} (apply OR opportunities OR join OR "work with us" OR "human resources") India',
        ]
    )

    page_urls: list[tuple[str, dict[str, Any], str]] = []
    seen_urls: set[str] = set()
    for query in queries:
        payload = serper_search(query)
        for result in payload.get("organic_results", [])[:8]:
            url = result.get("link")
            if not url or url in seen_urls:
                continue
            if not looks_like_hiring_or_careers_url(url, domain):
                continue
            seen_urls.add(url)
            page_urls.append((url, result, query))

    picked: list[ContactCandidate] = []
    for url, result, query in page_urls[:12]:
        html = fetch_url(url)
        if not html:
            continue
        page_text = html_to_text(html)
        if not is_india_context(page_text) and not is_india_context(json.dumps(result, ensure_ascii=False)):
            continue
        page_candidates = extract_contacts_from_page(
            company=company,
            url=url,
            result=result,
            page_html=html,
            page_text=page_text,
            query=query,
            seen_emails=seen_emails,
            smtp_timeout=smtp_timeout,
        )
        for candidate in page_candidates:
            add_contact_candidate(picked, seen_emails, candidate)
            if len(picked) >= max_contacts:
                return picked

    return picked


def add_contact_candidate(
    picked: list[ContactCandidate],
    seen_emails: set[str],
    contact: ContactCandidate,
) -> None:
    if not contact.email:
        return
    email_key = contact.email.lower()
    if email_key in seen_emails:
        return
    seen_emails.add(email_key)
    picked.append(contact)


def serper_search(query: str) -> dict[str, Any]:
    global _SERPER_NEXT_SEARCH_AT
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key or api_key.startswith("your-"):
        return {}

    delay = max(0.0, _SERPER_NEXT_SEARCH_AT - time.monotonic())
    if delay:
        time.sleep(delay)
    _SERPER_NEXT_SEARCH_AT = time.monotonic() + SERPER_MIN_INTERVAL + random.uniform(0.0, 0.5)
    payload = {
        "q": query,
        "gl": "in",
        "hl": "en",
        "num": 10,
    }
    req = urllib.request.Request(
        SERPER_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-KEY": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if isinstance(result, dict) and isinstance(result.get("organic"), list):
                result["organic_results"] = result["organic"]
            return result
    except urllib.error.HTTPError:
        return {}
    except (TimeoutError, ValueError, OSError):
        return {}


def fetch_url(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, TimeoutError, OSError):
        return ""


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_india_context(text: str) -> bool:
    haystack = text.lower()
    india_terms = (
        "india",
        "remote india",
        "anywhere in india",
        "bengaluru",
        "bangalore",
        "hyderabad",
        "pune",
        "chennai",
        "mumbai",
        "gurugram",
        "gurgaon",
        "noida",
        "delhi",
        "ncr",
    )
    return any(term in haystack for term in india_terms)


def is_hiring_context(text: str) -> bool:
    haystack = text.lower()
    terms = (
        "career",
        "careers",
        "job",
        "jobs",
        "hiring",
        "recruit",
        "talent acquisition",
        "human resources",
        "people ops",
        "people operations",
        "join us",
        "apply",
        "work with us",
        "opportunities",
    )
    return any(term in haystack for term in terms)


def looks_like_hiring_or_careers_url(url: str, domain: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = (parsed.path or "").lower()
    site_tokens = (
        "career",
        "careers",
        "job",
        "jobs",
        "hiring",
        "apply",
        "talent",
        "recruit",
        "contact",
        "team",
        "people",
        "about",
        "leadership",
        "staff",
        "join",
    )
    ats_hosts = (
        "greenhouse",
        "lever",
        "ashby",
        "smartrecruiters",
        "workable",
        "icims",
        "jobvite",
        "taleo",
        "bamboohr",
        "recruitee",
    )
    if domain.lower() in host:
        return any(token in path or token in host for token in site_tokens)
    return any(token in host for token in (*site_tokens, *ats_hosts))


def extract_contacts_from_page(
    *,
    company: dict[str, Any],
    url: str,
    result: dict[str, Any],
    page_html: str,
    page_text: str,
    query: str,
    seen_emails: set[str],
    smtp_timeout: int,
) -> list[ContactCandidate]:
    domain = (company.get("domain") or "").lower()
    company_name = (company.get("name") or "").lower()
    emails = unique_emails(f"{page_text} {page_html}")
    picked: list[ContactCandidate] = []
    page_title = str(result.get("title") or extract_title(page_html) or "").strip()
    search_query = query
    page_context = f"{company_name} {page_text} {page_html} {page_title} {url} {json.dumps(result, ensure_ascii=False)} {search_query}".lower()
    page_url = url.lower()

    for email in emails:
        email_l = email.lower()
        if email_l in seen_emails:
            continue
        email_domain = email_l.split("@", 1)[-1]
        context = page_context
        if domain and not email_domain.endswith(domain) and not (company_name in context and is_hiring_context(context)):
            continue
        if not is_india_context(context) and not (
            email_domain.endswith(domain)
            and (
                is_hiring_context(context)
                or any(token in page_url or token in page_context for token in ("contact", "team", "people", "about", "career", "jobs", "hiring", "recruit"))
            )
        ):
            continue

        title = infer_contact_title(email, page_title, page_text)
        row = {"position": title, "department": infer_department(title, email, page_text)}
        role_type = role_type_from_contact(row)
        full_name = extract_person_name(page_text, email, page_title)

        syntax_ok = is_valid_email_syntax(email)
        syntax_result = "valid" if syntax_ok else "invalid"
        source_detail = {
            "syntax": syntax_result,
            "serper": {
                "url": url,
                "title": page_title,
                "query": search_query,
                "result": result,
            },
        }
        if not syntax_ok:
            continue

        smtp_result, raw = smtp_ping(email, timeout=smtp_timeout)
        source_detail["smtp"] = {"result": smtp_result, "raw": raw}
        picked.append(
            ContactCandidate(
                full_name=full_name,
                title=title,
                role_type=role_type,
                linkedin_url=None,
                email=email,
                source="serper",
                source_detail=source_detail,
            )
        )
        if len(picked) >= 10:
            break

    return picked


def unique_emails(text: str) -> list[str]:
    emails = []
    for match in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        email = match.strip(".,;:()[]{}<>\"' ")
        if email.lower() not in {item.lower() for item in emails}:
            emails.append(email)
    return emails


def extract_title(text: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        value = re.sub(r"\s+", " ", match.group(1)).strip()
        return value or None
    return None


def infer_contact_title(email: str, page_title: str, page_text: str) -> str:
    email_local = email.split("@", 1)[0].lower()
    context = f"{email_local} {page_title} {page_text}".lower()
    if any(term in context for term in ("talent acquisition", "recruit", "recruiter", "hr", "human resources")):
        return "Talent Acquisition"
    if any(term in context for term in ("hiring", "careers", "jobs", "join us", "apply")):
        return "Careers Team"
    if any(term in context for term in ("people ops", "people operations", "people partner")):
        return "People Operations"
    if any(term in context for term in ("engineering manager", "technical lead", "platform engineer", "backend engineer", "software engineer")):
        return "Hiring Manager"
    if any(term in email_local for term in ("hr", "recruit", "talent", "careers", "jobs", "people")):
        return "Talent Acquisition"
    return page_title[:80] if page_title else "Hiring Contact"


def infer_department(title: str, email: str, page_text: str) -> str:
    context = f"{title} {email} {page_text}".lower()
    if any(term in context for term in ("hr", "human resources", "recruit", "talent acquisition", "careers", "people ops", "people operations")):
        return "hr"
    if any(term in context for term in ("hiring manager", "engineering manager", "technical lead", "platform engineer", "backend engineer", "software engineer")):
        return "management"
    return "hr"


def extract_person_name(page_text: str, email: str, page_title: str) -> str | None:
    local = email.split("@", 1)[0]
    parts = re.split(r"[._-]+", local)
    if len(parts) >= 2 and all(part.isalpha() for part in parts[:2]):
        candidate = f"{parts[0].title()} {parts[1].title()}"
        if len(candidate) <= 40:
            return candidate
    match = re.search(r"\b([A-Z][a-z]+ [A-Z][a-z]+)\b", f"{page_title} {page_text}")
    if match:
        return match.group(1)
    return None


def persist_contacts(
    conn,
    *,
    user_id: str,
    company_id: str,
    opportunity_id: str,
    contacts: list[ContactCandidate],
) -> list[dict[str, Any]]:
    contact_records: list[dict[str, Any]] = []
    for index, contact in enumerate(contacts):
        cur = conn.execute(
            """
            insert into public.contacts (user_id, company_id, full_name, title, role_type, linkedin_url, linkedin_verified, source, source_detail)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                user_id,
                company_id,
                contact.full_name,
                contact.title,
                contact.role_type,
                contact.linkedin_url,
                False,
                contact.source,
                json.dumps(contact.source_detail),
            ),
        )
        contact_id = cur.fetchone()[0]
        relation_role = "fallback_hr" if contact.role_type == "hr" else ("primary" if index == 0 else "cc")
        conn.execute(
            """
            insert into public.opportunity_contacts (user_id, opportunity_id, contact_id, role)
            values (%s, %s, %s, %s)
            on conflict do nothing
            """,
            (user_id, opportunity_id, contact_id, relation_role),
        )
        insert_event(
            conn,
            user_id=user_id,
            event_type="contact.found",
            entity_type="contact",
            entity_id=contact_id,
            opportunity_id=opportunity_id,
            actor="agent",
            payload={"title": contact.title, "role_type": contact.role_type},
        )

        verification_status = derive_verification_status(contact.source_detail)
        contact_record: dict[str, Any] = {
            "contact_id": str(contact_id),
            "full_name": contact.full_name,
            "title": contact.title,
            "role_type": contact.role_type,
            "linkedin_url": contact.linkedin_url,
            "email": contact.email,
            "verification_status": verification_status,
            "source_detail": contact.source_detail,
        }
        if contact.email:
            email_cur = conn.execute(
                """
                insert into public.contact_emails (user_id, contact_id, email, is_primary, source, verification_status, last_verified_at)
                values (%s, %s, %s, %s, %s, %s, now())
                on conflict (user_id, email) do update
                  set contact_id = excluded.contact_id,
                      source = excluded.source,
                      verification_status = excluded.verification_status,
                      last_verified_at = excluded.last_verified_at,
                      updated_at = now()
                returning id
                """,
                (
                    user_id,
                    contact_id,
                    contact.email,
                    True,
                    contact.source,
                    verification_status,
                ),
            )
            contact_email_id = email_cur.fetchone()[0]
            syntax_result = contact.source_detail.get("syntax", "unknown")
            smtp_result = contact.source_detail.get("smtp", {}).get("result")
            insert_email_verification(
                conn,
                user_id=user_id,
                contact_email_id=contact_email_id,
                method="syntax",
                result=syntax_result,
                raw_response={"email": contact.email},
            )
            if smtp_result:
                insert_email_verification(
                    conn,
                    user_id=user_id,
                    contact_email_id=contact_email_id,
                    method="smtp_ping",
                    result=smtp_result,
                    raw_response=contact.source_detail.get("smtp", {}).get("raw"),
                )
            insert_event(
                conn,
                user_id=user_id,
                event_type="email.verified",
                entity_type="contact_email",
                entity_id=contact_email_id,
                opportunity_id=opportunity_id,
                actor="agent",
                payload={"method": "smtp_ping", "result": smtp_result or syntax_result},
            )

            contact_record["contact_email_id"] = str(contact_email_id)
            contact_record["smtp_verification"] = {
                "syntax": syntax_result,
                "smtp": smtp_result,
            }

        contact_records.append(contact_record)

    return contact_records


def derive_verification_status(source_detail: dict[str, Any]) -> str:
    smtp = source_detail.get("smtp", {})
    result = smtp.get("result")
    if result in {"valid", "invalid", "catch_all", "risky", "disposable", "unknown"}:
        return result
    syntax = source_detail.get("syntax")
    if syntax == "invalid":
        return "invalid"
    return "unknown"


def role_type_from_contact(row: dict[str, Any]) -> str | None:
    title = (row.get("position") or "").lower()
    department = (row.get("department") or "").lower()
    if "hr" in department or "people" in title or "talent" in title or "recruit" in title:
        return "hr"
    if "executive" in department or title.startswith(("ceo", "cto", "cfo", "coo", "founder")):
        return "founder"
    if "management" in department or "hiring" in title or "manager" in title:
        return "hiring_manager"
    if "product" in department:
        return "other"
    return "other"


def is_hr_ta_contact(row: dict[str, Any]) -> bool:
    title = (row.get("position") or "").lower()
    department = (row.get("department") or "").lower()
    keywords = (
        "hr",
        "human resources",
        "recruit",
        "talent acquisition",
        "people operations",
        "people partner",
        "people ops",
        "head of people",
        "hr business partner",
        "hiring manager",
        "engineering manager",
        "technical lead",
        "head of engineering",
        "people manager",
        "manager",
        "director",
        "lead",
    )
    if department == "hr":
        return any(keyword in title for keyword in keywords) or "people" in title or "talent" in title
    return any(keyword in title for keyword in keywords)


def is_india_job_posting(item: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(item.get(key) or "") for key in ("title", "location", "summary", "url")
    ).lower()
    india_terms = (
        "india",
        "remote india",
        "anywhere in india",
        "bengaluru",
        "bangalore",
        "hyderabad",
        "pune",
        "chennai",
        "mumbai",
        "gurugram",
        "gurgaon",
        "noida",
        "delhi",
        "ncr",
    )
    return any(term in haystack for term in india_terms)


def insert_snapshot(conn, user_id: str, company_id: str, run_id: str, intel: CompanyIntelligence):
    cur = conn.execute(
        """
        insert into public.company_snapshots (
          user_id, company_id, run_id, funding_stage, headcount,
          growth_signal, sentiment_score, sentiment_detail, leadership,
          traffic, sources
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        returning id
        """,
        (
            user_id,
            company_id,
            run_id,
            intel.funding_status,
            coerce_int(intel.company_size),
            to_jsonb(intel.growth_signal),
            intel.sentiment_score,
            to_jsonb(intel.sentiment_detail),
            to_jsonb(intel.leadership),
            to_jsonb(intel.traffic),
            to_jsonb(intel.sources),
        ),
    )
    return cur.fetchone()[0]


def update_latest_snapshot(conn, company_id: str, snapshot_id: str) -> None:
    conn.execute(
        "update public.companies set latest_snapshot_id = %s, updated_at = now() where id = %s",
        (snapshot_id, company_id),
    )


def insert_news_and_jobs(conn, user_id: str, company_id: str, intel: CompanyIntelligence) -> None:
    for item in intel.recent_news:
        url = item.get("url")
        if not url:
            continue
        conn.execute(
            """
            insert into public.company_news (user_id, company_id, kind, title, url, published_at, summary)
            values (%s,%s,%s,%s,%s,%s,%s)
            on conflict (user_id, company_id, url) do nothing
            """,
            (
                user_id,
                company_id,
                item.get("kind", "other"),
                item.get("title") or "Untitled news",
                url,
                safe_timestamptz(item.get("published_at")),
                item.get("summary"),
            ),
        )

    for item in intel.job_postings:
        url = item.get("url")
        if not url:
            continue
        conn.execute(
            """
            insert into public.job_postings (user_id, company_id, title, url, source, location, seniority, description, parsed, status)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (user_id, url) do update
              set company_id = excluded.company_id,
                  title = excluded.title,
                  source = excluded.source,
                  location = excluded.location,
                  seniority = excluded.seniority,
                  description = excluded.description,
                  parsed = excluded.parsed,
                  status = excluded.status,
                  updated_at = now(),
                  last_seen_at = now()
            """,
            (
                user_id,
                company_id,
                item.get("title") or "Open role",
                url,
                item.get("source"),
                item.get("location"),
                item.get("seniority"),
                item.get("summary"),
                to_jsonb(item),
                item.get("status", "open"),
            ),
        )


def upsert_company(conn, user_id: str, company: dict[str, Any]) -> str:
    domain = company.get("domain")
    if domain:
        cur = conn.execute(
            """
            insert into public.companies (user_id, name, domain, website_url, careers_url, attributes)
            values (%s,%s,%s,%s,%s,%s)
            on conflict (user_id, domain) where domain is not null do update
              set name = excluded.name,
                  website_url = coalesce(public.companies.website_url, excluded.website_url),
                  careers_url = coalesce(public.companies.careers_url, excluded.careers_url),
                  attributes = public.companies.attributes || excluded.attributes,
                  updated_at = now()
            returning id
            """,
            (
                user_id,
                company["name"],
                domain,
                company.get("website_url"),
                company.get("careers_url"),
                to_jsonb(company.get("raw", {})),
            ),
        )
        return cur.fetchone()[0]

    cur = conn.execute(
        """
        insert into public.companies (user_id, name, website_url, careers_url, attributes)
        values (%s,%s,%s,%s,%s)
        returning id
        """,
        (
            user_id,
            company["name"],
            company.get("website_url"),
            company.get("careers_url"),
            to_jsonb(company.get("raw", {})),
        ),
    )
    return cur.fetchone()[0]


def upsert_opportunity(
    conn,
    *,
    user_id: str,
    campaign_id: str,
    company_id: str,
    role_title: str,
    relevance_score: int,
    job_posting_id: str | None,
) -> str:
    cur = conn.execute(
        """
        insert into public.opportunities (
          user_id, campaign_id, company_id, job_posting_id, role_title,
          relevance_score, status, attributes
        ) values (%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (user_id, company_id, job_posting_id) do update
          set role_title = excluded.role_title,
              relevance_score = excluded.relevance_score,
              status = 'qualified',
              updated_at = now(),
              attributes = public.opportunities.attributes || excluded.attributes
        returning id
        """,
        (
            user_id,
            campaign_id,
            company_id,
            job_posting_id,
            role_title,
            relevance_score,
            "qualified",
            to_jsonb({"phase": 1}),
        ),
    )
    opportunity_id = cur.fetchone()[0]
    insert_event(
        conn,
        user_id=user_id,
        event_type="opportunity.created",
        entity_type="opportunity",
        entity_id=opportunity_id,
        opportunity_id=opportunity_id,
        campaign_id=campaign_id,
        actor="agent",
        payload={"relevance_score": relevance_score, "status": "qualified"},
    )
    return opportunity_id


def create_campaign(conn, user_id: str, role_prompt: str, search_plan: SearchPlan):
    cur = conn.execute(
        """
        insert into public.campaigns (user_id, name, role_prompt, parsed_signals)
        values (%s, %s, %s, %s)
        returning id
        """,
        (
            user_id,
            role_prompt[:64],
            role_prompt,
            to_jsonb(asdict(search_plan)),
        ),
    )
    return cur.fetchone()[0]


def create_agent_run(conn, user_id: str, campaign_id: str):
    cur = conn.execute(
        """
        insert into public.agent_runs (user_id, campaign_id, graph_name, trigger, status, started_at)
        values (%s, %s, %s, %s, %s, now())
        returning id
        """,
        (user_id, campaign_id, "phase_1", "manual", "running"),
    )
    return cur.fetchone()[0]


def insert_event(
    conn,
    *,
    user_id: str,
    event_type: str,
    entity_type: str | None,
    entity_id: str | None,
    opportunity_id: str | None = None,
    campaign_id: str | None = None,
    run_id: str | None = None,
    actor: str = "agent",
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        insert into public.events (
          user_id, event_type, entity_type, entity_id, opportunity_id, campaign_id, run_id, actor, payload
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            user_id,
            event_type,
            entity_type,
            entity_id,
            opportunity_id,
            campaign_id,
            run_id,
            actor,
            to_jsonb(payload or {}),
        ),
    )


def insert_email_verification(
    conn,
    *,
    user_id: str,
    contact_email_id: str,
    method: str,
    result: str,
    raw_response: Any,
) -> None:
    conn.execute(
        """
        insert into public.email_verifications (user_id, contact_email_id, method, result, raw_response)
        values (%s,%s,%s,%s,%s)
        """,
        (user_id, contact_email_id, method, result, to_jsonb(raw_response)),
    )


def hunter_request(method: str, path: str, *, query: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    api_key = os.environ["HUNTER_API_KEY"]
    params = {"api_key": api_key}
    if query:
        params.update(query)
    url = f"{HUNTER_BASE_URL}{path}?{urllib.parse.urlencode(params, doseq=True)}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Hunter API error {exc.code} on {path}: {exc.read().decode('utf-8', errors='replace')}") from exc


def openrouter_chat(
    *,
    system: str,
    user: str,
    tools: list[dict[str, Any]] | None = None,
    max_tool_calls: int = 6,
    model: str = DEFAULT_MODEL,
) -> str:
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
    }
    if tools:
        body["tools"] = tools
        body["max_tool_calls"] = max_tool_calls
    req = urllib.request.Request(
        OPENROUTER_CHAT_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"OpenRouter error {exc.code}: {exc.read().decode('utf-8', errors='replace')}") from exc
    message = payload["choices"][0]["message"]
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return content


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    stripped = re.sub(r"^```json\s*", "", stripped)
    stripped = re.sub(r"^```\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError(f"no JSON object found: {text[:200]}")
    return json.loads(stripped[start : end + 1])


def coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp_float(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    return max(low, min(high, value))


def safe_timestamptz(value: Any) -> Any:
    if value in (None, "", "unknown"):
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?", candidate):
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        if m:
            return int(m.group(0))
    return None


def to_jsonb(value: Any) -> Any:
    return Jsonb(json.loads(json.dumps(value, default=str)))


def is_valid_email_syntax(email: str) -> bool:
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+",
            email,
        )
    )


def smtp_ping(email: str, timeout: int = 10) -> tuple[str, dict[str, Any]]:
    domain = email.split("@", 1)[-1]
    mx_hosts = resolve_mx_hosts(domain)
    if not mx_hosts:
        return "unknown", {"reason": "no_mx_records", "domain": domain}

    host = mx_hosts[0]
    trace: dict[str, Any] = {"mx_host": host, "domain": domain}
    try:
        with smtplib.SMTP(host, 25, timeout=timeout) as smtp:
            smtp.ehlo_or_helo_if_needed()
            code, message = smtp.mail("probe@example.com")
            trace["mail_code"] = code
            trace["mail_message"] = decode_smtp_message(message)
            code, message = smtp.rcpt(email)
            trace["rcpt_code"] = code
            trace["rcpt_message"] = decode_smtp_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        return "unknown", {**trace, "error": str(exc)}

    if 200 <= trace.get("rcpt_code", 0) < 300:
        return "valid", trace
    if trace.get("rcpt_code") in {450, 451, 452}:
        return "risky", trace
    if trace.get("rcpt_code") in {550, 551, 552, 553, 554}:
        return "invalid", trace
    return "unknown", trace


def decode_smtp_message(message: Any) -> str:
    if isinstance(message, bytes):
        return message.decode("utf-8", errors="replace")
    return str(message)


def resolve_mx_hosts(domain: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["nslookup", "-type=mx", domain],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    hosts: list[str] = []
    for line in proc.stdout.splitlines():
        if "mail exchanger =" in line:
            parts = line.split("mail exchanger =", 1)[1].strip().rstrip(".")
            if parts:
                hosts.append(parts)
    return hosts


def join_name(first: str | None, last: str | None) -> str | None:
    parts = [part for part in (first, last) if part]
    return " ".join(parts) if parts else None


if __name__ == "__main__":
    raise SystemExit(main())
