import os
import cv2
import time
import base64
from pathlib import Path
from flask import Flask, render_template, Response, request, jsonify, send_from_directory

from core.config import config, DATA_DIR, SNAPSHOTS_DIR, FAMILY_DIR, EMAILS_DIR
from core.database import (
    get_all_family_members,
    get_recent_intrusion_events,
    get_recent_emails,
    get_event_stats
)
from core.face_engine import face_engine
from core.camera import camera
from core.security_controller import security_controller
from core.mailer import mailer

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = "home-security-master-key-2026"
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Serve uploaded / generated data files
@app.route("/data/snapshots/<path:filename>")
def serve_snapshot(filename):
    return send_from_directory(SNAPSHOTS_DIR, filename)

@app.route("/data/family/<path:filename>")
def serve_family_photo(filename):
    return send_from_directory(FAMILY_DIR, filename)

@app.route("/data/emails/<path:filename>")
def serve_email_preview(filename):
    return send_from_directory(EMAILS_DIR, filename)

@app.route("/")
def index():
    return render_template("index.html")

def generate_video_stream():
    """Generates continuous MJPEG video stream from security controller"""
    while True:
        frame = security_controller.get_annotated_frame()
        if frame is None or frame.size == 0:
            time.sleep(0.04)
            continue

        # Encode to JPEG
        ret, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ret:
            time.sleep(0.04)
            continue

        frame_bytes = buffer.tobytes()
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        time.sleep(0.04)

