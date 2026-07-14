import hashlib
import hmac
import json
import os
import threading
import time
from typing import Any, Dict


class AuditStream:
    """Append-only tamper-evident audit stream with HMAC signatures.

    Each event links to the previous event hash, creating a hash chain.
    Any deletion/reordering/edit breaks chain verification.
    """

    def __init__(self, data_dir: str, signing_key: str) -> None:
        self._lock = threading.Lock()
        self._signing_key = (signing_key or "").encode("utf-8")
        self._audit_dir = os.path.join(data_dir, "audit")
        self._audit_file = os.path.join(self._audit_dir, "events.jsonl")
        os.makedirs(self._audit_dir, exist_ok=True)
        self._last_hash = self._load_last_hash()

    @property
    def file_path(self) -> str:
        return self._audit_file

    def _load_last_hash(self) -> str:
        if not os.path.exists(self._audit_file):
            return "GENESIS"
        last_line = ""
        try:
            with open(self._audit_file, "rb") as f:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                while pos > 0:
                    pos -= 1
                    f.seek(pos, os.SEEK_SET)
                    ch = f.read(1)
                    if ch == b"\n" and last_line:
                        break
                    if ch != b"\n":
                        last_line = ch.decode("utf-8", errors="replace") + last_line
            if not last_line.strip():
                return "GENESIS"
            obj = json.loads(last_line)
            return str(obj.get("event_hash") or "GENESIS")
        except Exception:
            return "GENESIS"

    def _sign(self, msg: bytes) -> str:
        return hmac.new(self._signing_key, msg, hashlib.sha256).hexdigest()

    def append(self, event_type: str, actor: str, ip: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = int(time.time())
        with self._lock:
            body = {
                "ts": now,
                "event_type": str(event_type),
                "actor": str(actor),
                "ip": str(ip),
                "payload": payload if isinstance(payload, dict) else {"value": str(payload)},
                "prev_hash": self._last_hash,
            }
            canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            signature = self._sign(canonical)
            event_hash = hashlib.sha256(canonical + signature.encode("utf-8")).hexdigest()
            entry = dict(body)
            entry["signature"] = signature
            entry["event_hash"] = event_hash

            with open(self._audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, separators=(",", ":"), sort_keys=True) + "\n")

            self._last_hash = event_hash
            return entry

    def verify(self) -> Dict[str, Any]:
        if not os.path.exists(self._audit_file):
            return {"ok": True, "count": 0, "message": "no events"}

        prev = "GENESIS"
        count = 0
        try:
            with open(self._audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    obj = json.loads(raw)
                    obj_prev = str(obj.get("prev_hash") or "")
                    if obj_prev != prev:
                        return {"ok": False, "count": count, "message": "hash chain broken", "at": count + 1}

                    body = {
                        "ts": obj.get("ts"),
                        "event_type": obj.get("event_type"),
                        "actor": obj.get("actor"),
                        "ip": obj.get("ip"),
                        "payload": obj.get("payload"),
                        "prev_hash": obj_prev,
                    }
                    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    expected_sig = self._sign(canonical)
                    got_sig = str(obj.get("signature") or "")
                    if not hmac.compare_digest(expected_sig.encode("utf-8"), got_sig.encode("utf-8")):
                        return {"ok": False, "count": count, "message": "signature mismatch", "at": count + 1}

                    expected_hash = hashlib.sha256(canonical + got_sig.encode("utf-8")).hexdigest()
                    got_hash = str(obj.get("event_hash") or "")
                    if expected_hash != got_hash:
                        return {"ok": False, "count": count, "message": "event hash mismatch", "at": count + 1}

                    prev = got_hash
                    count += 1
            return {"ok": True, "count": count, "message": "verified"}
        except Exception as e:
            return {"ok": False, "count": count, "message": f"verification error: {e}"}
