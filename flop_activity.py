#!/usr/bin/env python3
"""Create useful, signed FLOP/Technocore activity without automated spam."""

from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature

import flop_agent


ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "activity_state.json"
ACTIVITY_FILE = ROOT / "activity.jsonl"
TESTNET_FILE = ROOT / "testnet_activity.jsonl"
HARDWARE_FILE = ROOT / "hardware_snapshot.json"
MIN_PUBLIC_POST_INTERVAL_SECONDS = 6 * 60 * 60
INITIAL_MESSAGE = (
    "FLOP Japanese safety note (2026-08-28): the official draft says the Q4 2026 "
    "testnet activity earns the genesis airdrop, and agents are mainly measured by test "
    "tokens spent on inference. No claim contract is announced. Never send funds or a "
    "wallet seed. Sources: https://flop.finance/teaser/ and "
    "https://github.com/flop-labs/technocore-chat"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _encode_signature(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_signature(encoded: str) -> bytes:
    return base64.urlsafe_b64decode(encoded + "==")


def _validate_source(source: str) -> str:
    parsed = urllib.parse.urlsplit(source)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise flop_agent.FlopAgentError("source must be a public HTTPS URL without credentials")
    return source


def _post_signed(
    room: str,
    text: str,
    *,
    kind: str,
    source: str,
    enforce_interval: bool,
) -> dict[str, Any]:
    state = _load_json(STATE_FILE)
    seed = flop_agent._load_seed()
    did = flop_agent._did(seed)
    if state.get("room") != room or state.get("did") != did:
        raise flop_agent.FlopAgentError("activity room is not initialized")

    now_ns = time.time_ns()
    last_post_ns = int(state.get("last_post_at_unix_ns", 0))
    if enforce_interval and now_ns - last_post_ns < MIN_PUBLIC_POST_INTERVAL_SECONDS * 1_000_000_000:
        remaining = MIN_PUBLIC_POST_INTERVAL_SECONDS - (now_ns - last_post_ns) // 1_000_000_000
        raise flop_agent.FlopAgentError(
            f"public posting is limited to one useful update per 6 hours; retry in {remaining}s"
        )

    nonce = str(now_ns)
    cleaned, signature = flop_agent._sign_room(seed, room, nonce, text)
    reply = flop_agent._request(
        f"{flop_agent.BASE_URL}/r/{room}?format=json",
        body={"did": did, "sig": signature, "nonce": nonce, "text": cleaned},
    )
    try:
        posted = json.loads(reply)["posted"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise flop_agent.FlopAgentError("Technocore did not return a posted record") from error
    if not (
        posted.get("from") == did
        and str(posted.get("nonce")) == nonce
        and posted.get("text") == cleaned
    ):
        raise flop_agent.FlopAgentError("Technocore posted record did not match the signature")

    permalink = f"{flop_agent.BASE_URL}/humans#r/{room}/{posted['seq']}"
    record = {
        "kind": kind,
        "did": did,
        "room": room,
        "source": source,
        "text": cleaned,
        "nonce": nonce,
        "signature": signature,
        "posted": posted,
        "permalink": permalink,
    }
    _append_jsonl(ACTIVITY_FILE, record)
    state["last_post_at_unix_ns"] = now_ns
    state["last_sequence"] = posted["seq"]
    state["last_message_url"] = permalink
    flop_agent._write_json(STATE_FILE, state)
    return record


def setup_room() -> dict[str, Any]:
    seed = flop_agent._load_seed()
    did = flop_agent._did(seed)
    room = "technocore"
    state = _load_json(STATE_FILE)

    if state:
        if state.get("did") != did or state.get("room") != room:
            raise flop_agent.FlopAgentError("existing activity state belongs to another DID")
        return {"status": "existing", **state}

    state = {
        "did": did,
        "room": room,
        "room_url": f"{flop_agent.BASE_URL}/humans#r/{room}",
        "mode": "shared-room-signed-writes",
        "initialized_at_unix_ns": time.time_ns(),
        "purpose": "Japanese FLOP testnet safety and evidence notes",
    }
    flop_agent._write_json(STATE_FILE, state)
    first = _post_signed(
        room,
        INITIAL_MESSAGE,
        kind="official-safety-note",
        source="https://flop.finance/teaser/",
        enforce_interval=False,
    )
    return {"status": "created", "room": room, "first_activity": first}


def publish(title: str, summary: str, source: str) -> dict[str, Any]:
    state = _load_json(STATE_FILE)
    if not state:
        raise flop_agent.FlopAgentError("run setup-room before publishing")
    source = _validate_source(source)
    title = flop_agent._clean_text(title, limit=120)
    summary = flop_agent._clean_text(summary, limit=700)
    text = f"{title} — {summary} Source: {source}"
    return _post_signed(
        str(state["room"]),
        text,
        kind="useful-update",
        source=source,
        enforce_interval=True,
    )


def record_testnet(action: str, reference: str, details: str) -> dict[str, Any]:
    """Record a real testnet action after it happened; never performs a transaction."""
    seed = flop_agent._load_seed()
    did = flop_agent._did(seed)
    payload = {
        "action": action,
        "details": flop_agent._clean_text(details, limit=1000),
        "did": did,
        "recorded_at_unix_ns": time.time_ns(),
        "reference": flop_agent._clean_text(reference, limit=500),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    signature = _encode_signature(flop_agent._private_key(seed).sign(canonical.encode("utf-8")))
    record = {"payload": payload, "signature": signature}
    _append_jsonl(TESTNET_FILE, record)
    return record


def verify_logs() -> dict[str, Any]:
    seed = flop_agent._load_seed()
    public_key = flop_agent._private_key(seed).public_key()
    did = flop_agent._did(seed)
    activities = _records(ACTIVITY_FILE)
    testnet = _records(TESTNET_FILE)
    try:
        for item in activities:
            canonical = f"{item['room']}|{item['nonce']}|{item['text']}".encode("utf-8")
            public_key.verify(_decode_signature(item["signature"]), canonical)
            if item["did"] != did or item["posted"]["from"] != did:
                raise flop_agent.FlopAgentError("activity log contains a different DID")
        for item in testnet:
            canonical = json.dumps(
                item["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            public_key.verify(_decode_signature(item["signature"]), canonical)
            if item["payload"]["did"] != did:
                raise flop_agent.FlopAgentError("testnet log contains a different DID")
    except (InvalidSignature, KeyError, TypeError) as error:
        raise flop_agent.FlopAgentError("an activity proof failed verification") from error
    return {
        "did": did,
        "public_activity_proofs_verified": len(activities),
        "testnet_action_proofs_verified": len(testnet),
    }


def status() -> dict[str, Any]:
    state = _load_json(STATE_FILE)
    hardware = _load_json(HARDWARE_FILE)
    return {
        "room": state.get("room"),
        "room_url": state.get("room_url"),
        "mode": state.get("mode"),
        "public_activity_count": len(_records(ACTIVITY_FILE)),
        "testnet_action_count": len(_records(TESTNET_FILE)),
        "official_primary_signal": "settled testnet compute spend; draft rules",
        "selected_track": hardware.get("selected_track", "agent"),
        "testnet_adapter": "pending official endpoint publication",
        "chain_activity_verified": False,
        "guarantee": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup-room", help="initialize signed activity and post one safety note")
    publish_parser = commands.add_parser("publish", help="publish one sourced, useful update")
    publish_parser.add_argument("--title", required=True)
    publish_parser.add_argument("--summary", required=True)
    publish_parser.add_argument("--source", required=True)
    record_parser = commands.add_parser("record-testnet", help="sign evidence of a real testnet action")
    record_parser.add_argument("--action", choices=("faucet", "inference", "prize", "other"), required=True)
    record_parser.add_argument("--reference", required=True, help="testnet transaction/session ID")
    record_parser.add_argument("--details", required=True)
    commands.add_parser("verify", help="verify every local activity signature")
    commands.add_parser("status", help="show activity readiness and counts")
    args = parser.parse_args()

    try:
        if args.command == "setup-room":
            result = setup_room()
        elif args.command == "publish":
            result = publish(args.title, args.summary, args.source)
        elif args.command == "record-testnet":
            result = record_testnet(args.action, args.reference, args.details)
        elif args.command == "verify":
            result = verify_logs()
        else:
            result = status()
    except flop_agent.FlopAgentError as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
