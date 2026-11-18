"""Talking to Clever: the district safety check, the Events API, and SFTP upload."""
from __future__ import annotations

import base64
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import Secrets


class GuardError(SystemExit):
    pass


# ----------------------------------------------------------------- Data API
def _get(sec: Secrets, path: str, params: dict | None = None) -> dict:
    url = path if path.startswith("http") else f"{sec.api_base.rstrip('/')}/{path.lstrip('/')}"
    if url.startswith("/"):
        url = "https://api.clever.com" + url
    resp = requests.get(url, params=params, timeout=30,
                        headers={"Authorization": f"Bearer {sec.district_token}", "Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()


def verify_sandbox_district(cfg: dict, sec: Secrets) -> dict:
    """Refuse to touch anything unless the token's district is the configured sandbox.

    The district token is scoped to exactly one district, so this confirms the
    credentials we hold point at the sandbox we expect, by id AND name.
    """
    sec.require("district_id", "district_token")
    data = _get(sec, "districts")
    districts = [d["data"] for d in data.get("data", [])]
    if len(districts) != 1:
        raise GuardError(f"Expected exactly one district for this token, got {len(districts)}")
    d = districts[0]
    if d.get("id") != sec.district_id:
        raise GuardError(f"Token district {d.get('id')} != CLEVER_DISTRICT_ID {sec.district_id}. Refusing.")
    prefixes = cfg["district"].get("required_name_prefixes", [])
    if prefixes and not any(d.get("name", "").startswith(p) for p in prefixes):
        raise GuardError(f"District name {d.get('name')!r} lacks a sandbox prefix {prefixes}. Refusing.")
    return d


def events_report(sec: Secrets, cursor_path: Path) -> dict:
    """Count events since the last run. The first run just records a starting cursor."""
    cursor = json.loads(cursor_path.read_text()).get("last_event_id") if cursor_path.exists() else None
    if not cursor:
        latest = _get(sec, "events", {"ending_before": "last", "limit": 1}).get("data", [])
        last_id = latest[0]["data"]["id"] if latest else ""
        _save_cursor(cursor_path, last_id)
        return {"baseline": True, "last_event_id": last_id, "counts": {}, "total": 0}

    counts: Counter = Counter()
    samples: dict[str, str] = {}
    last_id, pages = cursor, 0
    params = {"starting_after": cursor, "limit": 1000}
    while True:
        page = _get(sec, "events", params)
        items = page.get("data", [])
        for item in items:
            ev = item["data"]
            counts[ev["type"]] += 1
            obj = ev.get("data", {}).get("object", {})
            if ev["type"] not in samples:
                name = obj.get("name")
                label = (f"{name.get('first', '')} {name.get('last', '')}".strip() if isinstance(name, dict)
                         else name or obj.get("id", ""))
                samples[ev["type"]] = label
            last_id = ev["id"]
        pages += 1
        if len(items) < params["limit"] or pages > 50:
            break
        params = {"starting_after": last_id, "limit": 1000}
    _save_cursor(cursor_path, last_id)
    return {"baseline": False, "last_event_id": last_id, "counts": dict(sorted(counts.items())),
            "total": sum(counts.values()), "samples": samples}


def _save_cursor(path: Path, last_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_event_id": last_id,
                                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=1) + "\n")


# ----------------------------------------------------------------- SFTP
KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521")


def parse_host_key(value: str):
    """Find '<key-type> <base64>' anywhere in an ssh-keyscan line. None if there isn't one."""
    import paramiko
    parts = (value or "").split()
    for i, tok in enumerate(parts[:-1]):
        if tok in KEY_TYPES:
            try:
                return paramiko.PKey.from_type_string(tok, base64.b64decode(parts[i + 1]))
            except Exception:
                return None
    return None


def sftp_upload(sec: Secrets, files: list[Path], min_interval_minutes: int = 60, last_upload_at: str = "") -> None:
    """Upload all five files to the SFTP home directory, overwriting the previous set.

    Clever processes the set 5 minutes after the last activity, so the files are
    sent back to back. Clever asks for uploads no more than hourly; we enforce it.
    """
    import paramiko

    sec.require("sftp_username", "sftp_password")
    if last_upload_at:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last_upload_at)
        if age.total_seconds() < min_interval_minutes * 60:
            raise GuardError(f"Last upload was {int(age.total_seconds() // 60)} min ago; Clever allows at most hourly.")

    client = paramiko.SSHClient()
    key = parse_host_key(sec.sftp_host_key)
    if key:
        client.get_host_keys().add(sec.sftp_host, key.get_name(), key)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        if sec.sftp_host_key:
            print("WARNING: CLEVER_SFTP_HOST_KEY doesn't contain a key (expected e.g. 'ssh-rsa AAAA...'); "
                  "ignoring it.")
        print("WARNING: SFTP server key not pinned; accepting it as presented.")
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(sec.sftp_host, port=sec.sftp_port, username=sec.sftp_username, password=sec.sftp_password,
                   look_for_keys=False, allow_agent=False, timeout=30)
    try:
        sftp = client.open_sftp()
        for p in files:
            sftp.put(str(p), p.name)
            print(f"  uploaded {p.name} ({p.stat().st_size:,} bytes)")
        sftp.close()
    finally:
        client.close()
