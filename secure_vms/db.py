import sqlite3, threading
from config import DB
_l = threading.Lock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE,pw TEXT,role TEXT);
CREATE TABLE IF NOT EXISTS cameras(id INTEGER PRIMARY KEY,name TEXT,source TEXT,zone TEXT,last_seen REAL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,ts REAL,camera_id INT,type TEXT,source TEXT,detail TEXT,score INT);
CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY,ts REAL,camera_id INT,score INT,level TEXT,status TEXT,
  summary TEXT,shot TEXT,clip TEXT,shot_sha TEXT,sha256 TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,ts REAL,user TEXT,ip TEXT,action TEXT);
CREATE TABLE IF NOT EXISTS logins(id INTEGER PRIMARY KEY,ts REAL,ip TEXT,username TEXT,ok INT);
"""
def init():
    with sqlite3.connect(DB) as c: c.executescript(SCHEMA)
def q(sql, args=(), one=False, commit=False):
    with _l:
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        cur = c.execute(sql, args); rows = [dict(r) for r in cur.fetchall()]
        c.commit(); lid = cur.lastrowid; c.close()
    if commit: return lid
    return (rows[0] if rows else None) if one else rows
