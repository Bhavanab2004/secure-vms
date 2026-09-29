import time, socket, threading, collections
from urllib.parse import urlparse
import db, risk
FAILS = collections.defaultdict(list); REQ = collections.defaultdict(collections.deque)
def failed_login(ip, user):
    t = time.time(); FAILS[ip] = [x for x in FAILS[ip] if t - x < 300] + [t]
    if len(FAILS[ip]) >= 5: risk.add_event(None, 'failed_login', f'{len(FAILS[ip])} failed logins from {ip} (user "{user}")')
def unauthorized(ip, what): risk.add_event(None, 'unauthorized_access', f'{ip} -> {what}')
def rate(ip):
    q = REQ[ip]; t = time.time(); q.append(t)
    while q and t - q[0] > 10: q.popleft()
    if len(q) > 200: risk.add_event(None, 'suspicious_network', f'{ip}: {len(q)} requests in 10s')
def _open(h, p):
    try:
        with socket.create_connection((h, p), timeout=1): return True
    except OSError: return False
def start_monitor(get_cams):
    """Network cameras only: flags newly opened ports (compromise) and exposed telnet."""
    def loop():
        base = {}
        while True:
            for c in get_cams():
                u = urlparse(str(c['source']))
                if not u.hostname: continue
                op = {p for p in (21, 22, 23, 80, 554, 2323, 8080) if _open(u.hostname, p)}
                b = base.setdefault(c['id'], op)
                if op - b: risk.add_event(c['id'], 'camera_compromise', f'new open ports {sorted(op - b)} on {u.hostname}')
                if op & {23, 2323}: risk.add_event(c['id'], 'suspicious_network', f'telnet exposed on {u.hostname}')
            time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()
