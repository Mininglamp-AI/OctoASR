# coding=utf-8
"""Background service daemon"""

import argparse
import signal
import sys
from pathlib import Path

from manoasr.cli.utils.constants import DEFAULT_PORT, PROJECT_ROOT
from manoasr.cli.utils.process import remove_pid


def signal_handler(signum, frame):
    remove_pid()
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--vad", default=None)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--model-type", default="auto", choices=["auto", "funasr", "qwen3_asr"])
    parser.add_argument("--load-on-startup", action="store_true")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    sys.path.insert(0, str(PROJECT_ROOT))

    import server

    server.MODEL_PATH = args.model
    server.VAD_MODEL_PATH = args.vad
    server.MODEL_TYPE = args.model_type
    server.HOST = "0.0.0.0"
    server.PORT = args.port
    server.LOAD_ON_STARTUP = args.load_on_startup
    server.DEBUG_MODE = args.debug

    import uvicorn

    try:
        uvicorn.run(server.app, host="0.0.0.0", port=args.port, log_level="info")
    finally:
        remove_pid()


if __name__ == "__main__":
    main()
