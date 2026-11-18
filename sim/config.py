"""Load config/sandbox.yaml plus secrets from the environment (.env locally)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "sandbox.yaml"
STATE_DIR = ROOT / "state"
BUILD_DIR = ROOT / "build"
ARTIFACT_DIR = ROOT / "artifacts"


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (KEY=VALUE lines). Real env vars win over the file."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass
class Secrets:
    district_id: str
    district_token: str
    sftp_host: str
    sftp_port: int
    sftp_username: str
    sftp_password: str
    sftp_host_key: str
    login_url: str
    api_base: str

    @classmethod
    def from_env(cls) -> "Secrets":
        load_dotenv()
        g = os.environ.get
        return cls(
            district_id=g("CLEVER_DISTRICT_ID", ""),
            district_token=g("CLEVER_DISTRICT_TOKEN", ""),
            sftp_host=g("CLEVER_SFTP_HOST", "sftp2.clever.com"),
            sftp_port=int(g("CLEVER_SFTP_PORT", "22")),
            sftp_username=g("CLEVER_SFTP_USERNAME", ""),
            sftp_password=g("CLEVER_SFTP_PASSWORD", ""),
            sftp_host_key=g("CLEVER_SFTP_HOST_KEY", ""),
            login_url=g("CLEVER_LOGIN_URL", ""),
            api_base=g("CLEVER_API_BASE", "https://api.clever.com/v3.0"),
        )

    def require(self, *names: str) -> None:
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            env = {
                "district_id": "CLEVER_DISTRICT_ID",
                "district_token": "CLEVER_DISTRICT_TOKEN",
                "sftp_username": "CLEVER_SFTP_USERNAME",
                "sftp_password": "CLEVER_SFTP_PASSWORD",
                "login_url": "CLEVER_LOGIN_URL",
            }
            raise SystemExit("Missing settings: " + ", ".join(env.get(n, n) for n in missing))


def load_config(path: Path | None = None) -> dict:
    with open(path or CONFIG_PATH) as f:
        return yaml.safe_load(f)
