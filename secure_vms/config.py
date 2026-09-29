import os
BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'data', 'vms.db')
EVID = os.path.join(BASE, 'data', 'evidence')
UPLOADS = os.path.join(BASE, 'data', 'uploads')
MODELS = os.path.join(BASE, 'models')
SECRET = os.environ.get('VMS_SECRET', 'change-me-in-production')
SMTP = dict(host=os.environ.get('SMTP_HOST'), port=int(os.environ.get('SMTP_PORT', 587)),
            user=os.environ.get('SMTP_USER'), pw=os.environ.get('SMTP_PASS'), to=os.environ.get('ALERT_TO'))
for d in (os.path.dirname(DB), EVID, UPLOADS, MODELS):
    os.makedirs(d, exist_ok=True)