@app.route("/video_feed")
def video_feed():
    return Response(generate_video_stream(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

# --- API Endpoints ---

@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(security_controller.get_status())

@app.route("/api/arm", methods=["POST"])
def api_arm():
    data = request.get_json() or {}
    mode = data.get("mode", "ARMED_AWAY")
    pin = data.get("pin", "")
    success, msg = security_controller.arm(mode, pin)
    return jsonify({"success": success, "message": msg, "state": security_controller.state})

@app.route("/api/disarm", methods=["POST"])
def api_disarm():
    data = request.get_json() or {}
    pin = data.get("pin", "")
    success, msg = security_controller.disarm(pin)
    return jsonify({"success": success, "message": msg, "state": security_controller.state})

@app.route("/api/panic", methods=["POST"])
def api_panic():
    success, msg = security_controller.trigger_panic()
    return jsonify({"success": success, "message": msg})

@app.route("/api/silence", methods=["POST"])
def api_silence():
    data = request.get_json() or {}
    pin = data.get("pin", "")
    success, msg = security_controller.silence_alarm(pin)
    return jsonify({"success": success, "message": msg})

@app.route("/api/family", methods=["GET"])
def api_get_family():
    members = get_all_family_members()
    return jsonify({"success": True, "members": members})

@app.route("/api/family", methods=["POST"])
def api_add_family():
    """
    Registers a family member. Accepts:
    - Multipart Form: name, relationship, and file in 'photo'
    - JSON: name, relationship, image_base64
    """
    try:
        name = ""
        relationship = "Family"
        img_bytes = None

        if request.content_type and "multipart/form-data" in request.content_type:
            name = request.form.get("name", "").strip()
            relationship = request.form.get("relationship", "Family").strip()
            if "photo" in request.files:
                img_bytes = request.files["photo"].read()
        else:
            data = request.get_json() or {}
            name = data.get("name", "").strip()
            relationship = data.get("relationship", "Family").strip()
            img_b64 = data.get("image_base64", "")
            if img_b64:
                # Strip data:image/...;base64, prefix if present
                if "," in img_b64:
                    img_b64 = img_b64.split(",")[1]
                img_bytes = base64.b64decode(img_b64)

        if not name:
            return jsonify({"success": False, "message": "Please enter a name for the family member."}), 400

        if not img_bytes:
            return jsonify({"success": False, "message": "Please provide a face photo (upload or camera snapshot)."}), 400

        success, result = face_engine.register_member(name, relationship, img_bytes)
        if not success:
            return jsonify({"success": False, "message": result}), 400

        return jsonify({"success": True, "message": f"{name} successfully registered as {relationship}!", "member": result})

    except Exception as e:
        return jsonify({"success": False, "message": f"Registration error: {str(e)}"}), 500

@app.route("/api/family/<int:member_id>", methods=["DELETE"])
def api_delete_family(member_id):
    try:
        face_engine.remove_member(member_id)
        return jsonify({"success": True, "message": "Family member removed."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/events", methods=["GET"])
def api_get_events():
    limit = int(request.args.get("limit", 40))
    events = get_recent_intrusion_events(limit)
    return jsonify({"success": True, "events": events})

@app.route("/api/emails", methods=["GET"])
def api_get_emails():
    limit = int(request.args.get("limit", 20))
    emails = get_recent_emails(limit)
    return jsonify({"success": True, "emails": emails})

@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    safe_config = config.all()
    # Mask password
    if safe_config.get("smtp_password"):
        safe_config["smtp_password_masked"] = "••••••••"
    return jsonify({"success": True, "settings": safe_config})

@app.route("/api/settings", methods=["POST"])
def api_update_settings():
    data = request.get_json() or {}
    allowed_keys = [
        "owner_name", "owner_email", "smtp_enabled", "smtp_host",
        "smtp_port", "smtp_user", "smtp_password", "smtp_use_tls",
        "pin_code", "siren_enabled", "alert_cooldown_seconds",
        "face_confidence_threshold", "db_type", "mysql_host",
        "mysql_port", "mysql_user", "mysql_password", "mysql_db"
    ]
    updates = {}
    for k in allowed_keys:
        if k in data:
            if (k in ["smtp_password", "mysql_password"]) and data[k] is None:
                continue
            updates[k] = data[k]

    if updates:
        config.update(updates)
        # Re-initialize DB if DB parameters changed
        from core.database import init_db
        init_db()

    return jsonify({"success": True, "message": "Settings updated successfully."})

@app.route("/api/test_db", methods=["POST"])
def api_test_db():
    data = request.get_json() or {}
    host = data.get("mysql_host") or config.get("mysql_host", "localhost")
    port = int(data.get("mysql_port") or config.get("mysql_port", 3306))
    user = data.get("mysql_user") or config.get("mysql_user", "root")
    password = data.get("mysql_password")
    if password is None:
        password = config.get("mysql_password", "")
    db_name = data.get("mysql_db") or config.get("mysql_db", "home_intruder_system")

    from core.database import test_mysql_connection_params
    success, msg = test_mysql_connection_params(host, port, user, password, db_name)
    return jsonify({"success": success, "message": msg})

@app.route("/api/test_email", methods=["POST"])
def api_test_email():
    data = request.get_json() or {}
    target_email = data.get("email") or config.get("owner_email")
    if not target_email:
        return jsonify({"success": False, "message": "No email address provided."}), 400

    success, msg = mailer.send_test_email(target_email)
    return jsonify({"success": success, "message": msg})

@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    data = request.get_json() or {}
    sim_type = data.get("type", "intruder")
    duration = int(data.get("duration", 12))

    if sim_type == "intruder":
        camera.trigger_simulated_intruder(duration)
        return jsonify({"success": True, "message": f"Simulating unknown intruder walk-in for {duration} seconds."})
    elif sim_type == "family":
        member_name = data.get("name", "Family Member")
        camera.trigger_simulated_family(member_name, duration)
        return jsonify({"success": True, "message": f"Simulating arrival of {member_name} for {duration} seconds."})
    elif sim_type == "clear":
        camera.clear_simulation()
        return jsonify({"success": True, "message": "Simulation cleared."})
    else:
        return jsonify({"success": False, "message": "Unknown simulation type."}), 400

@app.route("/api/snapshot_current", methods=["GET"])
def api_snapshot_current():
    """Captures the current raw frame as a base64 JPEG for live face enrollment in the UI"""
    frame = camera.get_frame()
    if frame is None or frame.size == 0:
        return jsonify({"success": False, "message": "No camera frame available."}), 500

    ret, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ret:
        return jsonify({"success": False, "message": "Failed to encode frame."}), 500

    b64 = base64.b64encode(buffer).decode("utf-8")
    return jsonify({"success": True, "image_base64": f"data:image/jpeg;base64,{b64}"})

def create_app():
    return app
