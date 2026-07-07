"""
Postgres persistence for Matador Mike (Railway provides DATABASE_URL
automatically once you attach a Postgres service to the project).

Tables:
- clients:   the businesses/people Mike is tracking work for
- deadlines: things due, optionally tied to a client
- tasks:     an in-progress scheduling negotiation with a third party
- messages:  every text in/out, tagged by which phone number the thread is with
"""

import os
import time
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]


@contextmanager
def get_conn():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                notes TEXT,
                created_at DOUBLE PRECISION NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deadlines (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES clients(id),
                client_name TEXT,              -- kept even without a matched client record
                description TEXT NOT NULL,
                due_date DATE NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',   -- open | done
                created_at DOUBLE PRECISION NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                party_phone TEXT NOT NULL,
                client_name TEXT,
                purpose TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',  -- pending | confirmed | declined
                confirmed_time TEXT,
                created_at DOUBLE PRECISION NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                thread_phone TEXT NOT NULL,
                role TEXT NOT NULL,           -- 'user' or 'assistant'
                content TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
            )
        """)


# ---------- messages ----------

def add_message(thread_phone: str, role: str, content: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO messages (thread_phone, role, content, created_at) VALUES (%s, %s, %s, %s)",
            (thread_phone, role, content, time.time()),
        )


def get_history(thread_phone: str, limit: int = 20):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT role, content FROM messages WHERE thread_phone = %s ORDER BY id ASC LIMIT %s",
            (thread_phone, limit),
        )
        return [{"role": r["role"], "content": r["content"]} for r in cur.fetchall()]


# ---------- clients ----------

def add_client(name: str, phone: str = None, email: str = None, notes: str = None) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clients (name, phone, email, notes, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (name, phone, email, notes, time.time()),
        )
        return cur.fetchone()["id"]


def find_client_by_name(name: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM clients WHERE name ILIKE %s ORDER BY id DESC LIMIT 1",
            (f"%{name}%",),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_clients():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM clients ORDER BY name ASC")
        return [r["name"] for r in cur.fetchall()]


# ---------- deadlines ----------

def add_deadline(description: str, due_date: str, client_name: str = None) -> int:
    client = find_client_by_name(client_name) if client_name else None
    client_id = client["id"] if client else None
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO deadlines (client_id, client_name, description, due_date, created_at)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (client_id, client_name, description, due_date, time.time()),
        )
        return cur.fetchone()["id"]


def get_upcoming_deadlines(days_ahead: int = 7):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM deadlines
               WHERE status = 'open' AND due_date <= CURRENT_DATE + %s
               ORDER BY due_date ASC""",
            (days_ahead,),
        )
        return [dict(r) for r in cur.fetchall()]


def mark_deadline_done(deadline_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE deadlines SET status = 'done' WHERE id = %s", (deadline_id,))


# ---------- tasks (scheduling negotiations) ----------

def create_task(party_phone: str, purpose: str, client_name: str = None) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tasks (party_phone, client_name, purpose, created_at)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (party_phone, client_name, purpose, time.time()),
        )
        return cur.fetchone()["id"]


def get_open_task_for(party_phone: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM tasks WHERE party_phone = %s AND status = 'pending' ORDER BY id DESC LIMIT 1",
            (party_phone,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_all_open_tasks():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC")
        return [dict(r) for r in cur.fetchall()]


def update_task_status(task_id: int, status: str, confirmed_time: str = None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tasks SET status = %s, confirmed_time = %s WHERE id = %s",
            (status, confirmed_time, task_id),
        )
