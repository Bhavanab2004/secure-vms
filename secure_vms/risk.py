"""Risk & event engine: weights per event, correlation window, AI x tamper x cyber multiplier."""
import time, db, evidence, alerts
W = {'weapon': 60, 'fighting': 50, 'intrusion': 40, 'loitering': 20, 'tamper_covered': 45, 'tamper_frozen': 35,
     'tamper_disconnected': 40, 'failed_login': 15, 'unauthorized_access': 30, 'suspicious_network': 30, 'camera_compromise': 70}
AI = {'weapon', 'fighting', 'intrusion', 'loitering'}
WINDOW, COOLDOWN = 60, 20
RANK = {'Low': 0, 'Medium': 1, 'High': 2, 'Critical': 3}
_last = {}
def level(s): return 'Critical' if s >= 100 else 'High' if s >= 70 else 'Medium' if s >= 35 else 'Low'
def add_event(cam, etype, detail=''):
    now = time.time(); k = (cam, etype)
    if now - _last.get(k, 0) < COOLDOWN: return
    _last[k] = now
    src = 'ai' if etype in AI else 'tamper' if etype.startswith('tamper') else 'cyber'
    db.q("INSERT INTO events(ts,camera_id,type,source,detail,score) VALUES(?,?,?,?,?,?)", (now, cam, etype, src, detail, W[etype]), commit=True)
    rows = db.q("SELECT type,source FROM events WHERE ts>? AND (camera_id IS ? OR camera_id IS NULL)", (now - WINDOW, cam))
    score = sum(W[r['type']] for r in rows)
    if len({r['source'] for r in rows}) > 1: score = int(score * 1.5)   # correlated multi-domain activity
    lv = level(score)
    if lv == 'Low': return
    summary = f"{lv} risk ({score}): " + ', '.join(sorted({r['type'] for r in rows})) + f" | latest: {detail}"
    inc = db.q("SELECT * FROM incidents WHERE camera_id IS ? AND status!='Closed' AND ts>? ORDER BY id DESC", (cam, now - WINDOW * 5), one=True)
    if inc:
        if score > inc['score']:
            db.q("UPDATE incidents SET score=?,level=?,summary=? WHERE id=?", (score, lv, summary, inc['id']), commit=True)
            if RANK[lv] > RANK[inc['level']]:
                evidence.capture(inc['id'], cam); alerts.notify(inc['id'], lv, summary)
    else:
        iid = db.q("INSERT INTO incidents(ts,camera_id,score,level,status,summary) VALUES(?,?,?,?,'Open',?)", (now, cam, score, lv, summary), commit=True)
        evidence.capture(iid, cam); alerts.notify(iid, lv, summary)
