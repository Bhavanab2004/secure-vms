import os, json, time, collections, threading, cv2, numpy as np
from config import MODELS
try: from ultralytics import YOLO
except Exception: YOLO = None
LOCK = threading.Lock()
def _load(name, fallback=None):
    if not YOLO: return None
    p = os.path.join(MODELS, name)
    try:
        if os.path.exists(p): return YOLO(p)
        return YOLO(fallback) if fallback else None
    except Exception as e:
        print('model load failed:', name, e); return None
OBJ = _load('yolov8n.pt', 'yolov8n.pt')   # person/object (auto-downloads on first run)
WEAP = _load('weapon.pt')                 # optional custom weapon detector

# Load the new video-based classifier
try:
    import dcsass_infer
    cls_path = os.path.join(MODELS, 'dcsass_video_clf.pt')
    CLS = dcsass_infer.DcsassPredictor(cls_path) if os.path.exists(cls_path) else None
except Exception as e:
    print('Failed to load video classifier:', e)
    CLS = None

print('models -> object:', bool(OBJ), '| weapon:', bool(WEAP), '| dcsass:', bool(CLS))
FIGHT = {'fighting', 'assault', 'abuse'}; GUN = {'shooting'}; COCO_W = {'knife', 'baseball bat', 'scissors'}
LOITER = 20  # seconds

class Detector:
    def __init__(s, zone):
        s.poly = np.array(json.loads(zone), float) if zone else None
        s.tr = {}; s.nid = 0; s.hist = collections.deque(maxlen=3)
        s.v_buf = collections.deque(maxlen=16)
    def run(s, f):
        ev = []; h, w = f.shape[:2]; now = time.time(); persons = []; fc = f.copy()
        with LOCK:
            r = OBJ(f, verbose=False, conf=.4)[0] if OBJ else None
            wr = WEAP(f, verbose=False, conf=.5)[0] if WEAP else None
        def box(b, n, col):
            x1, y1, x2, y2 = map(int, b.xyxy[0])
            cv2.rectangle(f, (x1, y1), (x2, y2), col, 2); cv2.putText(f, n, (x1, y1 - 4), 0, .5, col, 1)
            return x1, y1, x2, y2
        if r is not None:
            for b in r.boxes:
                n = r.names[int(b.cls)]
                if n == 'person': persons.append(box(b, n, (0, 200, 0)))
                elif n in COCO_W and not WEAP: box(b, n, (0, 0, 255)); ev.append(('weapon', n))
        if wr is not None:
            for b in wr.boxes: box(b, wr.names[int(b.cls)], (0, 0, 255)); ev.append(('weapon', wr.names[int(b.cls)]))
        if s.poly is not None:  # restricted-area intrusion
            p = (s.poly * [w, h]).astype(np.int32); cv2.polylines(f, [p], True, (0, 0, 255), 2)
            for x1, y1, x2, y2 in persons:
                if cv2.pointPolygonTest(p, (float((x1 + x2) / 2), float(y2)), False) >= 0:
                    ev.append(('intrusion', 'person inside restricted zone'))
        used = set()  # loitering via simple centroid tracker
        for bx in persons:
            cx, cy = (bx[0] + bx[2]) / 2, bx[3]
            cand = [(tid, t) for tid, t in s.tr.items() if tid not in used and np.hypot(t['x'] - cx, t['y'] - cy) < 80]
            if cand:
                tid, t = min(cand, key=lambda z: np.hypot(z[1]['x'] - cx, z[1]['y'] - cy))
                t['x'], t['y'], t['seen'] = cx, cy, now
            else:
                s.nid += 1; tid = s.nid; s.tr[tid] = t = dict(x=cx, y=cy, x0=cx, y0=cy, t0=now, seen=now)
            used.add(tid)
            if np.hypot(t['x'] - t['x0'], t['y'] - t['y0']) > 120: t['x0'], t['y0'], t['t0'] = cx, cy, now
            if now - t['t0'] > LOITER: ev.append(('loitering', f'person #{tid} for {int(now - t["t0"])}s'))
        s.tr = {k: v for k, v in s.tr.items() if now - v['seen'] < 3}
        s.v_buf.append(fc)
        if persons and CLS and len(s.v_buf) == 16:  # fighting / shooting from the DCSASS classifier
            with LOCK: out = CLS.predict_frames(list(s.v_buf))
            name = out['label'].lower(); conf = out['confidence']
            cv2.putText(f, f'{name} {conf:.2f}', (8, 20), 0, .6, (255, 255, 0), 2)
            s.hist.append(name if name in (FIGHT | GUN) and conf > .6 else None)
            hits = [x for x in s.hist if x]
            if len(hits) >= 2: ev.append(('weapon' if hits[-1] in GUN else 'fighting', f'{hits[-1]} {conf:.2f}'))
        return list({e[0]: e for e in ev}.values())
