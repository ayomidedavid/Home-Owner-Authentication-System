import os
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path
from core.config import config, EMAILS_DIR
from core.database import log_outbox_email

class AlertMailer:
    def __init__(self):
        pass

    def build_alert_html(self, timestamp: str, event_type: str, camera_name: str, notes: str) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #1e293b; border-radius: 12px; border: 1px solid #dc2626; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            .header {{ background-color: #b91c1c; padding: 20px; text-align: center; color: #ffffff; }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }}
            .content {{ padding: 24px; }}
            .alert-box {{ background-color: rgba(220, 38, 38, 0.15); border-left: 4px solid #ef4444; padding: 12px 16px; margin-bottom: 20px; border-radius: 4px; }}
            .meta-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px; }}
            .meta-table td {{ padding: 8px 0; border-bottom: 1px solid #334155; }}
            .meta-table td.label {{ color: #94a3b8; font-weight: 600; width: 130px; }}
            .meta-table td.val {{ color: #f1f5f9; font-weight: 500; }}
            .photo-box {{ text-align: center; margin: 20px 0; background-color: #090d16; padding: 12px; border-radius: 8px; border: 1px solid #334155; }}
            .photo-box img {{ max-width: 100%; height: auto; border-radius: 6px; }}
            .footer {{ background-color: #0f172a; padding: 16px; text-align: center; font-size: 12px; color: #64748b; }}
            .badge {{ background-color: #ef4444; color: #fff; padding: 3px 8px; border-radius: 9999px; font-size: 11px; font-weight: 700; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>🚨 SECURITY INTRUDER ALERT</h1>
              <p style="margin: 4px 0 0; font-size: 14px; opacity: 0.9;">Unrecognized Individual Detected on Premises</p>
            </div>
            <div class="content">
              <div class="alert-box">
                <strong style="color: #ef4444;">WARNING:</strong> An unknown person was identified by your Home Security facial recognition scanner. The individual did not match any enrolled family members.
              </div>

              <table class="meta-table">
                <tr>
                  <td class="label">Date & Time:</td>
                  <td class="val">{timestamp}</td>
                </tr>
                <tr>
                  <td class="label">Detection Type:</td>
                  <td class="val"><span class="badge">{event_type}</span></td>
                </tr>
                <tr>
                  <td class="label">Camera Zone:</td>
                  <td class="val">{camera_name}</td>
                </tr>
                <tr>
                  <td class="label">System Action:</td>
                  <td class="val">Snapshot Captured, Alarm Logged, Owner Alerted</td>
                </tr>
                {f'<tr><td class="label">Details:</td><td class="val">{notes}</td></tr>' if notes else ''}
              </table>

              <div class="photo-box">
                <p style="margin-top: 0; color: #94a3b8; font-size: 13px;">Captured Intruder Evidence Photo (also attached):</p>
                <img src="cid:intruder_snapshot" alt="Intruder Snapshot">
              </div>
            </div>
            <div class="footer">
              This automated alert was dispatched by your local Home Security System.
            </div>
          </div>
        </body>
        </html>
        """

    def send_intruder_alert(self, snapshot_path: str, timestamp: str = None, event_type: str = "UNKNOWN_INTRUDER", camera_name: str = "Front Entrance Camera", notes: str = "") -> bool:
        if not timestamp:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        recipient = config.get("owner_email", "owner@example.com")
        subject = f"🚨 [INTRUDER ALERT] Unrecognized person detected at {timestamp}"
        body_html = self.build_alert_html(timestamp, event_type, camera_name, notes)

        # Build MIME Message
        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"] = config.get("smtp_user") or "security@home-intruder-system.local"
        msg["To"] = recipient

        # Alternative container for HTML
        msg_alternative = MIMEMultipart("alternative")
        msg.attach(msg_alternative)

        # Attach HTML text
        msg_html = MIMEText(body_html, "html")
        msg_alternative.attach(msg_html)

        # Attach Snapshot Image inline & as attachment
        snapshot_file = Path(snapshot_path)
        if snapshot_file.exists():
            try:
                with open(snapshot_file, "rb") as f:
                    img_data = f.read()
                    # Inline image for cid:intruder_snapshot
                    img_inline = MIMEImage(img_data)
                    img_inline.add_header("Content-ID", "<intruder_snapshot>")
                    img_inline.add_header("Content-Disposition", "inline", filename=snapshot_file.name)
                    msg.attach(img_inline)

                    # Attachment
                    img_attach = MIMEImage(img_data)
                    img_attach.add_header("Content-Disposition", "attachment", filename=snapshot_file.name)
                    msg.attach(img_attach)
            except Exception as e:
                print(f"[Mailer] Error attaching snapshot {snapshot_path}: {e}")

        # Always save a local copy to data/emails for dashboard viewing
        safe_time = timestamp.replace(":", "-").replace(" ", "_")
        local_email_file = EMAILS_DIR / f"alert_{safe_time}.html"
        try:
            with open(local_email_file, "w", encoding="utf-8") as f:
                f.write(body_html)
        except Exception as e:
            print(f"[Mailer] Error saving local email copy: {e}")

        # Attempt SMTP dispatch if configured
        smtp_enabled = config.get("smtp_enabled", False)
        smtp_host = config.get("smtp_host", "")
        smtp_port = int(config.get("smtp_port", 587))
        smtp_user = config.get("smtp_user", "")
        smtp_pass = config.get("smtp_password", "")
        use_tls = config.get("smtp_use_tls", True)

        if smtp_enabled and smtp_host and smtp_user and smtp_pass:
            try:
                if smtp_port == 465:
                    server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
                else:
                    server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                    if use_tls:
                        server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(msg["From"], [recipient], msg.as_string())
                server.quit()
                print(f"[Mailer] Successfully delivered alert email to {recipient} via {smtp_host}")
                log_outbox_email(recipient, subject, body_html, str(snapshot_file), "SENT")
                return True
            except Exception as e:
                err_msg = str(e)
                print(f"[Mailer] SMTP send failed: {err_msg}. Saved to local outbox.")
                log_outbox_email(recipient, subject, body_html, str(snapshot_file), "FAILED", err_msg)
                return False
        else:
            # Stored in local outbox
            print(f"[Mailer] SMTP not active. Alert logged to local outbox for {recipient}")
            log_outbox_email(recipient, subject, body_html, str(snapshot_file), "OFFLINE_SAVED", "SMTP not enabled or credentials pending")
            return True

    def send_test_email(self, to_email: str) -> tuple[bool, str]:
        """Test SMTP connection and send a test message"""
        smtp_host = config.get("smtp_host", "")
        smtp_port = int(config.get("smtp_port", 587))
        smtp_user = config.get("smtp_user", "")
        smtp_pass = config.get("smtp_password", "")
        use_tls = config.get("smtp_use_tls", True)

        if not (smtp_host and smtp_user and smtp_pass):
            return False, "SMTP Host, Username, or Password is missing in settings."

        try:
            msg = MIMEMultipart()
            msg["Subject"] = "✅ Home Security - Test Notification"
            msg["From"] = smtp_user
            msg["To"] = to_email
            body = """
            <h2>Home Security - Email Test Successful</h2>
            <p>Your email notification settings are configured correctly! You will receive high-priority intruder alerts with photo evidence at this email address whenever an unknown individual is detected.</p>
            """
            msg.attach(MIMEText(body, "html"))

            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                if use_tls:
                    server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_email], msg.as_string())
            server.quit()
            return True, f"Test email sent successfully to {to_email}"
        except Exception as e:
            return False, f"SMTP Connection error: {str(e)}"

mailer = AlertMailer()
