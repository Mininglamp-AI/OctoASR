# coding=utf-8
"""Background service daemon"""

import argparse
import signal
import sys
from pathlib import Path

from octoasr.cli.utils.constants import DEFAULT_HOST, DEFAULT_PORT, PROJECT_ROOT
from octoasr.cli.utils.process import remove_pid


def signal_handler(signum, frame):
    remove_pid()
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--vad", default=None)
    parser.add_argument("--mention", default=None)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--model-type", default="auto", choices=["auto", "funasr", "qwen3_asr"])
    parser.add_argument("--load-on-startup", action="store_true")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--disable-auto-mention", action="store_true",
                        help="Disable semantic auto-@ for this service run")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    sys.path.insert(0, str(PROJECT_ROOT))

    import server

    server.MODEL_PATH = args.model
    server.VAD_MODEL_PATH = args.vad
    server.MENTION_MODEL_PATH = args.mention
    server.MODEL_TYPE = args.model_type
    server.HOST = args.host
    server.PORT = args.port
    server.LOAD_ON_STARTUP = args.load_on_startup
    server.DEBUG_MODE = args.debug
    server.AUTO_MENTION_DISABLED = args.disable_auto_mention

    import uvicorn

    try:
        uvicorn.run(server.app, host=args.host, port=args.port, log_level="info")
    finally:
        remove_pid()


if __name__ == "__main__":
    main()
