#!/usr/bin/env python3
"""Hook logger: write chat logs to AI-Chat-Logs every 5 rounds.

A round means: one user message + one ai message.
The script is event-driven and tolerates different payload shapes from hook providers.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "AI-Chat-Logs"
STATE_DIR = OUT_DIR / ".state"
STATE_FILE = STATE_DIR / "hook_state.json"

ROUNDS_PER_FILE = 5


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def default_state() -> Dict[str, Any]:
    return {
        "next_index": 1,
        "open_round": None,
        "completed_rounds": [],
        "session_started_at": None,
        "last_event": None,
    }


def load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return default_state()
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        state = default_state()
        state.update(data)
        return state
    except Exception:
        return default_state()


def save_state(state: Dict[str, Any]) -> None:
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def try_read_stdin_json() -> Dict[str, Any]:
    # Many hook runners pass payload via stdin. Keep this best-effort.
    try:
        import sys

        if sys.stdin and not sys.stdin.closed:
            raw = sys.stdin.read().strip()
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return {}


def parse_env_json(var_name: str) -> Dict[str, Any]:
    raw = os.environ.get(var_name, "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def first_non_empty(*values: Optional[str]) -> str:
    for v in values:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def dig(payload: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def normalize_role(event: str, payload: Dict[str, Any]) -> str:
    e = event.lower()
    if "user" in e or "prompt" in e:
        return "user"
    if "assistant" in e or "response" in e or "ai" in e:
        return "ai"

    role = first_non_empty(
        dig(payload, "role", "sender", "author", "actor"),
    ).lower()
    if role in {"user", "human"}:
        return "user"
    if role in {"assistant", "ai", "copilot", "model"}:
        return "ai"
    return "system"


def normalize_text(payload: Dict[str, Any], arg_text: str) -> str:
    direct = first_non_empty(
        arg_text,
        dig(payload, "text", "message", "content", "prompt", "response", "output"),
    )
    if direct:
        return direct

    data = payload.get("data")
    if isinstance(data, dict):
        nested = first_non_empty(
            dig(data, "text", "message", "content", "prompt", "response", "output"),
        )
        if nested:
            return nested

    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            return first_non_empty(
                dig(last, "text", "content", "message"),
            )

    return ""


def start_round_if_needed(state: Dict[str, Any], user_message: Dict[str, str]) -> None:
    open_round = state.get("open_round")
    if open_round and open_round.get("user") and not open_round.get("ai"):
        # Replace pending user message with latest one to avoid malformed streams.
        state["open_round"]["user"] = user_message
        return

    state["open_round"] = {"user": user_message, "ai": None}


def complete_round_if_possible(state: Dict[str, Any], ai_message: Dict[str, str]) -> None:
    open_round = state.get("open_round")
    if open_round and open_round.get("user") and not open_round.get("ai"):
        open_round["ai"] = ai_message
        state["completed_rounds"].append(open_round)
        state["open_round"] = None
        return

    # If AI message arrives without a user message, keep it as system note round.
    state["completed_rounds"].append(
        {
            "user": {"time": ai_message["time"], "text": "(missing user message)"},
            "ai": ai_message,
        }
    )


def write_chunk(state: Dict[str, Any], rounds: List[Dict[str, Any]]) -> Path:
    index = int(state.get("next_index", 1))
    out_file = OUT_DIR / f"chat-{index:04d}.md"

    lines: List[str] = []
    lines.append(f"# Chat Log {index:04d}")
    lines.append("")
    lines.append(f"Generated: {now_iso()}")
    lines.append(f"Rounds: {len(rounds)}")
    lines.append("")

    for i, r in enumerate(rounds, start=1):
        user = r.get("user") or {}
        ai = r.get("ai") or {}
        lines.append(f"## Round {i}")
        lines.append("")
        lines.append(f"### User @ {user.get('time', '')}")
        lines.append("")
        lines.append((user.get("text") or "(empty)").rstrip())
        lines.append("")
        lines.append(f"### AI @ {ai.get('time', '')}")
        lines.append("")
        lines.append((ai.get("text") or "(empty)").rstrip())
        lines.append("")

    out_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    state["next_index"] = index + 1
    return out_file


def flush_if_ready(state: Dict[str, Any]) -> Optional[Path]:
    rounds: List[Dict[str, Any]] = state.get("completed_rounds", [])
    if len(rounds) < ROUNDS_PER_FILE:
        return None

    chunk = rounds[:ROUNDS_PER_FILE]
    state["completed_rounds"] = rounds[ROUNDS_PER_FILE:]
    return write_chunk(state, chunk)


def handle_event(event: str, text: str, payload: Dict[str, Any]) -> str:
    ensure_dirs()
    state = load_state()
    state["last_event"] = {"name": event, "at": now_iso()}

    event_lower = event.lower()
    if event_lower == "sessionstart":
        state["session_started_at"] = now_iso()
        save_state(state)
        return "session_started"

    role = normalize_role(event, payload)
    message_text = normalize_text(payload, text)
    message = {"time": now_iso(), "text": message_text}

    if role == "user":
        start_round_if_needed(state, message)
    elif role == "ai":
        complete_round_if_possible(state, message)
    else:
        # System events are tracked only as metadata.
        pass

    out = flush_if_ready(state)

    if event_lower in {"sessionend", "conversationend"}:
        # Optional: flush remaining complete rounds at session end.
        rounds: List[Dict[str, Any]] = state.get("completed_rounds", [])
        if rounds:
            out = write_chunk(state, rounds)
            state["completed_rounds"] = []

    save_state(state)

    if out:
        return f"written:{out.name}"
    return "ok"


def main() -> None:
    parser = argparse.ArgumentParser(description="Copilot hook chat logger")
    parser.add_argument("--event", required=True, help="Hook event name")
    parser.add_argument("--text", default="", help="Message text if provided")
    args = parser.parse_args()

    payload = {}
    payload.update(parse_env_json("HOOK_PAYLOAD"))
    payload.update(parse_env_json("COPILOT_HOOK_PAYLOAD"))
    stdin_payload = try_read_stdin_json()
    if stdin_payload:
        payload.update(stdin_payload)

    result = handle_event(args.event, args.text, payload)
    print(result)


if __name__ == "__main__":
    main()
