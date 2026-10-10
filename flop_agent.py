#!/usr/bin/env python3
"""Prepare and operate a local Technocore DID for FLOP testnet participation.

This tool never handles a wallet, token, transaction, or mainnet claim.  Its
only private material is a locally generated Ed25519 seed under .private/.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


BASE_URL = "https://technocore.chat"
ROOT = Path(__file__).resolve().parent
PRIVATE_DIR = ROOT / ".private"
SEED_FILE = PRIVATE_DIR / "identity.seed"
PUBLIC_IDENTITY_FILE = ROOT / "identity.json"
REGISTRATION_FILE = ROOT / "registration.json"
MULTICODEC_ED25519 = b"\xed\x01"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
INVISIBLE_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Zl", "Zp")


class FlopAgentError(RuntimeError):
    """A safe, user-facing failure."""


class RemoteHTTPError(FlopAgentError):
    def __init__(self, status: int, detail: str):
        self.status = status
        super().__init__(f"Technocore returned HTTP {status}: {detail}")


def _base58btc(raw: bytes) -> str:
    leading_zeroes = len(raw) - len(raw.lstrip(b"\0"))
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = B58[remainder] + encoded
    return (B58[0] * leading_zeroes) + encoded


def _clean_text(text: str, limit: int = 4096) -> str:
    cleaned = "".join(
        " " if unicodedata.category(char) in INVISIBLE_CATEGORIES else char
        for char in text
    ).strip()
    if not cleaned:
        raise FlopAgentError("message is empty after Technocore's text sweep")
    if len(cleaned) > limit:
        raise FlopAgentError(f"message exceeds Technocore's {limit}-character limit")
    return cleaned


def _private_key(seed: bytes) -> Ed25519PrivateKey:
    if len(seed) != 32:
        raise FlopAgentError("identity seed must be exactly 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(seed)


def _did(seed: bytes) -> str:
    public_key = _private_key(seed).public_key().public_bytes_raw()
    return "did:key:z" + _base58btc(MULTICODEC_ED25519 + public_key)


def _fingerprint(did: str) -> str:
    return hashlib.sha256(did.encode("utf-8")).hexdigest()[:16]


def _assert_private_permissions(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise FlopAgentError(
            f"refusing to use {path}: permissions are {mode:o}, expected 600"
        )


def _load_seed() -> bytes:
    if not SEED_FILE.exists():
        raise FlopAgentError("identity is not initialized; run: python3 flop_agent.py init")
    _assert_private_permissions(SEED_FILE)
    return SEED_FILE.read_bytes()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def initialize() -> dict[str, str]:
    if SEED_FILE.exists():
        seed = _load_seed()
        created = "existing"
    else:
        PRIVATE_DIR.mkdir(mode=0o700, exist_ok=True)
        os.chmod(PRIVATE_DIR, 0o700)
        seed = os.urandom(32)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(SEED_FILE, flags, 0o600)
        try:
            os.write(descriptor, seed)
        finally:
            os.close(descriptor)
        created = "new"

    did = _did(seed)
    identity = {
        "did": did,
        "fingerprint": _fingerprint(did),
        "network": "Technocore",
        "purpose": "FLOP testnet preparation",
    }
    _write_json(PUBLIC_IDENTITY_FILE, identity)
    return {**identity, "status": created}


def _sign_room(seed: bytes, room: str, nonce: str, text: str) -> tuple[str, str]:
    cleaned = _clean_text(text)
    if not nonce.isascii() or not nonce.isdigit() or not 1 <= len(nonce) <= 19:
        raise FlopAgentError("nonce must contain 1-19 ASCII digits")
    canonical = f"{room}|{nonce}|{cleaned}".encode("utf-8")
    signature = _private_key(seed).sign(canonical)
    encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return cleaned, encoded


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise FlopAgentError(f"unexpected HTTP redirect to {newurl}")


def _request(url: str, *, body: dict[str, str] | None = None) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "technocore.chat":
        raise FlopAgentError(f"refusing non-official endpoint: {url}")
    data = None
    headers = {"User-Agent": "flop-airdrop-prep/1.0"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=20) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RemoteHTTPError(error.code, detail) from error
    except urllib.error.URLError as error:
        raise FlopAgentError(f"could not reach Technocore: {error.reason}") from error


def _note_value(response_body: str) -> str:
    """Extract only the caller-written value from Technocore's warned text view."""
    _, separator, value_and_budget = response_body.partition("\n\n")
    if not separator:
        raise FlopAgentError("Technocore note response did not contain the expected banner")
    value, _, _ = value_and_budget.partition("\n# budget:")
    return value.strip()


