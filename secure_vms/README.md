# Secure VMS - AI threat detection + cybersecurity analytics
CCTV -> AI Detection -> Threat Analysis -> Cyber Correlation -> Risk Score -> Alert -> Evidence -> Dashboard

## 1. Train the model (Kaggle notebook - easiest)
1. kaggle.com -> New Notebook -> Add Data -> search "DCSASS Dataset" (mateohervas) -> Session options: GPU on.
2. Cell 1: `!pip install -q ultralytics`
3. Cell 2: `!ls /kaggle/input/dcsass-dataset` (check folder layout). Upload `train/train_dcsass.py`, then run
   `!python train_dcsass.py /kaggle/input/dcsass-dataset`
4. Download `dcsass_cls.pt` from /kaggle/working and put it in `secure_vms/models/`.

Google Colab: Runtime > GPU, `!pip install ultralytics kagglehub`, then
`import kagglehub; p=kagglehub.dataset_download('mateohervas/dcsass-dataset')` and `!python train_dcsass.py {p}`.
Download the .pt file from the Colab file browser. (Model format is .pt; .h5/.keras are not needed.)

Optional weapon model: train yolov8n on a gun/knife detection dataset (`yolo detect train data=data.yaml model=yolov8n.pt epochs=30`)
and save as `models/weapon.pt`. Without it the app falls back to COCO knife/bat/scissors detection.

## 2. Run on your laptop
    python -m venv venv
    venv\Scripts\activate          (Mac/Linux: source venv/bin/activate)
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000 - login admin / admin123 (then create your own admin in the Admin tab).
First run downloads yolov8n.pt (internet needed once).

## 3. Use it
- Cameras tab: add source `0` (webcam), an `rtsp://...` URL, or upload a video. Optional restricted zone = polygon in 0-1 coordinates.
- Tamper test: cover the webcam 3s (covered) / freeze a source 8s (frozen) / unplug it (disconnected).
- Cyber test: fail login 5 times (failed_login); hit /api/stats logged out (unauthorized_access).
- Correlation: e.g. covered camera + failed logins within 60s -> score x1.5 -> High/Critical incident with screenshot + clip + SHA-256 in data/evidence.
- Email alerts (optional), set before starting: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_TO
  (Windows `set NAME=value`, Mac/Linux `export NAME=value`; Gmail needs an app password).

## Notes
- Roles: admin (all), officer (incidents, upload, verify, reports), viewer (read-only).
- Clips are mp4v; if a browser won't play them, download and open in VLC. Thresholds live in tamper.py / detector.py / risk.py.
- Use only on cameras/networks you own. For production: HTTPS, strong VMS_SECRET, change default credentials.
