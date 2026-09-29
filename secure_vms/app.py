import os, io, csv, time, functools
from flask import Flask, request, session, redirect, render_template, jsonify, Response, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import db, cyber, evidence, worker
from config import SECRET, EVID, UPLOADS

app = Flask(__name__); app.secret_key = SECRET
ROLES = {'viewer': 1, 'officer': 2, 'admin': 3}
workers = {}

def audit(action):
    db.q("INSERT INTO audit(ts,user,ip,action) VALUES(?,?,?,?)", (time.time(), session.get('user', '-'), request.remote_addr, action), commit=True)

def need(role):  # RBAC decorator
    def deco(fn):
        @functools.wraps(fn)
        def w(*a, **k):
            api = request.path.startswith(('/api', '/video'))
            if 'user' not in session:
                if api: cyber.unauthorized(request.remote_addr, request.path)
                return (jsonify(error='auth'), 401) if api else redirect('/login')
            if ROLES[session['role']] < ROLES[role]:
                cyber.unauthorized(request.remote_addr, f"{session['user']} denied {request.path}"); audit('DENIED ' + request.path)
                return jsonify(error='forbidden'), 403
            return fn(*a, **k)
        return w
    return deco

@app.before_request
def _rate():
    if not request.path.startswith('/video'): cyber.rate(request.remote_addr)

def start(cam):
    if cam['id'] not in workers: workers[cam['id']] = worker.Worker(cam); workers[cam['id']].start()

@app.route('/login', methods=['GET', 'POST'])
def login():
    err = ''
    if request.method == 'POST':
        u, p = request.form['username'], request.form['password']
        row = db.q("SELECT * FROM users WHERE username=?", (u,), one=True)
        ok = bool(row and check_password_hash(row['pw'], p))
        db.q("INSERT INTO logins(ts,ip,username,ok) VALUES(?,?,?,?)", (time.time(), request.remote_addr, u, int(ok)), commit=True)
        if ok: session.update(user=u, role=row['role']); audit('login'); return redirect('/')
        cyber.failed_login(request.remote_addr, u); err = 'Invalid credentials'
    return render_template('login.html', err=err)

@app.route('/logout')
def logout(): audit('logout'); session.clear(); return redirect('/login')

@app.route('/')
@need('viewer')
def home(): return render_template('dashboard.html', user=session['user'], role=session['role'])

@app.route('/video/<int:cid>')
@need('viewer')
def video(cid):
    w = workers.get(cid)
    if not w: return 'no such camera', 404
    def gen():
        while True:
            if w.jpg: yield b'--f\r\nContent-Type: image/jpeg\r\n\r\n' + w.jpg + b'\r\n'
            time.sleep(.1)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=f')

@app.route('/api/stats')
@need('viewer')
def stats():
    lv = {r['level']: r['n'] for r in db.q("SELECT level,count(*) n FROM incidents GROUP BY level")}
    ty = {r['type']: r['n'] for r in db.q("SELECT type,count(*) n FROM events GROUP BY type")}
    tr = db.q("SELECT date(ts,'unixepoch','localtime') d,count(*) n FROM incidents GROUP BY d ORDER BY d DESC LIMIT 7")[::-1]
    cams = [dict(id=c['id'], name=c['name'], status=workers[c['id']].status if c['id'] in workers else 'stopped') for c in db.q("SELECT * FROM cameras")]
    op = db.q("SELECT count(*) n FROM incidents WHERE status!='Closed'", one=True)['n']
    return jsonify(levels=lv, types=ty, trend=tr, cameras=cams, open=op)

@app.route('/api/incidents')
@need('viewer')
def incidents():
    return jsonify(db.q("SELECT i.*,c.name cam FROM incidents i LEFT JOIN cameras c ON c.id=i.camera_id ORDER BY i.id DESC LIMIT ?", (int(request.args.get('limit', 100)),)))

