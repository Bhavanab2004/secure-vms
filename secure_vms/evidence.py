import cv2, hashlib, os, db
from config import EVID
REG = {}  # camera_id -> Worker (ring buffer of recent frames)
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()
def capture(iid, cam):
    w = REG.get(cam); frames = list(w.buf) if w else []
    if not frames: return
    shot, clip = f'inc{iid}.jpg', f'inc{iid}.mp4'
    cv2.imwrite(os.path.join(EVID, shot), frames[-1])
    h, wd = frames[0].shape[:2]
    vw = cv2.VideoWriter(os.path.join(EVID, clip), cv2.VideoWriter_fourcc(*'mp4v'), w.fps, (wd, h))
    for fr in frames: vw.write(fr)
    vw.release()
    db.q("UPDATE incidents SET shot=?,clip=?,shot_sha=?,sha256=? WHERE id=?",
         (shot, clip, sha(os.path.join(EVID, shot)), sha(os.path.join(EVID, clip)), iid), commit=True)
def verify(iid):
    r = db.q("SELECT * FROM incidents WHERE id=?", (iid,), one=True)
    if not r or not r['clip']: return None
    return sha(os.path.join(EVID, r['clip'])) == r['sha256'] and sha(os.path.join(EVID, r['shot'])) == r['shot_sha']
