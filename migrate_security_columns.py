# One-shot migration script that adds account lockout columns to the doctors table — safe to re-run.
import os
import sys
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///diagnovate.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

COLUMNS = [
    ("failed_attempts", "INTEGER", "NOT NULL DEFAULT 0"),
    ("locked_until",    "DATETIME" if DATABASE_URL.startswith("sqlite") else "TIMESTAMP WITHOUT TIME ZONE", ""),
    ("last_login",      "DATETIME" if DATABASE_URL.startswith("sqlite") else "TIMESTAMP WITHOUT TIME ZONE", ""),
    ("last_ip",         "VARCHAR(45)", ""),
]

if DATABASE_URL.startswith("sqlite"):
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(__file__), db_path)
    print(f"SQLite database: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(doctors)")
    rows = cur.fetchall()
    if not rows:
        print("  SKIP — doctors table does not exist yet; db.create_all() will build it with all columns on first app start.")
        cur.close()
        conn.close()
        sys.exit(0)
    existing = {row[1] for row in rows}
    for col_name, col_type, col_extra in COLUMNS:
        if col_name in existing:
            print(f"  SKIP {col_name} (already exists)")
            continue
        sql = f'ALTER TABLE doctors ADD COLUMN "{col_name}" {col_type} {col_extra};'
        cur.execute(sql)
        print(f"  OK   {col_name} {col_type} {col_extra}")
    conn.commit()
    cur.close()
    conn.close()

else:
    import psycopg2
    conn_url = DATABASE_URL.replace("postgresql://", "postgres://", 1)
    print(f"PostgreSQL: {conn_url[:40]}...")
    conn = psycopg2.connect(conn_url)
    conn.autocommit = True
    cur = conn.cursor()
    for col_name, col_type, col_extra in COLUMNS:
        sql = f'ALTER TABLE doctors ADD COLUMN IF NOT EXISTS "{col_name}" {col_type} {col_extra};'
        cur.execute(sql)
        print(f"  OK   {col_name} {col_type} {col_extra}")
    cur.close()
    conn.close()

print("\nMigration complete.")
