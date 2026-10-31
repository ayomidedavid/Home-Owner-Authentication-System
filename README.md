# 🛡️ Sentinel AI — Home Intruder & Facial Recognition System

An intelligent, local home security surveillance and intruder detection system built in Python, OpenCV, and Flask. Sentinel AI enables homeowners to register family members using facial recognition, monitors the home in real time, distinguishes between authorized occupants and unknown intruders, sounds sirens, and instantly captures photo evidence and emails alerts to the homeowner.

---

## 🌟 Key Features

1. **Facial Recognition & Family Enrollment**:
   - Register family members with a single click via live camera snap or photo upload.
   - Powered by local OpenCV LBPH biometric recognition with real-time augmentation (no third-party cloud biometrics).
   - Real-time video HUD overlays **Green badges** (`FAMILY: [Name]`) for recognized residents.

2. **Intruder Detection & Differentiation**:
   - Analyzes all faces in the camera frame against the enrolled family database.
   - When an unlisted individual is detected while armed, marks them in **Flashing Red** (`🚨 UNKNOWN INTRUDER`) and triggers security protocols.

3. **Instant Photo Evidence & Owner Email Dispatch**:
   - Automatically snaps high-resolution timestamped evidence (`data/snapshots/intruder_*.jpg`).
   - Emails a high-priority security alert with the intruder's photo attached directly to the homeowner's inbox.
   - Includes an **Offline Outbox Viewer** in the web dashboard so you can preview sent alerts even before setting up SMTP.

4. **PyMySQL Database Backend**:
   - Fully integrated with **PyMySQL** to connect directly to your MySQL/MariaDB database (`home_intruder_system`).
   - Stores family profiles, biometric face references, intrusion logs, and email history.
   - Configure MySQL Host, Port, User, and Password directly in the web dashboard with a live **Test Connection** button.
   - Transparent fallback to SQLite if MySQL is ever offline.

4. **Security State Management & Keypad**:
   - Armed Modes: `ARMED_AWAY`, `ARMED_HOME`, `DISARMED`, and emergency `PANIC`.
   - Protected by numeric Security PIN (default: `1234`).
   - Dual-layer Siren: Hardware audible alarm (Windows `winsound`) + Browser Web Audio synthesizer.

5. **Built-in Interactive Simulator**:
   - Test bench with 1-click buttons:
     - 🚨 *Simulate Intruder*: Injects an intruder into the frame to verify siren, snapshot, and email dispatch.
     - 👤 *Simulate Family*: Injects an enrolled family member to verify safe recognition and alarm suppression.

---

## 🚀 Quick Start

### 1. Requirements
Ensure Python 3.10+ is installed. Dependencies:
```bash
pip install -r requirements.txt
```

### 2. Launch the System
Run the master launcher:
```bash
python run.py
```
This will:
- Initialize the SQLite database and folders.
- Start the facial recognition and surveillance engine.
- Launch the Web Command Center at `http://127.0.0.1:5000` and open it in your browser.

---

## 💻 Web Command Center Guide

1. **Dashboard URL**: `http://127.0.0.1:5000`
2. **Default Master PIN**: `1234` (configurable under *Email & Config* tab).
3. **Register Family Members**:
   - Go to the **Family Members** tab.
   - Click **Register Member**.
   - Enter name & relationship, then click **Snap from Camera** or **Upload Photo**.
   - Click **Save & Enroll Face**. The model retrains automatically in milliseconds.
4. **Configure Owner Email**:
   - Go to the **Email & Config** tab.
   - Enter your email address in **Owner Alert Email Address**.
   - (Optional) Enable SMTP and enter your SMTP details (e.g. `smtp.gmail.com`, port `587`, and an App Password).
   - Click **Send Test Email** to verify.
5. **Arming the System**:
   - Click **Arm Away** or **Arm Home** on the top navigation bar.
   - To disarm, click **Disarm** and enter your PIN `1234` on the numeric keypad.
6. **Test the Intruder Alert**:
   - In the **Interactive Security Simulator** panel under the video monitor, click **Simulate Intruder**.
   - Watch the HUD flash red, the siren activate, a snapshot save to the **Intruder Alerts** tab, and an alert dispatch to your email!

---

## 📂 Project Structure

```
Home Intruder System/
├── core/
│   ├── config.py             # Configuration manager (data/config.json)
│   ├── database.py           # SQLite database layer (data/security.db)
│   ├── face_engine.py        # Facial recognition and LBPH enrollment engine
│   ├── camera.py             # Video stream and interactive virtual simulator
│   ├── security_controller.py# Security state machine, HUD overlays, alarm siren
│   ├── mailer.py             # HTML email dispatcher with image attachment
│   └── models/               # Pretrained Haar cascade models & reference samples
├── web/
│   ├── app.py                # Flask server, MJPEG streaming, REST APIs
│   └── templates/
│       └── index.html        # Responsive cyber-defense Command Center UI
├── data/
│   ├── family/               # Enrolled family face crops
│   ├── snapshots/            # Captured intruder incident photos
│   └── emails/               # Local outbox email copies
├── run.py                    # Master launcher
├── test_system.py            # Automated test suite
└── requirements.txt          # Python dependencies
```

---

## 🛡️ Security & Privacy Notice
All facial biometric data and security snapshots are stored strictly locally on your machine in the `data/` directory. No facial features, video streams, or photos are transmitted to external servers or cloud providers.
