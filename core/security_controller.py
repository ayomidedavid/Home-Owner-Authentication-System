import cv2
import numpy as np
import threading
import time
import datetime
import os
from pathlib import Path
from core.config import config, SNAPSHOTS_DIR, DATA_DIR
from core.database import log_intrusion_event, get_event_stats
from core.face_engine import face_engine
from core.camera import camera
from core.mailer import mailer

# Attempt to import winsound on Windows for audible alarm siren
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

class SecurityController:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.worker_thread = None

        # State: DISARMED, ARMED_AWAY, ARMED_HOME, ALARM_TRIGGERED
        self.state = config.get("alarm_state", "ARMED_AWAY")
        self.is_alarm_ringing = False
        self.last_alert_time = 0
        self.siren_thread = None
        self.stop_siren = False

        # Live detection cache
        self.last_detected_faces = []
        self.annotated_frame = None
        self.recent_intruder_count = 0
        self.latest_snapshot_rel_path = None

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
            camera.start()
            self.worker_thread = threading.Thread(target=self._security_loop, daemon=True)
            self.worker_thread.start()
            print("[SecurityController] Surveillance and face recognition loop started.")

    def stop(self):
        with self.lock:
            self.running = False
            self.stop_siren = True
        camera.stop()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2)

    def verify_pin(self, pin: str) -> bool:
        correct_pin = str(config.get("pin_code", "1234")).strip()
        return str(pin).strip() == correct_pin

    def arm(self, mode: str, pin: str = None) -> tuple[bool, str]:
        if pin is not None and not self.verify_pin(pin):
            return False, "Incorrect Security PIN code."

        if mode not in ["ARMED_AWAY", "ARMED_HOME"]:
            return False, f"Invalid arm mode: {mode}"

        with self.lock:
            self.state = mode
            self.is_alarm_ringing = False
            self.stop_siren = True
        config.set("alarm_state", mode)
        print(f"[SecurityController] System armed in mode: {mode}")
        return True, f"System armed ({mode})"

    def disarm(self, pin: str) -> tuple[bool, str]:
        if not self.verify_pin(pin):
            return False, "Incorrect Security PIN code."

        with self.lock:
            self.state = "DISARMED"
            self.is_alarm_ringing = False
            self.stop_siren = True
        config.set("alarm_state", "DISARMED")
        print("[SecurityController] System disarmed.")
        return True, "System disarmed."

    def trigger_panic(self) -> tuple[bool, str]:
        with self.lock:
            self.state = "ALARM_TRIGGERED"
        self._trigger_alarm_sequence("MANUAL_PANIC", notes="Manual emergency panic triggered by user")
        return True, "Panic alarm triggered!"

    def silence_alarm(self, pin: str = None) -> tuple[bool, str]:
        if pin and not self.verify_pin(pin):
            return False, "Incorrect PIN code."
        with self.lock:
            self.is_alarm_ringing = False
            self.stop_siren = True
            if self.state == "ALARM_TRIGGERED":
                self.state = "ARMED_AWAY"
        return True, "Alarm silenced."

    def _play_siren_loop(self):
        """Audio siren beeper running in background thread"""
        if not HAS_WINSOUND or not config.get("siren_enabled", True):
            return

        while not self.stop_siren and self.is_alarm_ringing:
            try:
                # Police / Alarm two-tone frequency oscillation
                winsound.Beep(2400, 200)
                if self.stop_siren or not self.is_alarm_ringing:
                    break
                winsound.Beep(1800, 200)
            except Exception:
                break

    def _trigger_alarm_sequence(self, event_type: str, raw_frame = None, notes: str = ""):
        """Executes full intrusion response: snapshot, email dispatch, local siren"""
        now = time.time()
        cooldown = int(config.get("alert_cooldown_seconds", 20))
        
        # Check cooldown to prevent multiple alerts for the same event
        if now - self.last_alert_time < cooldown and event_type != "MANUAL_PANIC":
            print(f"[SecurityController] Intruder still present, within cooldown ({int(now - self.last_alert_time)}s < {cooldown}s)")
            return

        self.last_alert_time = now
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_time = timestamp_str.replace(":", "-").replace(" ", "_")

        # Capture frame snapshot
        if raw_frame is None:
            raw_frame = camera.get_frame()

        filename = f"intruder_{safe_time}.jpg"
        save_path = SNAPSHOTS_DIR / filename
        cv2.imwrite(str(save_path), raw_frame)
        self.latest_snapshot_rel_path = f"data/snapshots/{filename}"

        # Set alarm ringing
        with self.lock:
            self.is_alarm_ringing = True
            self.stop_siren = False

        # Launch siren thread if enabled
        if config.get("siren_enabled", True) and HAS_WINSOUND:
            if self.siren_thread is None or not self.siren_thread.is_alive():
                self.siren_thread = threading.Thread(target=self._play_siren_loop, daemon=True)
                self.siren_thread.start()

        # Dispatch Email Alert with attached snapshot
        recipient = config.get("owner_email", "owner@example.com")
        email_sent = mailer.send_intruder_alert(
            snapshot_path=str(save_path),
            timestamp=timestamp_str,
            event_type=event_type,
            camera_name="Main Security Zone",
            notes=notes
        )

        # Log event to database
        log_intrusion_event(
            event_type=event_type,
            confidence=95.0,
            snapshot_path=self.latest_snapshot_rel_path,
            email_sent=email_sent,
            recipient=recipient,
            notes=notes
        )

        print(f"[SecurityController] [ALERT] ALARM TRIGGERED! Intrusion logged. Snapshot saved to {filename}. Email sent: {email_sent}")

    def _annotate_hud(self, frame, faces):
        """Render clean, modern security camera OSD overlay"""
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # 1. Sleek Top Status Bar (translucent dark gradient)
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, 0), (w, 38), (18, 18, 20), -1)
        cv2.addWeighted(overlay, 0.75, annotated, 0.25, 0, annotated)
        cv2.line(annotated, (0, 38), (w, 38), (45, 45, 50), 1)

        # Status Dot & Mode
        if self.is_alarm_ringing:
            dot_color = (0, 0, 240)
            mode_lbl = "ALARM ACTIVE"
        elif self.state == "ARMED_AWAY":
            dot_color = (0, 160, 255)
            mode_lbl = "ARMED AWAY"
        elif self.state == "ARMED_HOME":
            dot_color = (255, 180, 0)
            mode_lbl = "ARMED HOME"
        else:
            dot_color = (70, 200, 70)
            mode_lbl = "DISARMED"

        cv2.circle(annotated, (20, 19), 5, dot_color, -1)
        cv2.putText(annotated, f"FRONT DOOR  |  {mode_lbl}", (34, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 230, 230), 1, cv2.LINE_AA)

        # Clean Monospace Timestamp on Right
        now_str = datetime.datetime.now().strftime("%b %d, %Y  %H:%M:%S")
        (tw, _), _ = cv2.getTextSize(now_str, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
        cv2.putText(annotated, now_str, (w - tw - 16, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 185), 1, cv2.LINE_AA)

        # 2. Render Face Tracking Outlines & Tags
        for f in faces:
            x, y, fw, fh = f["bbox"]
            is_known = f["is_known"]

            if is_known:
                color = (70, 200, 90) # Clean green
                name_text = f"{f['name']}"
                role_text = f"{f.get('relationship', 'Resident')}"
                full_tag = f"{name_text} ({role_text})"
            else:
                color = (40, 40, 235) # Clean red
                full_tag = "Unrecognized Visitor"

            # Draw clean bounding box
            cv2.rectangle(annotated, (x, y), (x + fw, y + fh), color, 2, cv2.LINE_AA)

            # Elegant bottom or top tag pill
            tag_y = y - 8 if y > 35 else y + fh + 22
            (label_w, label_h), _ = cv2.getTextSize(full_tag, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            pill_pad = 6
            cv2.rectangle(annotated, 
                          (x, tag_y - label_h - pill_pad), 
                          (x + label_w + pill_pad * 2, tag_y + pill_pad - 2), 
                          (20, 20, 22), -1)
            cv2.rectangle(annotated, 
                          (x, tag_y - label_h - pill_pad), 
                          (x + label_w + pill_pad * 2, tag_y + pill_pad - 2), 
                          color, 1)
            cv2.putText(annotated, full_tag, (x + pill_pad, tag_y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

        # 3. Clean Security Alert banner if alarm is ringing
        if self.is_alarm_ringing:
            overlay_alert = annotated.copy()
            cv2.rectangle(overlay_alert, (0, h - 44), (w, h), (15, 15, 200), -1)
            cv2.addWeighted(overlay_alert, 0.85, annotated, 0.15, 0, annotated)
            alert_msg = "SECURITY ALERT: Unrecognized person detected - Notification sent to homeowner"
            (msg_w, _), _ = cv2.getTextSize(alert_msg, cv2.FONT_HERSHEY_SIMPLEX, 0.46, 1)
            cv2.putText(annotated, alert_msg, (max(10, (w - msg_w) // 2), h - 17), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 1, cv2.LINE_AA)

        return annotated

    def _security_loop(self):
        """Continuous surveillance worker: face recognition + alert trigger"""
        while self.running:
            frame = camera.get_frame()
            if frame is None or frame.size == 0:
                time.sleep(0.04)
                continue

            # Identify all faces in the frame
            faces = face_engine.identify_faces(frame)
            self.last_detected_faces = faces

            # Evaluate Security Rules
            if self.state in ["ARMED_AWAY", "ARMED_HOME"]:
                has_unknown = any(not f["is_known"] for f in faces)
                has_family = any(f["is_known"] for f in faces)

                if has_unknown:
                    # An unknown person is spotted while armed -> INTRUDER ALERT!
                    self._trigger_alarm_sequence(
                        event_type="UNKNOWN_INTRUDER",
                        raw_frame=frame,
                        notes="Unrecognized face detected by camera while armed"
                    )
                elif has_family:
                    # Known family member returned home
                    if self.is_alarm_ringing:
                        # Auto-silence alarm when recognized family member is visible
                        print("[SecurityController] Family member identified! Silencing alarm.")
                        with self.lock:
                            self.is_alarm_ringing = False
                            self.stop_siren = True

            # Generate annotated HUD frame for live MJPEG streaming
            annotated = self._annotate_hud(frame, faces)
            with self.lock:
                self.annotated_frame = annotated

            time.sleep(0.03)

    def get_annotated_frame(self):
        with self.lock:
            if self.annotated_frame is not None:
                return self.annotated_frame.copy()
        return camera.get_frame()

    def get_status(self):
        stats = get_event_stats()
        return {
            "state": self.state,
            "is_alarm_ringing": self.is_alarm_ringing,
            "detected_faces_count": len(self.last_detected_faces),
            "detected_faces": self.last_detected_faces,
            "registered_family": stats["registered_family"],
            "total_intrusions": stats["total_intrusions"],
            "emails_dispatched": stats["emails_dispatched"],
            "owner_email": config.get("owner_email", "owner@example.com"),
            "smtp_enabled": config.get("smtp_enabled", False),
            "camera_source": config.get("camera_source", "0"),
            "is_simulator": camera.is_simulator
        }

# Global SecurityController instance
security_controller = SecurityController()
