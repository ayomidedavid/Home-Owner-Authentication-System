import cv2
import numpy as np
import threading
import time
import datetime
from pathlib import Path
from core.config import config, DATA_DIR

class CameraStream:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        
        self.cap = None
        self.is_simulator = False
        self.current_frame = None

        # Simulator state variables
        self.sim_tick = 0
        self.sim_intruder_active = False
        self.sim_intruder_timer = 0
        self.sim_family_active = False
        self.sim_family_timer = 0
        self.sim_family_name = "Family Member"
        self.sim_family_photo = None

        # Synthetic face avatars for simulation
        self._init_synthetic_faces()

    def _init_synthetic_faces(self):
        """Pre-render faces that Haar cascade reliably detects for simulation"""
        models_dir = Path(__file__).resolve().parent / "models"
        f_intruder = models_dir / "sample_intruder.jpg"
        f_family = models_dir / "sample_family.jpg"

        if f_intruder.exists():
            self.synthetic_intruder_face = cv2.resize(cv2.imread(str(f_intruder)), (120, 140))
        else:
            self.synthetic_intruder_face = self._generate_face_canvas(eye_color=(20, 20, 180), hair_color=(30, 30, 30))

        if f_family.exists():
            self.synthetic_family_face = cv2.resize(cv2.imread(str(f_family)), (120, 140))
        else:
            self.synthetic_family_face = self._generate_face_canvas(eye_color=(150, 100, 30), hair_color=(40, 70, 130))

    def _generate_face_canvas(self, eye_color, hair_color):
        """Draw a synthetic human face that triggers OpenCV face detection"""
        canvas = np.full((160, 140, 3), (210, 220, 235), dtype=np.uint8) # Skin tone
        # Head oval
        cv2.ellipse(canvas, (70, 80), (55, 70), 0, 0, 360, (190, 205, 230), -1)
        # Hair
        cv2.ellipse(canvas, (70, 35), (58, 30), 0, 180, 360, hair_color, -1)
        # Eyebrows
        cv2.line(canvas, (40, 58), (62, 56), hair_color, 4)
        cv2.line(canvas, (78, 56), (100, 58), hair_color, 4)
        # Eyes
        cv2.ellipse(canvas, (50, 68), (12, 7), 0, 0, 360, (255, 255, 255), -1)
        cv2.ellipse(canvas, (90, 68), (12, 7), 0, 0, 360, (255, 255, 255), -1)
        cv2.circle(canvas, (50, 68), 5, eye_color, -1)
        cv2.circle(canvas, (90, 68), 5, eye_color, -1)
        cv2.circle(canvas, (51, 67), 2, (255, 255, 255), -1)
        cv2.circle(canvas, (91, 67), 2, (255, 255, 255), -1)
        # Nose
        pts = np.array([[70, 75], [64, 95], [76, 95]], np.int32)
        cv2.polylines(canvas, [pts], False, (160, 175, 200), 2)
        # Mouth / Lips
        cv2.ellipse(canvas, (70, 115), (20, 6), 0, 0, 180, (120, 120, 200), -1)
        return canvas

    def _init_hardware(self):
        src = config.get("camera_source", "0")
        if src == "SIMULATOR":
            self.is_simulator = True
            return

        try:
            idx = int(src)
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                print(f"[Camera] Connected to physical webcam index {idx}")
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap = cap
                self.is_simulator = False
            else:
                print(f"[Camera] Physical camera index {idx} unavailable. Using Virtual Simulator.")
                self.is_simulator = True
                self.cap = None
        except Exception as e:
            print(f"[Camera] Hardware camera error: {e}. Using Virtual Simulator.")
            self.is_simulator = True

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
            # Pre-render initial frame so video stream is never blank
            self.current_frame = self._render_simulator_frame()
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()

    def stop(self):
        with self.lock:
            self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def trigger_simulated_intruder(self, duration_seconds: int = 12):
        """Command to inject an unknown intruder into the simulator stream"""
        self.sim_intruder_active = True
        self.sim_intruder_timer = time.time() + duration_seconds
        self.sim_family_active = False

    def trigger_simulated_family(self, member_name: str = "Family Member", duration_seconds: int = 12):
        """Command to inject a known family member into the simulator stream"""
        self.sim_family_active = True
        self.sim_family_name = member_name
        self.sim_family_timer = time.time() + duration_seconds
        self.sim_intruder_active = False

        # If a registered family photo exists, load it
        from core.database import get_all_family_members
        members = get_all_family_members(only_active=True)
        if members:
            for m in members:
                if m["name"].lower() == member_name.lower():
                    p = DATA_DIR.parent / m["photo_path"]
                    if p.exists():
                        self.sim_family_photo = cv2.imread(str(p))
                        break

    def clear_simulation(self):
        self.sim_intruder_active = False
        self.sim_family_active = False

    def _render_simulator_frame(self):
        """Generate high-tech home security surveillance scene"""
        w, h = 640, 480
        # Dark atmospheric interior living room scene
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Room walls / floor gradient
        for y in range(h):
            ratio = y / h
            b = int(25 + ratio * 20)
            g = int(30 + ratio * 22)
            r = int(35 + ratio * 25)
            frame[y, :] = (b, g, r)

        # Floor line
        cv2.line(frame, (0, 340), (w, 340), (45, 55, 65), 2)
        # Living room door frame on right
        cv2.rectangle(frame, (450, 120), (580, 340), (50, 60, 75), 3)
        cv2.rectangle(frame, (460, 130), (570, 340), (35, 42, 55), -1)
        # Window on left
        cv2.rectangle(frame, (60, 130), (220, 250), (60, 70, 85), 2)
        cv2.rectangle(frame, (65, 135), (215, 245), (20, 30, 45), -1)
        cv2.line(frame, (140, 135), (140, 245), (60, 70, 85), 2)
        cv2.line(frame, (65, 190), (215, 190), (60, 70, 85), 2)

        # Subtle camera scanline noise
        self.sim_tick += 1
        noise = np.random.randint(0, 10, (h, w, 3), dtype=np.uint8)
        frame = cv2.add(frame, noise)

        # Check simulation timers
        now = time.time()
        if self.sim_intruder_active and now > self.sim_intruder_timer:
            self.sim_intruder_active = False
        if self.sim_family_active and now > self.sim_family_timer:
            self.sim_family_active = False

        # If Intruder is active: render intruder walking into the room
        if self.sim_intruder_active:
            # Person movement across room
            progress = (now % 6.0) / 6.0
            px = int(480 - (progress * 240)) # Moves from doorway inward
            py = 180
            
            # Torso / hoodie (dark clothing)
            cv2.rectangle(frame, (px - 40, py + 80), (px + 40, py + 220), (20, 20, 25), -1)
            # Face
            fh, fw = self.synthetic_intruder_face.shape[:2]
            fx = px - (fw // 2)
            fy = py
            if 0 <= fy and fy + fh < h and 0 <= fx and fx + fw < w:
                frame[fy:fy+fh, fx:fx+fw] = self.synthetic_intruder_face

        # If Family member is active: render family member returning home
        elif self.sim_family_active:
            progress = (now % 6.0) / 6.0
            px = int(480 - (progress * 220))
            py = 180

            # Torso (casual colorful clothing)
            cv2.rectangle(frame, (px - 40, py + 80), (px + 40, py + 220), (120, 70, 30), -1)
            
            # If we have their real photo, use it!
            if self.sim_family_photo is not None:
                fh, fw = 140, 120
                resized_face = cv2.resize(self.sim_family_photo, (fw, fh))
                fx = px - (fw // 2)
                fy = py
                if 0 <= fy and fy + fh < h and 0 <= fx and fx + fw < w:
                    frame[fy:fy+fh, fx:fx+fw] = resized_face
            else:
                fh, fw = self.synthetic_family_face.shape[:2]
                fx = px - (fw // 2)
                fy = py
                if 0 <= fy and fy + fh < h and 0 <= fx and fx + fw < w:
                    frame[fy:fy+fh, fx:fx+fw] = self.synthetic_family_face

        return frame

    def _worker(self):
        self._init_hardware()
        while self.running:
            if not self.is_simulator and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.lock:
                        self.current_frame = frame
                else:
                    self.is_simulator = True
            else:
                # Render simulator frame at ~25 FPS
                frame = self._render_simulator_frame()
                with self.lock:
                    self.current_frame = frame
                time.sleep(0.04)

    def get_frame(self):
        """Returns the latest BGR frame"""
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
        # Fallback blank
        return np.zeros((480, 640, 3), dtype=np.uint8)

# Global camera instance
camera = CameraStream()
