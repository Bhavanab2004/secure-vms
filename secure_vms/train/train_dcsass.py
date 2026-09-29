"""
Train a DCSASS behaviour classifier (Fighting / Assault / Abuse / Shooting / ...) with YOLOv8-cls.
Run in a Kaggle Notebook (attach dataset 'mateohervas/dcsass-dataset', GPU on) or Google Colab (GPU runtime).
Usage:  python train_dcsass.py [DATASET_ROOT]
Output: dcsass_cls.pt  -> copy to secure_vms/models/
"""
import os, sys, glob, random, shutil, cv2
ROOT = sys.argv[1] if len(sys.argv) > 1 else '/kaggle/input/dcsass-dataset'
OUT = '/kaggle/working/frames' if os.path.exists('/kaggle/working') else 'frames'
CLASSES = ['Abuse', 'Arrest', 'Arson', 'Assault', 'Burglary', 'Explosion', 'Fighting', 'RoadAccidents',
           'Robbery', 'Shooting', 'Shoplifting', 'Stealing', 'Vandalism', 'Normal']
STEP, MAX_PER_CLIP = 12, 6          # 1 frame every 12 frames, max 6 per clip
random.seed(0); shutil.rmtree(OUT, ignore_errors=True)
vids = [p for e in ('mp4', 'avi') for p in glob.glob(f'{ROOT}/**/*.{e}', recursive=True)]
print('videos found:', len(vids))
counts = {}
for v in vids:
    parts = os.path.relpath(v, ROOT).split(os.sep)
    cls = next((c for c in CLASSES if any(c.lower() in p.lower() for p in parts[:-1])), None)   # class from folder name
    if not cls: continue
    split = 'val' if random.random() < .2 else 'train'
    d = f'{OUT}/{split}/{cls}'; os.makedirs(d, exist_ok=True)
    cap = cv2.VideoCapture(v); i = k = 0
    while k < MAX_PER_CLIP:
        ok, fr = cap.read()
        if not ok: break
        if i % STEP == 0:
            cv2.imwrite(f'{d}/{os.path.basename(v)[:-4]}_{i}.jpg', cv2.resize(fr, (224, 224))); k += 1
        i += 1
    counts[cls] = counts.get(cls, 0) + k
print('frames per class:', counts)
if len(counts) < 2: sys.exit('Could not map folders to classes - run `!ls` on the dataset and edit CLASSES / the class rule above.')
from ultralytics import YOLO
m = YOLO('yolov8n-cls.pt')
m.train(data=OUT, epochs=15, imgsz=224, batch=64, project='runs', name='dcsass')
shutil.copy(m.trainer.best, 'dcsass_cls.pt'); print('Saved dcsass_cls.pt')