@app.route('/api/incidents/<int:iid>', methods=['POST'])
@need('officer')
def set_status(iid):
    st = request.json.get('status')
    if st not in ('Open', 'Investigating', 'Resolved', 'Closed'): return jsonify(error='bad status'), 400
    db.q("UPDATE incidents SET status=? WHERE id=?", (st, iid), commit=True); audit(f'incident {iid} -> {st}'); return jsonify(ok=1)

@app.route('/api/evidence/<int:iid>/<kind>')
@need('viewer')
def get_evidence(iid, kind):
    r = db.q("SELECT shot,clip FROM incidents WHERE id=?", (iid,), one=True)
    if not r or kind not in ('shot', 'clip') or not r[kind]: return 'not found', 404
    audit(f'evidence {iid} {kind}'); return send_file(os.path.join(EVID, r[kind]))

@app.route('/api/verify/<int:iid>')
@need('officer')
def verify(iid): audit(f'verify {iid}'); return jsonify(intact=evidence.verify(iid))

@app.route('/api/cameras', methods=['GET', 'POST'])
@need('viewer')
def cameras():
    if request.method == 'GET': return jsonify(db.q("SELECT * FROM cameras"))
    if ROLES[session['role']] < 3: return jsonify(error='forbidden'), 403
    d = request.json
    cid = db.q("INSERT INTO cameras(name,source,zone) VALUES(?,?,?)", (d['name'], d['source'], d.get('zone') or None), commit=True)
    start(db.q("SELECT * FROM cameras WHERE id=?", (cid,), one=True)); audit('camera add ' + d['name']); return jsonify(id=cid)

@app.route('/api/cameras/<int:cid>', methods=['DELETE'])
@need('admin')
def del_camera(cid):
    w = workers.pop(cid, None)
    if w: w.run_flag = False
    evidence.REG.pop(cid, None); db.q("DELETE FROM cameras WHERE id=?", (cid,), commit=True); audit(f'camera del {cid}'); return jsonify(ok=1)

@app.route('/api/upload', methods=['POST'])
@need('officer')
def upload():
    f = request.files['file']; p = os.path.join(UPLOADS, f"{int(time.time())}_{secure_filename(f.filename)}"); f.save(p)
    cid = db.q("INSERT INTO cameras(name,source) VALUES(?,?)", ('Upload: ' + f.filename, p), commit=True)
    start(db.q("SELECT * FROM cameras WHERE id=?", (cid,), one=True)); audit('upload ' + f.filename); return jsonify(id=cid)

@app.route('/api/users', methods=['GET', 'POST'])
@need('admin')
def users():
    if request.method == 'POST':
        d = request.json
        if d['role'] not in ROLES: return jsonify(error='bad role'), 400
        db.q("INSERT INTO users(username,pw,role) VALUES(?,?,?)", (d['username'], generate_password_hash(d['password']), d['role']), commit=True)
        audit('user add ' + d['username'])
    return jsonify(db.q("SELECT id,username,role FROM users"))

@app.route('/api/audit')
@need('admin')
def audit_log(): return jsonify(db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 100"))

@app.route('/api/report')
@need('officer')
def report():
    o = io.StringIO(); w = csv.writer(o); w.writerow(['id', 'time', 'camera', 'level', 'score', 'status', 'summary', 'sha256'])
    for r in db.q("SELECT i.*,c.name cam FROM incidents i LEFT JOIN cameras c ON c.id=i.camera_id ORDER BY i.id"):
        w.writerow([r['id'], time.strftime('%F %T', time.localtime(r['ts'])), r['cam'], r['level'], r['score'], r['status'], r['summary'], r['sha256']])
    audit('report'); return Response(o.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=security_report.csv'})

if __name__ == '__main__':
    db.init()
    if not db.q("SELECT 1 FROM users"):
        db.q("INSERT INTO users(username,pw,role) VALUES('admin',?,'admin')", (generate_password_hash('admin123'),), commit=True)
        print('>>> Default login: admin / admin123  (change it: create a new admin in the Admin tab)')
    for c in db.q("SELECT * FROM cameras"): start(c)
    cyber.start_monitor(lambda: db.q("SELECT * FROM cameras"))
    app.run(host='127.0.0.1', port=5000, threaded=True)
