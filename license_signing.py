"""
license_signing.py  --  Ed25519 signing / verification for Alien AI Trader licenses.

Why this exists: the app must not trust a hand-written license.json. Licenses are
signed with a PRIVATE key that lives ONLY on the owner's machine and the central
license server (env var LICENSE_PRIVATE_KEY). Every installed copy verifies with the
PUBLIC key embedded below, which is safe to distribute. Without the private key, a
license cannot be forged.

- Owner machine / server: holds the private key -> can sign (owner_grant.py, the
  /api/license/validate response).
- Every user's app: has only the public key -> can verify, never sign.
"""
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Public verification key (safe to ship). Verifies licenses; cannot create them.
PUBLIC_KEY_HEX = "35bcc1b6a815f23fe494b419eec99ca0e3bc619cbb49fe07ddc8ad915fb131fa"


def canonical_message(lic: dict) -> bytes:
    """Deterministic bytes covered by the signature. Signer and verifier MUST build
    this identically, so the field set and order are fixed here."""
    parts = [
        str(lic.get("appId", "alien-ai-trader")),
        str(lic.get("email", "")),
        str(lic.get("tier", "")),
        str(lic.get("status", "")),
        str(int(lic.get("expiresAt", 0) or 0)),
        str(lic.get("licenseKey", "")),
    ]
    return "|".join(parts).encode("utf-8")


def _load_private_key_hex():
    """Owner/server only: env var first, then a local key file. None on user copies."""
    hexkey = os.environ.get("LICENSE_PRIVATE_KEY")
    if hexkey:
        return hexkey.strip()
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, "license_private_key.pem")) as f:
            return f.read().strip()
    except Exception:
        return None


def can_sign() -> bool:
    """True only where the private key is available (owner machine / central server)."""
    return bool(_load_private_key_hex())


def sign_license(lic: dict) -> dict:
    """Return a copy of lic with a valid 'signature'. Requires the private key."""
    hexkey = _load_private_key_hex()
    if not hexkey:
        raise RuntimeError(
            "No signing key (set LICENSE_PRIVATE_KEY or place license_private_key.pem)."
        )
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(hexkey))
    signed = dict(lic)
    signed.pop("signature", None)
    signed["signature"] = priv.sign(canonical_message(signed)).hex()
    return signed


def verify_license(lic: dict) -> bool:
    """True only if lic carries a signature produced by the matching private key.
    A missing, tampered, or hand-written signature returns False."""
    if not isinstance(lic, dict):
        return False
    sig_hex = lic.get("signature")
    if not sig_hex:
        return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
        pub.verify(bytes.fromhex(sig_hex), canonical_message(lic))
        return True
    except Exception:
        return False
