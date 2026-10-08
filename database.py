# database.py — Optimized MySQL layer (pooling + fewer queries)
import os
import time
import mysql.connector
from mysql.connector import Error, pooling
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", "3306")),
    "user":     os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "college_complaints"),
}

# SSL only when not localhost
if DB_CONFIG["host"] != "localhost":
    DB_CONFIG["ssl_disabled"] = False
    DB_CONFIG["ssl_verify_cert"] = False
else:
    DB_CONFIG["ssl_disabled"] = True

# ---------- Connection pool ----------
_pool = None

def get_connection():
    """Get a pooled connection — reused across requests."""
    global _pool
    if _pool is None:
        try:
            _pool = pooling.MySQLConnectionPool(
                pool_name="college_pool",
                pool_size=5,
                pool_reset_session=True,
                **DB_CONFIG
            )
        except Error as e:
            print("Pool error:", e)
            try:
                return mysql.connector.connect(**DB_CONFIG)
            except Error as e2:
                print("Connection error:", e2)
                return None
    try:
        return _pool.get_connection()
    except Error as e:
        print("Get connection error:", e)
        return None

# ---------- Simple in-memory cache ----------
_cache = {}
CACHE_TTL = 10  # seconds

def _cache_get(key):
    if key in _cache:
        val, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
    return None

def _cache_set(key, val):
    _cache[key] = (val, time.time())

def clear_cache():
    _cache.clear()

# ---------- Setup ----------
def init_db():
    conn = get_connection()
    if conn is None:
        return
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS complaints (
        complaint_id INT AUTO_INCREMENT PRIMARY KEY,
        student_name VARCHAR(100) NOT NULL,
        roll_number VARCHAR(30) NOT NULL,
        student_class VARCHAR(30) NOT NULL,
        category VARCHAR(50) NOT NULL,
        description TEXT NOT NULL,
        date_submitted VARCHAR(30) NOT NULL,
        status VARCHAR(20) NOT NULL,
        remark VARCHAR(255),
        is_archived INT DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS status_history (
        history_id INT AUTO_INCREMENT PRIMARY KEY,
        complaint_id INT NOT NULL,
        old_status VARCHAR(20),
        new_status VARCHAR(20),
        change_time VARCHAR(30),
        FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id) ON DELETE CASCADE)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS admins (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password VARCHAR(100) NOT NULL,
        created_at VARCHAR(30))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS inspectors (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        password VARCHAR(100) UNIQUE NOT NULL,
        created_by VARCHAR(50),
        created_at VARCHAR(30))""")
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM admins")
    if cur.fetchone()[0] == 0:
        from datetime import datetime
        cur.execute("INSERT INTO admins (username, password, created_at) VALUES (%s, %s, %s)",
                    ("admin", "admin123", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    cur.close()
    conn.close()

def _row_to_dict(cursor, row):
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))

# ---------- Complaints ----------
def insert_complaint(student_name, roll_number, student_class, category, description, date_submitted):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""INSERT INTO complaints
        (student_name, roll_number, student_class, category, description,
         date_submitted, status, remark, is_archived)
        VALUES (%s, %s, %s, %s, %s, %s, 'Pending', '', 0)""",
        (student_name, roll_number, student_class, category, description, date_submitted))
    conn.commit()
    new_id = cur.lastrowid
    cur.close()
    conn.close()
    clear_cache()
    return new_id

def get_all_complaints(include_archived=False, student_class=None, sort_by="id"):
    cache_key = f"all:{include_archived}:{student_class}:{sort_by}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    conn = get_connection()
    cur = conn.cursor()
    q = "SELECT * FROM complaints WHERE 1=1"
    params = []
    if not include_archived:
        q += " AND is_archived = 0"
    if student_class:
        q += " AND student_class = %s"
        params.append(student_class)
    if sort_by == "date":
        q += " ORDER BY date_submitted DESC"
    elif sort_by == "class":
        q += " ORDER BY student_class ASC, complaint_id ASC"
    elif sort_by == "category":
        q += " ORDER BY category ASC, complaint_id ASC"
    elif sort_by == "status":
        q += " ORDER BY FIELD(status,'Pending','In Progress','Resolved'), complaint_id ASC"
    else:
        q += " ORDER BY complaint_id ASC"
    cur.execute(q, tuple(params))
    rows = cur.fetchall()
    result = [_row_to_dict(cur, r) for r in rows]
    cur.close()
    conn.close()
    _cache_set(cache_key, result)
    return result

