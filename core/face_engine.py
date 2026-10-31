import cv2
import numpy as np
import os
import re
from pathlib import Path
from core.config import DATA_DIR, FAMILY_DIR, config
from core.database import (
    add_family_member,
    get_all_family_members,
    get_next_face_label,
    delete_family_member,
    get_connection
)

MODEL_PATH = DATA_DIR / "face_model.xml"

class FaceEngine:
    def __init__(self):
        # Load Haar Cascade face detectors from local models directory
        models_dir = Path(__file__).resolve().parent / "models"
        cascade_path = models_dir / "haarcascade_frontalface_default.xml"
        if not cascade_path.exists():
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        
        self.face_cascade = cv2.CascadeClassifier(str(cascade_path))
        
        # Profile face cascade for angle tolerance
        profile_path = models_dir / "haarcascade_profileface.xml"
        if profile_path.exists():
            self.profile_cascade = cv2.CascadeClassifier(str(profile_path))
        else:
            self.profile_cascade = None

        # LBPH Recognizer
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=1,
            neighbors=8,
            grid_x=8,
            grid_y=8,
            threshold=150.0  # Max distance before auto-reject
        )
        self.is_trained = False
        self.label_to_member = {}  # {label: member_dict}

        # Initialize by loading existing model and family database
        self.reload_model()

    def preprocess_face(self, face_gray):
        """Standardize face chip: 200x200, histogram equalization for illumination invariance"""
        resized = cv2.resize(face_gray, (200, 200))
        equalized = cv2.equalizeHist(resized)
        return equalized

    def detect_faces(self, frame_bgr):
        """Detect all face bounding boxes in BGR frame"""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(35, 35),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        # If no frontal faces found, attempt profile cascade
        if len(faces) == 0 and self.profile_cascade is not None:
            faces = self.profile_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(35, 35)
            )
        return faces, gray

    def augment_face_samples(self, face_chip_gray):
        """Generate subtle augmentations (flips, contrast, small rotations) to strengthen training"""
        samples = [face_chip_gray]
        
        # Horizontal flip
        flipped = cv2.flip(face_chip_gray, 1)
        samples.append(flipped)

        # Contrast variations
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        samples.append(clahe.apply(face_chip_gray))
        samples.append(clahe.apply(flipped))

        # Small rotations (-5 and +5 degrees)
        h, w = face_chip_gray.shape
        center = (w // 2, h // 2)
        for angle in [-5, 5]:
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(face_chip_gray, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
            samples.append(rotated)

        return samples

    def train_from_dataset(self):
        """Train or retrain the LBPH recognizer from all registered active family members"""
        members = get_all_family_members(only_active=True)
        if not members:
            self.is_trained = False
            self.label_to_member = {}
            if MODEL_PATH.exists():
                try:
                    os.remove(MODEL_PATH)
                except Exception:
                    pass
            print("[FaceEngine] No active family members registered. Model reset.")
            return False

        faces_training = []
        labels_training = []
        self.label_to_member = {}

        for m in members:
            label = m["face_label"]
            self.label_to_member[label] = m

            photo_file = Path(m["photo_path"])
            if not photo_file.is_absolute():
                photo_file = DATA_DIR.parent / photo_file

            if not photo_file.exists():
                print(f"[FaceEngine] Warning: Photo not found at {photo_file}")
                continue

            # Load image
            img = cv2.imread(str(photo_file))
            if img is None:
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Find face in photo
            detected, _ = self.detect_faces(img)
            if len(detected) > 0:
                # Largest face
                (x, y, w, h) = max(detected, key=lambda b: b[2] * b[3])
                chip = self.preprocess_face(gray[y:y+h, x:x+w])
            else:
                # Fallback to entire image resized
                chip = self.preprocess_face(gray)

            # Generate augmented variations
            augmented = self.augment_face_samples(chip)
            for s in augmented:
                faces_training.append(s)
                labels_training.append(label)

        if len(faces_training) == 0:
            self.is_trained = False
            return False

        # Train LBPH
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8, threshold=150.0)
        self.recognizer.train(faces_training, np.array(labels_training))
        self.recognizer.save(str(MODEL_PATH))
        self.is_trained = True
        print(f"[FaceEngine] Successfully trained on {len(faces_training)} samples for {len(members)} family members.")
        return True

    def reload_model(self):
        """Reload members and model from disk"""
        members = get_all_family_members(only_active=True)
        self.label_to_member = {m["face_label"]: m for m in members}
        
        if len(members) == 0:
            self.is_trained = False
            return

        if MODEL_PATH.exists():
            try:
                self.recognizer.read(str(MODEL_PATH))
                self.is_trained = True
                print(f"[FaceEngine] Loaded face model with {len(members)} active members.")
            except Exception as e:
                print(f"[FaceEngine] Could not read existing model, retraining: {e}")
                self.train_from_dataset()
        else:
            self.train_from_dataset()

    def register_member(self, name: str, relationship: str, image_bytes_or_bgr):
        """
        Enroll a new family member:
        1. Decode/prepare BGR image
        2. Detect face
        3. Save face photo to data/family/
        4. Add database record
        5. Retrain model
        """
        if isinstance(image_bytes_or_bgr, (bytes, bytearray)):
            nparr = np.frombuffer(image_bytes_or_bgr, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        elif isinstance(image_bytes_or_bgr, np.ndarray):
            img = image_bytes_or_bgr
        else:
            raise ValueError("Unsupported image format for registration")

        if img is None:
            return False, "Failed to decode image data"

        # Detect face (with multi-pass sensitivity)
        faces, gray = self.detect_faces(img)
        if len(faces) == 0:
            gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray_img, scaleFactor=1.05, minNeighbors=2, minSize=(30, 30))
            if len(faces) == 0 and self.profile_cascade is not None:
                faces = self.profile_cascade.detectMultiScale(gray_img, scaleFactor=1.05, minNeighbors=2, minSize=(30, 30))

        if len(faces) > 0:
            # Pick the largest face
            (x, y, w, h) = max(faces, key=lambda b: b[2] * b[3])
            pad_x = int(w * 0.15)
            pad_y = int(h * 0.15)
            ih, iw = img.shape[:2]
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(iw, x + w + pad_x)
            y2 = min(ih, y + h + pad_y)
            face_crop = img[y1:y2, x1:x2]
        else:
            # Fallback for pre-cropped face portraits or close-ups
            ih, iw = img.shape[:2]
            if ih >= 40 and iw >= 40 and 0.4 <= (iw / ih) <= 2.5:
                face_crop = img
            else:
                return False, "No face detected in the provided image. Please ensure face is clearly visible."

        # Generate unique filename
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name.strip().lower())
        face_label = get_next_face_label()
        filename = f"{face_label}_{safe_name}.jpg"
        save_path = FAMILY_DIR / filename
        cv2.imwrite(str(save_path), face_crop)

        # Relative path for portable storage
        rel_path = f"data/family/{filename}"

        # Insert to DB
        member_id = add_family_member(name.strip(), relationship.strip(), rel_path, face_label)

        # Retrain model
        self.train_from_dataset()

        return True, {
            "id": member_id,
            "name": name,
            "relationship": relationship,
            "photo_path": rel_path,
            "face_label": face_label
        }

    def remove_member(self, member_id: int):
        """Remove a family member and retrain model"""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT photo_path FROM family_members WHERE id = ?", (member_id,))
        row = cur.fetchone()
        conn.close()

        if row and row["photo_path"]:
            p = DATA_DIR.parent / row["photo_path"]
            if p.exists():
                try:
                    os.remove(p)
                except Exception:
                    pass

        delete_family_member(member_id)
        self.train_from_dataset()
        return True

    def identify_faces(self, frame_bgr):
        """
        Analyze a frame:
        Returns list of dicts:
        [{
            'bbox': (x, y, w, h),
            'is_known': bool,
            'name': str,
            'relationship': str,
            'confidence': float, # 0.0 - 100.0%
            'distance': float
        }]
        """
        faces, gray = self.detect_faces(frame_bgr)
        results = []

        # Distance threshold from config (default ~70.0 for LBPH)
        # In LBPH, 0 = identical match, 50 = very strong match, 75 = moderate match, >80 = different person
        threshold = float(config.get("face_confidence_threshold", 70.0))

        for (x, y, w, h) in faces:
            face_chip = self.preprocess_face(gray[y:y+h, x:x+w])
            
            if not self.is_trained or len(self.label_to_member) == 0:
                # No family registered yet -> any detected face is an UNKNOWN INTRUDER
                results.append({
                    "bbox": (int(x), int(y), int(w), int(h)),
                    "is_known": False,
                    "name": "UNKNOWN INTRUDER",
                    "relationship": "Unregistered",
                    "confidence": 0.0,
                    "distance": 999.0
                })
                continue

            try:
                label, distance = self.recognizer.predict(face_chip)
                
                # Check if distance is below threshold and label is in members
                if distance <= threshold and label in self.label_to_member:
                    member = self.label_to_member[label]
                    # Calculate intuitive confidence % (e.g., distance 30 -> 75%, distance 50 -> 60%)
                    conf_pct = max(10.0, min(99.0, 100.0 - (distance * 0.75)))
                    results.append({
                        "bbox": (int(x), int(y), int(w), int(h)),
                        "is_known": True,
                        "name": member["name"],
                        "relationship": member["relationship"],
                        "confidence": round(conf_pct, 1),
                        "distance": round(distance, 1)
                    })
                else:
                    # Does not match any registered family member
                    results.append({
                        "bbox": (int(x), int(y), int(w), int(h)),
                        "is_known": False,
                        "name": "UNKNOWN INTRUDER",
                        "relationship": "Intruder",
                        "confidence": 0.0,
                        "distance": round(distance, 1)
                    })
            except Exception as e:
                print(f"[FaceEngine] Predict error: {e}")
                results.append({
                    "bbox": (int(x), int(y), int(w), int(h)),
                    "is_known": False,
                    "name": "UNKNOWN INTRUDER",
                    "relationship": "Unknown",
                    "confidence": 0.0,
                    "distance": 999.0
                })

        return results

# Global FaceEngine instance
face_engine = FaceEngine()
