"""Drop everything the schema migrations own, keep auth.users and extensions.

Danger: deletes ALL data in the public schema. Dev tool only.

Run from anywhere:
    out/Scripts/python.exe -m outreach_agent.devtools.reset_public
"""

import psycopg

from outreach_agent.devtools.db import connect


def reset_public(conn: psycopg.Connection) -> int:
    conn.execute("drop trigger if exists on_auth_user_created on auth.users")
    conn.execute("drop function if exists public.handle_new_user()")

    rows = conn.execute(
        "select tablename from pg_tables where schemaname = 'public'"
    ).fetchall()
    for (table,) in rows:
        conn.execute(f'drop table if exists public."{table}" cascade')

    remaining = conn.execute(
        "select count(*) from pg_tables where schemaname = 'public'"
    ).fetchone()[0]
    return remaining


if __name__ == "__main__":
    with connect(autocommit=True) as conn:
        left = reset_public(conn)
        print(f"tables left in public: {left}")
        print("note: re-run 'supabase db push' to rebuild the schema")
