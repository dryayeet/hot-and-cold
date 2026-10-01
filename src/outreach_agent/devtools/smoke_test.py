"""Smoke test for the outreach-agent schema on Supabase.

Creates two throwaway auth users, checks RLS isolation between them, then
deletes them (cascade). Idempotent: clears leftovers from earlier runs first.

Run from anywhere:
    out/Scripts/python.exe -m outreach_agent.devtools.smoke_test
"""

import uuid

import psycopg
from psycopg import sql

from outreach_agent.devtools.db import connect

SMOKE_EMAIL_LIKE = "smoke-%@test.local"


def set_role(conn: psycopg.Connection, role: str, sub: uuid.UUID | None = None) -> None:
    conn.execute(sql.SQL("begin"))
    conn.execute(sql.SQL("set local role {}").format(sql.Identifier(role)))
    if sub:
        conn.execute(
            sql.SQL("set local request.jwt.claim.sub = {}").format(sql.Literal(str(sub)))
        )


def main() -> None:
    checks: list[tuple[str, object, bool]] = []

    with connect(autocommit=True) as conn:
        # --- 0. clear leftovers from any earlier run ---
        conn.execute(f"delete from auth.users where email like '{SMOKE_EMAIL_LIKE}'")

        # --- 1. schema counts ---
        n_tables = conn.execute(
            "select count(*) from pg_tables where schemaname = 'public'"
        ).fetchone()[0]
        checks.append(("tables in public", n_tables, n_tables == 25))

        n_seed = conn.execute("select count(*) from public.event_types").fetchone()[0]
        checks.append(("event_types seeded", n_seed, n_seed == 22))

        n_pol = conn.execute(
            "select count(*) from pg_policies where schemaname = 'public'"
        ).fetchone()[0]
        checks.append(("RLS policies", n_pol, n_pol == 35))

        buckets = [r[0] for r in conn.execute(
            "select id from storage.buckets where id in ('resumes','prep') order by 1"
        ).fetchall()]
        checks.append(("storage buckets", buckets, buckets == ["prep", "resumes"]))

        # --- 2. throwaway users (trigger auto-creates profiles) ---
        ua, ub = uuid.uuid4(), uuid.uuid4()
        conn.execute(
            "insert into auth.users (id, email, encrypted_password) values (%s,%s,%s), (%s,%s,%s)",
            (ua, "smoke-a@test.local", "x", ub, "smoke-b@test.local", "x"),
        )
        n_prof = conn.execute(
            "select count(*) from public.profiles where user_id in (%s,%s)", (ua, ub)
        ).fetchone()[0]
        checks.append(("profiles auto-created", n_prof, n_prof == 2))

        # --- 3. seed data as owner (agent-style writes bypass RLS) ---
        conn.execute(
            "insert into public.campaigns (user_id, role_prompt) values (%s, %s)",
            (ua, "smoke test"),
        )
        conn.execute(
            "insert into public.companies (user_id, name, domain) "
            "values (%s,'Acme A','a.test'), (%s,'Acme B','b.test')",
            (ua, ub),
        )
        conn.execute(
            "insert into public.opportunities (user_id, campaign_id, company_id, role_title) "
            "select %s, c.id, co.id, 'Engineer' from public.campaigns c, public.companies co "
            "where c.user_id = %s and co.user_id = %s",
            (ua, ua, ua),
        )

        # --- 4. RLS: act as user A ---
        set_role(conn, "authenticated", ua)
        n = conn.execute("select count(*) from public.companies").fetchone()[0]
        checks.append(("A sees own companies", n, n == 1))
        n = conn.execute("select count(*) from public.opportunities").fetchone()[0]
        checks.append(("A sees own opportunities", n, n == 1))
        n = conn.execute("select count(*) from public.event_types").fetchone()[0]
        checks.append(("A reads shared event_types", n, n == 22))

        conn.execute(
            "update public.profiles set settings = '{\"smoke\":true}' where user_id = %s",
            (ua,),
        )
        row = conn.execute(
            "select settings->>'smoke' from public.profiles where user_id = %s", (ua,)
        ).fetchone()
        checks.append(("A updates own profile", row, row == ("true",)))

        conn.execute("commit")
        conn.execute("update public.campaigns set name = 'renamed' where user_id = %s", (ua,))
        row = conn.execute(
            "select updated_at > created_at from public.campaigns where user_id = %s",
            (ua,),
        ).fetchone()
        checks.append(("updated_at trigger fires", row, row == (True,)))

        # --- 5. RLS: cross-user isolation as user B ---
        set_role(conn, "authenticated", ub)
        n = conn.execute("select count(*) from public.companies").fetchone()[0]
        checks.append(("B sees only own companies", n, n == 1))
        cur = conn.execute(
            "update public.opportunities set notes = 'hax' where user_id = %s returning id",
            (ua,),
        )
        checks.append(("B cannot update A rows", cur.rowcount, cur.rowcount == 0))
        n = conn.execute("select count(*) from public.opportunities").fetchone()[0]
        checks.append(("B sees no A opportunities", n, n == 0))
        conn.execute("commit")

        # --- 6. anon blocked entirely ---
        set_role(conn, "anon")
        try:
            conn.execute("select * from public.companies").fetchall()
            checks.append(("anon blocked", "no error", False))
        except psycopg.errors.InsufficientPrivilege:
            conn.execute("rollback")
            checks.append(("anon blocked", "permission denied", True))
        else:
            conn.execute("rollback")

        # --- 7. cleanup: deleting users cascades everything (autocommit: sticks) ---
        conn.execute("delete from auth.users where id in (%s, %s)", (ua, ub))
        left_companies = conn.execute("select count(*) from public.companies").fetchone()[0]
        left_profiles = conn.execute("select count(*) from public.profiles").fetchone()[0]
        checks.append(("cascade cleanup", (left_companies, left_profiles), (0, 0) == (left_companies, left_profiles)))

    print()
    fails = 0
    for name, got, passed in checks:
        fails += (not passed)
        print(("PASS" if passed else "FAIL"), "-", name, "| got:", got)
    print()
    print("RESULT:", "ALL PASS" if fails == 0 else f"{fails} FAILURES")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
