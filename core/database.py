import os
import datetime
import sqlite3
import pymysql
import pymysql.cursors
from pathlib import Path
from core.config import config, DATA_DIR

SQLITE_PATH = DATA_DIR / "security.db"

def get_mysql_connection(include_db=True):
    """Establishes a MySQL connection using PyMySQL"""
    host = config.get("mysql_host", "localhost")
    port = int(config.get("mysql_port", 3306))
    user = config.get("mysql_user", "root")
    password = config.get("mysql_password", "")
    db_name = config.get("mysql_db", "home_intruder_system")

    kwargs = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
        "connect_timeout": 5
    }
    if include_db:
        kwargs["database"] = db_name

    return pymysql.connect(**kwargs)

def get_connection():
    """
    Returns active database connection based on config.
    Defaults to MySQL via PyMySQL; falls back to SQLite if MySQL is unavailable.
    """
    db_type = config.get("db_type", "mysql")
    if db_type == "mysql":
        try:
            return get_mysql_connection(include_db=True), "mysql"
        except Exception as e:
            print(f"[Database] PyMySQL connection error: {e}. Falling back to SQLite.")

    # SQLite fallback
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn, "sqlite"

def init_db():
    """Initializes MySQL schema (and SQLite fallback schema)"""
    db_type = config.get("db_type", "mysql")
    
    if db_type == "mysql":
        try:
            # 1. Connect to MySQL server without selecting database first
            server_conn = get_mysql_connection(include_db=False)
            db_name = config.get("mysql_db", "home_intruder_system")
            with server_conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            server_conn.close()

            # 2. Connect to the database and ensure tables exist
            conn = get_mysql_connection(include_db=True)
            with conn.cursor() as cur:
                # Family members
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS family_members (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(191) NOT NULL,
                        relationship VARCHAR(100) NOT NULL,
                        registered_at DATETIME NOT NULL,
                        photo_path VARCHAR(255) NOT NULL,
                        face_label INT UNIQUE NOT NULL,
                        is_active TINYINT DEFAULT 1
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                # Intrusion events
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS intrusion_events (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        timestamp DATETIME NOT NULL,
                        event_type VARCHAR(100) NOT NULL,
                        confidence FLOAT,
                        snapshot_path VARCHAR(255),
                        email_sent TINYINT DEFAULT 0,
                        email_recipient VARCHAR(191),
                        notes TEXT
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                # Outbox emails
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS outbox_emails (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        timestamp DATETIME NOT NULL,
                        recipient VARCHAR(191) NOT NULL,
                        subject VARCHAR(255) NOT NULL,
                        body_html LONGTEXT NOT NULL,
                        attachment_path VARCHAR(255),
                        status VARCHAR(50) NOT NULL,
                        error_message TEXT
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            conn.close()
            print(f"[Database] PyMySQL initialized successfully on MySQL: `{db_name}`.")
            return True
        except Exception as e:
            print(f"[Database] Could not initialize MySQL via PyMySQL: {e}. Ensuring SQLite fallback is ready.")

    # SQLite schema fallback
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            relationship TEXT NOT NULL,
            registered_at TEXT NOT NULL,
            photo_path TEXT NOT NULL,
            face_label INTEGER UNIQUE NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS intrusion_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            confidence REAL,
            snapshot_path TEXT,
            email_sent INTEGER DEFAULT 0,
            email_recipient TEXT,
            notes TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS outbox_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            body_html TEXT NOT NULL,
            attachment_path TEXT,
            status TEXT NOT NULL,
            error_message TEXT
        )
    """)
    conn.commit()
    conn.close()
    return True

def _format_row(row):
    """Formats DB row dict and ensures datetime fields are formatted as strings for JSON serialization"""
    if not row:
        return row
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, (datetime.date, datetime.datetime)):
            d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return d

# --- Family Members Operations ---

def add_family_member(name: str, relationship: str, photo_path: str, face_label: int) -> int:
    conn, engine = get_connection()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if engine == "mysql":
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO family_members (name, relationship, registered_at, photo_path, face_label, is_active)
                VALUES (%s, %s, %s, %s, %s, 1)
            """, (name, relationship, now_str, photo_path, face_label))
            member_id = cur.lastrowid
        conn.close()
        return member_id
    else:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO family_members (name, relationship, registered_at, photo_path, face_label, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (name, relationship, now_str, photo_path, face_label))
        member_id = cur.lastrowid
        conn.commit()
        conn.close()
        return member_id

def get_all_family_members(only_active=False):
    conn, engine = get_connection()
    if engine == "mysql":
        with conn.cursor() as cur:
            if only_active:
                cur.execute("SELECT * FROM family_members WHERE is_active = 1 ORDER BY id DESC")
            else:
                cur.execute("SELECT * FROM family_members ORDER BY id DESC")
            rows = [_format_row(r) for r in cur.fetchall()]
        conn.close()
        return rows
    else:
        cur = conn.cursor()
        if only_active:
            cur.execute("SELECT * FROM family_members WHERE is_active = 1 ORDER BY id DESC")
        else:
            cur.execute("SELECT * FROM family_members ORDER BY id DESC")
        rows = [_format_row(dict(r)) for r in cur.fetchall()]
        conn.close()
        return rows

def get_family_member_by_id(member_id: int):
    conn, engine = get_connection()
    if engine == "mysql":
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM family_members WHERE id = %s", (member_id,))
            row = cur.fetchone()
        conn.close()
        return _format_row(row) if row else None
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM family_members WHERE id = ?", (member_id,))
        row = cur.fetchone()
        conn.close()
        return _format_row(dict(row)) if row else None

def get_next_face_label() -> int:
    conn, engine = get_connection()
    if engine == "mysql":
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(face_label) AS max_label FROM family_members")
            res = cur.fetchone()
            val = res["max_label"] if res else None
        conn.close()
        return (val + 1) if val is not None else 1
    else:
        cur = conn.cursor()
        cur.execute("SELECT MAX(face_label) FROM family_members")
        val = cur.fetchone()[0]
        conn.close()
        return (val + 1) if val is not None else 1

def delete_family_member(member_id: int):
    conn, engine = get_connection()
    if engine == "mysql":
        with conn.cursor() as cur:
            cur.execute("DELETE FROM family_members WHERE id = %s", (member_id,))
        conn.close()
    else:
        cur = conn.cursor()
        cur.execute("DELETE FROM family_members WHERE id = ?", (member_id,))
        conn.commit()
        conn.close()

# --- Intrusion Events Operations ---

def log_intrusion_event(event_type: str, confidence: float, snapshot_path: str, email_sent: bool, recipient: str, notes: str = "") -> int:
    conn, engine = get_connection()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if engine == "mysql":
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO intrusion_events (timestamp, event_type, confidence, snapshot_path, email_sent, email_recipient, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (now_str, event_type, confidence, snapshot_path, 1 if email_sent else 0, recipient, notes))
            event_id = cur.lastrowid
        conn.close()
        return event_id
    else:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO intrusion_events (timestamp, event_type, confidence, snapshot_path, email_sent, email_recipient, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (now_str, event_type, confidence, snapshot_path, 1 if email_sent else 0, recipient, notes))
        event_id = cur.lastrowid
        conn.commit()
        conn.close()
        return event_id

def get_recent_intrusion_events(limit: int = 50):
    conn, engine = get_connection()
    if engine == "mysql":
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM intrusion_events ORDER BY id DESC LIMIT %s", (limit,))
            rows = [_format_row(r) for r in cur.fetchall()]
        conn.close()
        return rows
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM intrusion_events ORDER BY id DESC LIMIT ?", (limit,))
        rows = [_format_row(dict(r)) for r in cur.fetchall()]
        conn.close()
        return rows

def get_event_stats():
    conn, engine = get_connection()
    if engine == "mysql":
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM intrusion_events")
            total_events = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) AS cnt FROM family_members WHERE is_active = 1")
            total_family = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) AS cnt FROM outbox_emails")
            total_emails = cur.fetchone()["cnt"]
        conn.close()
        return {
            "total_intrusions": total_events,
            "registered_family": total_family,
            "emails_dispatched": total_emails,
            "db_engine": "MySQL (PyMySQL)"
        }
    else:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM intrusion_events")
        total_events = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM family_members WHERE is_active = 1")
        total_family = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM outbox_emails")
        total_emails = cur.fetchone()[0]
        conn.close()
        return {
            "total_intrusions": total_events,
            "registered_family": total_family,
            "emails_dispatched": total_emails,
            "db_engine": "SQLite (Fallback)"
        }