def get_complaint_by_id(complaint_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM complaints WHERE complaint_id = %s", (complaint_id,))
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None
    cur.close()
    conn.close()
    return result

def get_complaints_by_roll(roll_number):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""SELECT * FROM complaints
        WHERE LOWER(TRIM(roll_number)) = LOWER(TRIM(%s))
        ORDER BY complaint_id ASC""", (roll_number,))
    rows = cur.fetchall()
    result = [_row_to_dict(cur, r) for r in rows]
    cur.close()
    conn.close()
    return result

def update_complaint_status(complaint_id, new_status, remark=""):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE complaints SET status = %s, remark = %s WHERE complaint_id = %s",
                (new_status, remark, complaint_id))
    conn.commit()
    ok = cur.rowcount > 0
    cur.close()
    conn.close()
    clear_cache()
    return ok

def delete_complaint(complaint_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM status_history WHERE complaint_id = %s", (complaint_id,))
    cur.execute("DELETE FROM complaints WHERE complaint_id = %s", (complaint_id,))
    conn.commit()
    ok = cur.rowcount > 0
    cur.close()
    conn.close()
    clear_cache()
    return ok

def archive_complaint(complaint_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE complaints SET is_archived = 1 WHERE complaint_id = %s", (complaint_id,))
    conn.commit()
    ok = cur.rowcount > 0
    cur.close()
    conn.close()
    clear_cache()
    return ok

def add_status_history(complaint_id, old_status, new_status, change_time):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""INSERT INTO status_history
        (complaint_id, old_status, new_status, change_time) VALUES (%s, %s, %s, %s)""",
        (complaint_id, old_status, new_status, change_time))
    conn.commit()
    cur.close()
    conn.close()

def get_status_history(complaint_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""SELECT old_status, new_status, change_time FROM status_history
        WHERE complaint_id = %s ORDER BY history_id ASC""", (complaint_id,))
    rows = cur.fetchall()
    result = [{"old_status": r[0], "new_status": r[1], "change_time": r[2]} for r in rows]
    cur.close()
    conn.close()
    return result

def get_pending_complaints_fifo():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""SELECT * FROM complaints
        WHERE status = 'Pending' AND is_archived = 0
        ORDER BY complaint_id ASC""")
    rows = cur.fetchall()
    result = [_row_to_dict(cur, r) for r in rows]
    cur.close()
    conn.close()
    return result

