import os
import json
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FAMILY_DIR = DATA_DIR / "family"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
EMAILS_DIR = DATA_DIR / "emails"
CONFIG_FILE = DATA_DIR / "config.json"

# Ensure runtime directories exist
for path in [DATA_DIR, FAMILY_DIR, SNAPSHOTS_DIR, EMAILS_DIR]:
    path.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "owner_name": "Homeowner",
    "owner_email": "owner@example.com",
    "smtp_enabled": False,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_use_tls": True,
    "alarm_state": "ARMED_AWAY",  # DISARMED, ARMED_AWAY, ARMED_HOME
    "pin_code": "1234",
    "face_confidence_threshold": 70.0,  # Lower distance / higher confidence threshold
    "alert_cooldown_seconds": 20,
    "siren_enabled": True,
    "camera_source": "0",  # "0" for default physical webcam, or "SIMULATOR"
    "simulation_mode": False,
    "db_type": "mysql",  # "mysql" (PyMySQL) or "sqlite"
    "mysql_host": "localhost",
    "mysql_port": 3306,
    "mysql_user": "root",
    "mysql_password": "",
    "mysql_db": "home_intruder_system"
}

class ConfigManager:
    def __init__(self, config_path=CONFIG_FILE):
        self.config_path = config_path
        self._config = self._load()

    def _load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Merge defaults for any missing keys
                    merged = DEFAULT_CONFIG.copy()
                    merged.update(data)
                    return merged
            except Exception as e:
                print(f"[Config] Error loading config: {e}. Falling back to defaults.")
        # Save default config
        self._save(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    def _save(self, config_data):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value
        self._save(self._config)

    def update(self, key_values: dict):
        self._config.update(key_values)
        self._save(self._config)

    def all(self):
        return self._config.copy()

# Global config instance
config = ConfigManager()
