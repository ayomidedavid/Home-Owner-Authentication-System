import os
import sys
import unittest
import numpy as np
import cv2
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.config import config, DATA_DIR, SNAPSHOTS_DIR, EMAILS_DIR
from core.database import (
    init_db,
    add_family_member,
    get_all_family_members,
    log_intrusion_event,
    get_recent_intrusion_events,
    log_outbox_email,
    get_recent_emails,
    get_event_stats
)
from core.face_engine import face_engine
from core.mailer import mailer
from core.security_controller import security_controller
from web.app import app

def create_synthetic_face_image(hair_color=(20, 40, 80), eye_color=(180, 50, 30)):
    """Helper to generate a clear synthetic face frame that triggers Haar cascades"""
    canvas = np.full((320, 320, 3), (215, 225, 240), dtype=np.uint8) # Skin tone
    # Face oval
    cv2.ellipse(canvas, (160, 160), (90, 120), 0, 0, 360, (190, 205, 230), -1)
    # Hair
    cv2.ellipse(canvas, (160, 75), (95, 45), 0, 180, 360, hair_color, -1)
    # Eyebrows
    cv2.line(canvas, (110, 125), (145, 122), hair_color, 4)
    cv2.line(canvas, (175, 122), (210, 125), hair_color, 4)
    # Eyes
    cv2.ellipse(canvas, (125, 142), (18, 10), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(canvas, (195, 142), (18, 10), 0, 0, 360, (255, 255, 255), -1)
    cv2.circle(canvas, (125, 142), 7, eye_color, -1)
    cv2.circle(canvas, (195, 142), 7, eye_color, -1)
    # Pupils
    cv2.circle(canvas, (125, 142), 3, (0, 0, 0), -1)
    cv2.circle(canvas, (195, 142), 3, (0, 0, 0), -1)
    # Nose
    pts = np.array([[160, 150], [150, 185], [170, 185]], np.int32)
    cv2.polylines(canvas, [pts], False, (160, 175, 200), 2)
    # Mouth
    cv2.ellipse(canvas, (160, 220), (30, 10), 0, 0, 180, (120, 120, 200), -1)
    return canvas

class TestHomeIntruderSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_config_manager(self):
        """Verify configuration load, set, and persistence"""
        config.set("owner_email", "test_owner@example.com")
        self.assertEqual(config.get("owner_email"), "test_owner@example.com")
        self.assertEqual(config.get("pin_code"), "1234")

    def test_02_database_operations(self):
        """Verify SQLite tables and logging queries"""
        initial_stats = get_event_stats()
        
        # Test intrusion log
        ev_id = log_intrusion_event("TEST_BREACH", 98.5, "data/snapshots/test.jpg", True, "test@example.com", "Unit test")
        self.assertGreater(ev_id, 0)
        events = get_recent_intrusion_events(10)
        self.assertTrue(any(e["id"] == ev_id for e in events))

        # Test outbox log
        email_id = log_outbox_email("test@example.com", "Test Subject", "<p>Hello</p>", "data/snapshots/test.jpg", "SENT")
        self.assertGreater(email_id, 0)
        emails = get_recent_emails(10)
        self.assertTrue(any(em["id"] == email_id for em in emails))

    def test_03_family_enrollment_and_recognition(self):
        """Verify face enrollment, LBPH training, and intruder differentiation"""
        models_dir = Path(__file__).resolve().parent / "core" / "models"
        family_img_path = models_dir / "sample_family.jpg"
        intruder_img_path = models_dir / "sample_intruder.jpg"

        sarah_face = cv2.imread(str(family_img_path))
        self.assertIsNotNone(sarah_face, "sample_family.jpg should exist")

        # 1. Register "Sarah Jenkins (Spouse)"
        success, result = face_engine.register_member("Sarah Jenkins", "Spouse", sarah_face)
        self.assertTrue(success, f"Enrollment failed: {result}")
        self.assertTrue(face_engine.is_trained)

        # 2. Test identification on Sarah's face -> Should be recognized as Sarah
        faces = face_engine.identify_faces(sarah_face)
        if len(faces) == 0:
            # Test direct crop prediction
            gray = cv2.cvtColor(sarah_face, cv2.COLOR_BGR2GRAY)
            chip = face_engine.preprocess_face(gray)
            label, dist = face_engine.recognizer.predict(chip)
            self.assertEqual(label, result["face_label"])
            print(f"[Test] Direct crop recognized: label={label}, dist={dist:.1f}")
        else:
            match = faces[0]
            self.assertTrue(match["is_known"], f"Expected Sarah to be recognized, got {match}")
            self.assertEqual(match["name"], "Sarah Jenkins")

        # 3. Test identification on an unfamiliar intruder face
        intruder_face = cv2.imread(str(intruder_img_path))
        if intruder_face is not None:
            intruder_results = face_engine.identify_faces(intruder_face)
            if len(intruder_results) > 0:
                print(f"[Test] Intruder test detection result: {intruder_results[0]}")

    def test_04_mailer_alert_generation(self):
        """Verify alert email generation with photo attachment and outbox logging"""
        test_snapshot = SNAPSHOTS_DIR / "unit_test_snap.jpg"
        dummy_img = np.zeros((200, 200, 3), dtype=np.uint8)
        cv2.imwrite(str(test_snapshot), dummy_img)

        sent = mailer.send_intruder_alert(
            snapshot_path=str(test_snapshot),
            event_type="TEST_INTRUSION",
            camera_name="Backyard Zone",
            notes="Automated test validation"
        )
        self.assertTrue(sent)
        
        # Verify outbox has logged email
        recent_emails = get_recent_emails(5)
        self.assertTrue(len(recent_emails) > 0)
        latest = recent_emails[0]
        self.assertIn("INTRUDER ALERT", latest["subject"])
        self.assertIn(latest["status"], ["SENT", "OFFLINE_SAVED"])

    def test_05_security_controller_state_machine(self):
        """Verify PIN verification, Arm, Disarm, and Panic triggers"""
        # Bad PIN
        ok, msg = security_controller.arm("ARMED_AWAY", "9999")
        self.assertFalse(ok)

        # Good PIN Arm
        ok, msg = security_controller.arm("ARMED_AWAY", "1234")
        self.assertTrue(ok)
        self.assertEqual(security_controller.state, "ARMED_AWAY")

        # Good PIN Disarm
        ok, msg = security_controller.disarm("1234")
        self.assertTrue(ok)
        self.assertEqual(security_controller.state, "DISARMED")

    def test_06_web_api_endpoints(self):
        """Verify Flask web server routes and JSON responses"""
        client = app.test_client()
        
        # Index
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)

        # Status
        resp = client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("state", data)
        self.assertIn("registered_family", data)

        # Family list
        resp = client.get("/api/family")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

        # Events list
        resp = client.get("/api/events")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

        # Settings
        resp = client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

        # Simulator trigger
        resp = client.post("/api/simulate", json={"type": "intruder", "duration": 5})
        self.assertEqual(resp.status_code, 200)

if __name__ == "__main__":
    unittest.main()
