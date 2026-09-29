import os, time, threading, collections, cv2
import db, evidence, risk, detector, tamper
class Worker(threading.Thread):
    def __init__(s, cam):
        super().__init__(daemon=True)
        s.id, s.src, s.fps = cam['id'], cam['source'], 10
        s.buf = collections.deque(maxlen=80); s.jpg = None; s.run_flag = True; s.status = 'connecting'
        s.tam = tamper.Tamper(); s.det = detector.Detector(cam.get('zone'))
    def run(s):
        evidence.REG[s.id] = s
        src = int(s.src) if str(s.src).isdigit() else s.src
        is_file = os.path.isfile(str(src)); cap = None; n = fails = 0; seen = 0
        while s.run_flag:
            t0 = time.time()
            if cap is None: cap = cv2.VideoCapture(src)
            ok, f = cap.read()
            if not ok:
                if is_file and fails < 3: cap.set(cv2.CAP_PROP_POS_FRAMES, 0); fails += 1; continue  # loop uploaded video
                fails += 1
                if fails > 30:
                    s.status = 'offline'; risk.add_event(s.id, 'tamper_disconnected', 'camera not delivering frames')
                    cap.release(); cap = None; fails = 0; time.sleep(5)
                time.sleep(.1); continue
            fails = 0; s.status = 'online'
            f = cv2.resize(f, (640, int(f.shape[0] * 640 / f.shape[1]))); n += 1
            t = s.tam.check(f)
            if t: risk.add_event(s.id, 'tamper_' + t[0], t[1])
            if n % 3 == 0:
                for etype, detail in s.det.run(f): risk.add_event(s.id, etype, detail)
            s.buf.append(f); s.jpg = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()
            if t0 - seen > 10: seen = t0; db.q("UPDATE cameras SET last_seen=? WHERE id=?", (t0, s.id), commit=True)
            if is_file: time.sleep(max(0, 1 / s.fps - (time.time() - t0)))
        if cap: cap.release()
