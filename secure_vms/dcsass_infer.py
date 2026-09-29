import cv2, numpy as np, torch, torch.nn as nn

CLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
CLIP_STD = (0.26862954, 0.26130258, 0.27577711)

def _pick(got, idx):
    keys = np.array(sorted(got))
    return [got[int(keys[np.abs(keys - j).argmin()])] for j in idx]

def sample_frames(path, T=16, size=224):
    """T RGB frames (T,size,size,3) uint8 spread evenly over the whole clip, or None if unreadable."""
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    got, idx = {}, None
    if n > 0:
        idx = np.linspace(0, n - 1, T).round().astype(int)
        need = set(idx.tolist())
        last, i = max(need), 0
        while i <= last and cap.grab():
            if i in need:
                ok, fr = cap.retrieve()
                if ok:
                    got[i] = cv2.resize(fr, (size, size), interpolation=cv2.INTER_AREA)[:, :, ::-1]
            i += 1
    cap.release()
    if not got:  # frame count unknown: read everything
        cap = cv2.VideoCapture(path)
        allf = []
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            allf.append(cv2.resize(fr, (size, size), interpolation=cv2.INTER_AREA)[:, :, ::-1])
        cap.release()
        if not allf:
            return None
        got = dict(enumerate(allf))
        idx = np.linspace(0, len(allf) - 1, T).round().astype(int)
    return np.ascontiguousarray(np.stack(_pick(got, idx)))

class ClipFeat:
    """Frozen CLIP vision encoder -> one vector per frame."""
    def __init__(self, clip_id, device):
        from transformers import CLIPVisionModel
        self.device = device
        self.dtype = torch.float16 if device == 'cuda' else torch.float32
        self.m = CLIPVisionModel.from_pretrained(clip_id).to(self.dtype).to(device).eval()
        self.dim = self.m.config.hidden_size
        self.mean = torch.tensor(CLIP_MEAN, device=device).view(1, 3, 1, 1)
        self.std = torch.tensor(CLIP_STD, device=device).view(1, 3, 1, 1)

    @torch.no_grad()
    def __call__(self, x):  # x: (N,H,W,3) uint8 RGB
        x = x.to(self.device).permute(0, 3, 1, 2).float().div(255)
        x = ((x - self.mean) / self.std).to(self.dtype)
        return self.m(pixel_values=x).pooler_output.float()

class TemporalClassifier(nn.Module):
    def __init__(self, in_dim, n_classes, T=16, d=384, layers=2, heads=6, drop=0.2):
        super().__init__()
        self.proj = nn.Sequential(nn.LayerNorm(in_dim), nn.Dropout(drop), nn.Linear(in_dim, d))
        self.cls = nn.Parameter(torch.zeros(1, 1, d))
        self.pos = nn.Parameter(torch.zeros(1, T + 1, d))
        nn.init.trunc_normal_(self.cls, std=0.02)
        nn.init.trunc_normal_(self.pos, std=0.02)
        layer = nn.TransformerEncoderLayer(d, heads, d * 3, drop, activation='gelu',
                                           batch_first=True, norm_first=True)
        self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.head = nn.Sequential(nn.LayerNorm(d), nn.Dropout(drop), nn.Linear(d, n_classes))

    def forward(self, x):  # (B,T,in_dim)
        x = self.proj(x)
        x = torch.cat([self.cls.expand(x.size(0), -1, -1), x], 1) + self.pos[:, :x.size(1) + 1]
        return self.head(self.enc(x)[:, 0])

def pick_device():
    if torch.cuda.is_available():
        return 'cuda'
    mps = getattr(torch.backends, 'mps', None)
    if mps is not None and mps.is_available():
        return 'mps'
    return 'cpu'

class DcsassPredictor:
    def __init__(self, ckpt_path, device=None):
        self.device = device or pick_device()
        ck = torch.load(ckpt_path, map_location='cpu')
        self.classes, self.T, self.img = ck['classes'], ck['T'], ck['img']
        self.models = []
        for sd in ck['state_dicts']:
            m = TemporalClassifier(ck['in_dim'], len(self.classes), self.T, **ck['arch'])
            m.load_state_dict(sd)
            self.models.append(m.to(self.device).eval())
        self.fe = ClipFeat(ck['clip_id'], self.device)

    @torch.no_grad()
    def predict_frames(self, frames):
        """frames: T RGB uint8 frames (any size). For a live stream pass the last ~T frames spread over ~3 s."""
        frames = np.stack([cv2.resize(f, (self.img, self.img), interpolation=cv2.INTER_AREA) for f in frames])
        x = torch.from_numpy(frames)
        f0, f1 = self.fe(x), self.fe(x.flip(2))
        p = 0
        for m in self.models:
            for f in (f0, f1):
                p = p + torch.softmax(m(f[None]), -1)[0]
        p = (p / (2 * len(self.models))).cpu().numpy()
        out = {'label': self.classes[int(p.argmax())], 'confidence': float(p.max()),
               'probs': {c: float(v) for c, v in zip(self.classes, p)}}
        if 'Normal' in self.classes:
            out['anomaly_score'] = float(1 - p[self.classes.index('Normal')])
        return out

    def predict(self, video_path):
        fr = sample_frames(video_path, self.T, self.img)
        if fr is None:
            raise ValueError(f'could not read {video_path}')
        return self.predict_frames(fr)

