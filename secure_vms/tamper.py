import time, cv2
class Tamper:
    """Detects covered lens (dark/uniform) and frozen feed (no pixel change). Thresholds are tunable."""
    def __init__(s): s.prev = None; s.frz = None; s.cov = None
    def check(s, f):
        g = cv2.cvtColor(cv2.resize(f, (160, 90)), cv2.COLOR_BGR2GRAY); now = time.time(); out = None
        bad = g.mean() < 15 or g.std() < 6
        s.cov = (s.cov or now) if bad else None
        if s.cov and now - s.cov > 3: out = ('covered', f'mean={g.mean():.0f} std={g.std():.1f}')
        same = s.prev is not None and cv2.absdiff(g, s.prev).mean() < .15
        s.frz = (s.frz or now) if same else None
        s.prev = g
        if s.frz and now - s.frz > 8: out = ('frozen', 'no pixel change for 8s')
        return out
