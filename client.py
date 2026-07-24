# coding=utf-8

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests


DEFAULT_AUDIO = Path(__file__).resolve().parent / "assets" / "BAC009S0764W0129.wav"
DEFAULT_URL = "http://127.0.0.1:8787"


def transcribe(
    base_url: str,
    audio_path: Path,
    mode: str = "smart",
    context_text: str = "",
    chat_context: str = "",
    personal_context: str = "",
    member_context: str = "",
    auth_token: str = "",
    timeout: float = 120.0,
) -> dict:
    url = f"{base_url.rstrip('/')}/v1/voice/transcribe"
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    data = {"mode": mode}
    if context_text:
        data["context_text"] = context_text
    if chat_context:
        data["chat_context"] = chat_context
    if personal_context:
        data["personal_context"] = personal_context
    if member_context:
        data["member_context"] = member_context

    with open(audio_path, "rb") as f:
        files = {"audio": (audio_path.name, f, "audio/wav")}
        started = time.time()
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=timeout)
        elapsed = time.time() - started

    print(f"[POST {url}] status={resp.status_code} elapsed={elapsed:.2f}s", file=sys.stderr)
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text}
    return body


def fetch_config(base_url: str, timeout: float = 10.0) -> dict:
    url = f"{base_url.rstrip('/')}/v1/voice/config"
    resp = requests.get(url, timeout=timeout)
    print(f"[GET {url}] status={resp.status_code}", file=sys.stderr)
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="OctoASR test client")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--mode", default="smart", choices=["smart", "append_only", "edit_only"])
    parser.add_argument("--context-text", default="")
    parser.add_argument("--chat-context", default="")
    parser.add_argument("--personal-context", default="")
    parser.add_argument("--member-context", default="")
    parser.add_argument("--auth-token", default="")
    parser.add_argument("--config-only", action="store_true", help="only fetch /v1/voice/config")
    args = parser.parse_args()

    if args.config_only:
        result = fetch_config(args.url)
    else:
        if not args.audio.exists():
            print(f"audio file not found: {args.audio}", file=sys.stderr)
            sys.exit(1)
        result = transcribe(
            base_url=args.url,
            audio_path=args.audio,
            mode=args.mode,
            context_text=args.context_text,
            chat_context=args.chat_context,
            personal_context=args.personal_context,
            member_context=args.member_context,
            auth_token=args.auth_token,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
