import smtplib, threading, os, db
from email.message import EmailMessage
from config import SMTP, EVID
def notify(iid, level, summary):  # dashboard alerts are served from the incidents table; this sends email
    if SMTP['host'] and SMTP['to']: threading.Thread(target=_send, args=(iid, level, summary), daemon=True).start()
def _send(iid, level, summary):
    try:
        m = EmailMessage(); m['Subject'] = f'[{level}] Security incident #{iid}'; m['From'] = SMTP['user']; m['To'] = SMTP['to']
        m.set_content(summary)
        inc = db.q("SELECT shot FROM incidents WHERE id=?", (iid,), one=True)
        if inc and inc['shot']:
            m.add_attachment(open(os.path.join(EVID, inc['shot']), 'rb').read(), maintype='image', subtype='jpeg', filename=inc['shot'])
        with smtplib.SMTP(SMTP['host'], SMTP['port']) as s:
            s.starttls(); s.login(SMTP['user'], SMTP['pw']); s.send_message(m)
    except Exception as e: print('email failed:', e)