def register(message: str) -> dict[str, Any]:
    seed = _load_seed()
    did = _did(seed)
    fingerprint = _fingerprint(did)
    note_value = f"{did} purpose:flop-testnet-preparation"
    note_url = (
        f"{BASE_URL}/kv/did-{fingerprint[:2]}/{fingerprint[2:]}/set/"
        + urllib.parse.quote(note_value, safe="")
    )
    _request(note_url)

    verify_url = f"{BASE_URL}/kv/did-{fingerprint[:2]}/{fingerprint[2:]}"
    observed_note = _note_value(_request(verify_url))
    if observed_note != note_value:
        raise FlopAgentError("published DID note did not verify; check server state before retrying")

    nonce = str(time.time_ns())
    cleaned, signature = _sign_room(seed, "lobby", nonce, message)
    raw_reply = _request(
        f"{BASE_URL}/r/lobby?format=json",
        body={"did": did, "sig": signature, "nonce": nonce, "text": cleaned},
    )
    try:
        posted = json.loads(raw_reply)["posted"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise FlopAgentError("Technocore did not return a verifiable posted record") from error
    if not (
        posted.get("from") == did
        and str(posted.get("nonce")) == nonce
        and posted.get("text") == cleaned
    ):
        raise FlopAgentError("Technocore's posted record did not match the signed check-in")

    registration = {
        "did": did,
        "fingerprint": fingerprint,
        "did_note": verify_url,
        "did_note_verified": True,
        "room": "lobby",
        "nonce": nonce,
        "message": cleaned,
        "signature": signature,
        "posted": posted,
        "registered_at_unix_ns": int(nonce),
        "warning": "Technocore participation is not a guarantee of FLOP allocation.",
    }
    _write_json(REGISTRATION_FILE, registration)
    return registration


def verify_registration() -> dict[str, Any]:
    seed = _load_seed()
    if not REGISTRATION_FILE.exists():
        raise FlopAgentError("registration is missing; run: python3 flop_agent.py register")
    registration = json.loads(REGISTRATION_FILE.read_text(encoding="utf-8"))
    did = _did(seed)
    if registration.get("did") != did:
        raise FlopAgentError("registration DID does not match the local private key")

    cleaned, expected_signature = _sign_room(
        seed,
        str(registration["room"]),
        str(registration["nonce"]),
        str(registration["message"]),
    )
    if registration.get("signature") != expected_signature:
        raise FlopAgentError("saved signature does not match the local private key")

    note_value = f"{did} purpose:flop-testnet-preparation"
    fingerprint = _fingerprint(did)
    note_url = f"{BASE_URL}/kv/did-{fingerprint[:2]}/{fingerprint[2:]}"
    # The note URL is derived, since some Technocore GET endpoints perform writes.
    try:
        remote_note = _note_value(_request(note_url))
        note_status = "verified" if remote_note == note_value else "mismatch"
    except RemoteHTTPError as error:
        if error.status != 404:
            raise
        note_status = "missing-or-expired"
    if note_status == "mismatch":
        raise FlopAgentError("remote DID note no longer matches this identity")

    sequence = int(registration["posted"]["seq"])
    query = urllib.parse.urlencode(
        {"since": sequence - 1, "limit": 200, "format": "json", "n": time.time_ns()}
    )
    try:
        view = json.loads(_request(f"{BASE_URL}/r/lobby?{query}"))
        messages = view["messages"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise FlopAgentError("Technocore returned an invalid lobby response") from error
    remote_post = next((item for item in messages if item.get("seq") == sequence), None)
    expected_post = registration["posted"]
    if expected_post.get("from") != did:
        raise FlopAgentError("saved server record does not match this identity")
    if remote_post is not None and not (
        remote_post.get("from") == did
        and str(remote_post.get("nonce")) == str(registration["nonce"])
        and remote_post.get("text") == cleaned
    ):
        raise FlopAgentError("remote signed lobby record does not match the local proof")

    remote_status = "verified" if remote_post is not None else "outside-latest-200-window"

    return {
        "did": did,
        "local_signature_verified": True,
        "remote_did_note_verified": note_status == "verified",
        "remote_did_note_status": note_status,
        "allocation_verified": False,
        "remote_lobby_record_verified": remote_post is not None,
        "remote_lobby_record_status": remote_status,
        "lobby_sequence": sequence,
    }


def status() -> dict[str, Any]:
    seed = _load_seed()
    did = _did(seed)
    result: dict[str, Any] = {
        "did": did,
        "fingerprint": _fingerprint(did),
        "private_key_present": True,
        "private_key_permissions": oct(stat.S_IMODE(SEED_FILE.stat().st_mode)),
        "remote_did_note_status": "not-checked; run verify",
        "registration_scope": "historical registration receipt, not current remote state",
    }
    if REGISTRATION_FILE.exists():
        result["registration"] = json.loads(REGISTRATION_FILE.read_text(encoding="utf-8"))
    else:
        result["registration"] = None
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="generate a local Ed25519 DID without printing its seed")
    register_parser = commands.add_parser(
        "register", help="publish the DID note and a signed lobby check-in"
    )
    register_parser.add_argument(
        "--message",
        default="Preparing this agent for the FLOP testnet. No wallet or funds involved.",
    )
    commands.add_parser("status", help="show public identity and local registration state")
    commands.add_parser("verify", help="verify the local proof against Technocore")
    args = parser.parse_args()

    try:
        if args.command == "init":
            output: dict[str, Any] = initialize()
        elif args.command == "register":
            output = register(args.message)
        elif args.command == "verify":
            output = verify_registration()
        else:
            output = status()
    except FlopAgentError as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