# --- Outbox Emails Operations ---

def log_outbox_email(recipient: str, subject: str, body_html: str, attachment_path: str, status: str, error_message: str = ""):
    conn, engine = get_connection()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if engine == "mysql":
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO outbox_emails (timestamp, recipient, subject, body_html, attachment_path, status, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (now_str, recipient, subject, body_html, attachment_path, status, error_message))
            email_id = cur.lastrowid
        conn.close()
        return email_id
    else:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO outbox_emails (timestamp, recipient, subject, body_html, attachment_path, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (now_str, recipient, subject, body_html, attachment_path, status, error_message))
        email_id = cur.lastrowid
        conn.commit()
        conn.close()
        return email_id

def get_recent_emails(limit: int = 20):
    conn, engine = get_connection()
    if engine == "mysql":
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM outbox_emails ORDER BY id DESC LIMIT %s", (limit,))
            rows = [_format_row(r) for r in cur.fetchall()]
        conn.close()
        return rows
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM outbox_emails ORDER BY id DESC LIMIT ?", (limit,))
        rows = [_format_row(dict(r)) for r in cur.fetchall()]
        conn.close()
        return rows

def test_mysql_connection_params(host, port, user, password, db_name="home_intruder_system"):
    """Tests connection parameters with PyMySQL"""
    try:
        conn = pymysql.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            charset="utf8mb4",
            connect_timeout=4
        )
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.select_db(db_name)
        conn.close()
        return True, f"Successfully connected to MySQL server and selected/created database `{db_name}`!"
    except Exception as e:
        return False, f"MySQL connection failed: {str(e)}"

# Initialize DB on module import
init_db()