# ---------- FAST combined stats + dashboard (ONE round-trip) ----------
def get_full_dashboard_data(student_class=None):
    """Single query returning stats + all dashboard data."""
    cache_key = f"dash:{student_class}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    conn = get_connection()
    cur = conn.cursor()

    where = "WHERE is_archived = 0"
    params = []
    if student_class:
        where += " AND student_class = %s"
        params.append(student_class)

    # ---- Single combined query using UNION ALL ----
    # This gets category counts, class counts, status counts, date counts
    # all in one round-trip.
    combined_query = f"""
        SELECT 'category' AS kind, category AS label, COUNT(*) AS cnt
        FROM complaints {where}
        GROUP BY category
        UNION ALL
        SELECT 'class' AS kind, student_class AS label, COUNT(*) AS cnt
        FROM complaints {where}
        GROUP BY student_class
        UNION ALL
        SELECT 'status' AS kind, status AS label, COUNT(*) AS cnt
        FROM complaints {where}
        GROUP BY status
        UNION ALL
        SELECT 'date' AS kind, LEFT(date_submitted, 10) AS label, COUNT(*) AS cnt
        FROM complaints {where}
        GROUP BY LEFT(date_submitted, 10)
    """
    cur.execute(combined_query, tuple(params) * 4)
    rows = cur.fetchall()

    by_category = []
    by_class = []
    by_status = {"Pending": 0, "In Progress": 0, "Resolved": 0}
    by_date = []

    for kind, label, cnt in rows:
        if kind == "category":
            by_category.append({"label": label, "count": cnt})
        elif kind == "class":
            by_class.append({"label": label, "count": cnt})
        elif kind == "status":
            by_status[label] = cnt
        elif kind == "date":
            by_date.append({"label": str(label), "count": cnt})

    by_category.sort(key=lambda x: -x["count"])
    by_class.sort(key=lambda x: -x["count"])
    by_date.sort(key=lambda x: x["label"])

    total = sum(by_status.values())
    t = total if total > 0 else 1

    for row in by_category:
        row["percent"] = round(row["count"] * 100.0 / t, 1)
    for row in by_class:
        row["percent"] = round(row["count"] * 100.0 / t, 1)
    for row in by_date:
        row["percent"] = round(row["count"] * 100.0 / t, 1)
    status_pct = {k: round(v * 100.0 / t, 1) for k, v in by_status.items()}

    result = {
        "total": total,
        "pending": by_status.get("Pending", 0),
        "progress": by_status.get("In Progress", 0),
        "resolved": by_status.get("Resolved", 0),
        "by_category": by_category,
        "by_class": by_class,
        "by_status": by_status,
        "status_pct": status_pct,
        "by_date": by_date,
    }

    cur.close()
    conn.close()
    _cache_set(cache_key, result)
    return result

def get_complaint_stats(student_class=None):
    """Kept for compatibility — calls the combined function."""
    d = get_full_dashboard_data(student_class)
    return {
        "total": d["total"],
        "pending": d["pending"],
        "progress": d["progress"],
        "resolved": d["resolved"],
    }

def get_dashboard_data(student_class=None):
    return get_full_dashboard_data(student_class)

def get_category_summary():
    d = get_full_dashboard_data(None)
    return [{"category": r["label"], "count": r["count"], "percent": r["percent"]}
            for r in d["by_category"]]

def get_class_summary():
    d = get_full_dashboard_data(None)
    return [r["label"] for r in d["by_class"]]

# ---------- Admins ----------
def verify_admin(username, password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM admins WHERE username = %s AND password = %s", (username, password))
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None
    cur.close()
    conn.close()
    return result

def get_all_admins():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, created_at FROM admins ORDER BY id ASC")
    rows = cur.fetchall()
    result = [{"id": r[0], "username": r[1], "created_at": r[2]} for r in rows]
    cur.close()
    conn.close()
    return result

def add_admin(username, password, created_at):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO admins (username, password, created_at) VALUES (%s, %s, %s)",
                    (username, password, created_at))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Admin created successfully."
    except Error:
        conn.close()
        return False, "Username already exists."

def delete_admin(admin_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM admins")
    count = cur.fetchone()[0]
    if count <= 1:
        cur.close()
        conn.close()
        return False, "Cannot delete the last admin."
    cur.execute("DELETE FROM admins WHERE id = %s", (admin_id,))
    conn.commit()
    ok = cur.rowcount > 0
    cur.close()
    conn.close()
    return ok, "Admin deleted." if ok else "Admin not found."

# ---------- Inspectors ----------
def verify_inspector(password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM inspectors WHERE password = %s", (password,))
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None
    cur.close()
    conn.close()
    return result

def get_all_inspectors():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM inspectors ORDER BY id ASC")
    rows = cur.fetchall()
    result = [_row_to_dict(cur, r) for r in rows]
    cur.close()
    conn.close()
    return result

def add_inspector(name, password, created_by, created_at):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""INSERT INTO inspectors
            (name, password, created_by, created_at) VALUES (%s, %s, %s, %s)""",
            (name, password, created_by, created_at))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Inspector created successfully."
    except Error:
        conn.close()
        return False, "This password is already in use."

def delete_inspector(inspector_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM inspectors WHERE id = %s", (inspector_id,))
    conn.commit()
    ok = cur.rowcount > 0
    cur.close()
    conn.close()
    return ok, "Inspector deleted." if ok else "Inspector not found."
