# coding=utf-8

from __future__ import annotations

import argparse
import asyncio
import functools
import inspect
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.auto_model import AutoModel

from utils.hotwords_extractor import extract_terms as extract_hotwords_from_context
from utils.repetition_detector import check_repetition, has_repetition


def _setup_logger() -> logging.Logger:
    """Configure the app logger robustly.

    `logging.basicConfig` is a no-op once the root logger already has handlers,
    and uvicorn reconfigures logging on startup — so relying on basicConfig made
    "Transcribe OK" lines silently disappear. Attach our own StreamHandler to
    this module's logger and disable propagation so it always emits to
    stdout/stderr (which the daemon redirects to the log file) regardless of
    uvicorn's setup.
    """
    log = logging.getLogger(__name__)
    log.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in log.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        log.addHandler(handler)
    log.propagate = False
    return log


logger = _setup_logger()

MODEL_PATH: Optional[str] = None
VAD_MODEL_PATH: Optional[str] = None
MAX_FILE_SIZE = 30 * 1024 * 1024
MAX_DURATION = 660
MODEL_NAME = "mano-asr"
MODEL_TYPE = "auto"
ENGINE_NAME = "mlx"
AUTH_TOKEN: Optional[str] = None
HOST = "0.0.0.0"
PORT = 8787
LOAD_ON_STARTUP = False
DEBUG_MODE = False

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac"}
ALLOWED_MODES = {"smart", "append_only", "edit_only"}

CONTEXT_TEXT_LIMIT = 5000
CHAT_CONTEXT_LIMIT = 20000
PERSONAL_CONTEXT_LIMIT = 10000
MEMBER_CONTEXT_LIMIT = 5000

SESSIONS_DIR = Path.home() / ".mano-asr" / "sessions"

# 转写结果硬替换：模型常把这些英文专有名词输出成中文音译，强制改回目标写法
TRANSCRIPT_REPLACEMENTS = {
    "毕达哥拉斯": "Pythagoras",
    "彭特兰": "Pentland",
    "布鲁克斯": "Brooks",
    "哥德尔": "Godel",
    "冯·诺伊曼": "von Neumann",
    "冯诺伊曼": "von Neumann",
    "达芬奇": "Da Vinci",
    "达·芬奇": "Da Vinci",
    "卡诺": "Kano",
    "鬼谷子": "Guiguzi",
    "苏格拉底": "Socrates",
    "科特": "Kotter",
}

_model: Optional[AutoModel] = None
_model_lock = Lock()
_generate_lock: Optional[asyncio.Lock] = None
_model_executor: Optional[ThreadPoolExecutor] = None


def error_location(exc: Optional[BaseException] = None, caller_depth: int = 2) -> str:
    if exc is not None and exc.__traceback__ is not None:
        last_frame = traceback.extract_tb(exc.__traceback__)[-1]
        return f"{Path(last_frame.filename).name}:{last_frame.lineno} in {last_frame.name}"

    frame = inspect.currentframe()
    for _ in range(caller_depth):
        if frame is None:
            break
        frame = frame.f_back
    if frame is None:
        return "unknown"
    return f"{Path(frame.f_code.co_filename).name}:{frame.f_lineno} in {frame.f_code.co_name}"


def exception_detail(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{exc.__class__.__name__}: {text}" if text else exc.__class__.__name__


def api_error(
    status_code: int,
    message: str,
    *,
    detail: Optional[str] = None,
    location: Optional[str] = None,
    exc: Optional[BaseException] = None,
    request: Optional[Request] = None,
) -> JSONResponse:
    resolved_location = location or error_location(exc)
    resolved_detail = detail or (exception_detail(exc) if exc is not None else None)
    content = {"status": status_code, "msg": message, "location": resolved_location}
    if resolved_detail:
        content["detail"] = resolved_detail

    request_text = ""
    if request is not None:
        request_text = f" method={request.method} path={request.url.path}"

    log_level = logging.ERROR if status_code >= 500 else logging.WARNING
    exc_info = (type(exc), exc, exc.__traceback__) if exc is not None else None
    logger.log(
        log_level,
        "API error status=%s msg=%s location=%s detail=%s%s",
        status_code,
        message,
        resolved_location,
        resolved_detail or "",
        request_text,
        exc_info=exc_info,
    )
    return JSONResponse(status_code=status_code, content=content)


def save_session(record: dict[str, Any]) -> None:
    try:
        now = datetime.now()
        day_dir = SESSIONS_DIR / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        session_stem = f"{now.strftime('%H%M%S_%f')}_{uuid.uuid4().hex[:6]}"
        audio_files = record.pop("_audio_files", [])
        saved_audio_files = []
        recording_errors = []

        for item in audio_files:
            try:
                source_path = Path(item["source_path"])
                if not source_path.exists():
                    recording_errors.append(f"audio source not found: {source_path}")
                    continue

                role = item.get("role", "audio")
                suffix = source_path.suffix or Path(item.get("original_filename") or "").suffix or ".bin"
                target_path = day_dir / f"{session_stem}_{role}{suffix}"
                shutil.copy2(source_path, target_path)
                saved_audio_files.append({
                    "role": role,
                    "path": str(target_path),
                    "filename": target_path.name,
                    "original_filename": item.get("original_filename"),
                    "content_type": item.get("content_type"),
                    "size": target_path.stat().st_size,
                })
            except Exception as exc:
                recording_errors.append(f"failed to save audio file: {exception_detail(exc)}")

        if saved_audio_files:
            record["audio_files"] = saved_audio_files
        if recording_errors:
            record["session_recording_errors"] = recording_errors

        with open(day_dir / f"{session_stem}.json", "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to save session record")


def get_model() -> AutoModel:
    global _model
    if MODEL_PATH is None:
        raise RuntimeError("model path is required")
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info("Loading ASR model: %s", MODEL_PATH)
                _model = AutoModel(model=MODEL_PATH, model_type=MODEL_TYPE, vad_model=VAD_MODEL_PATH)
    return _model


async def run_model_worker(func, *args, **kwargs):
    if _model_executor is None:
        raise RuntimeError("model executor is not initialized")
    loop = asyncio.get_running_loop()
    call = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(_model_executor, call)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _generate_lock, _model_executor
    _generate_lock = asyncio.Lock()
    _model_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mano-asr-model")
    if LOAD_ON_STARTUP:
        await run_model_worker(get_model)
    try:
        yield
    finally:
        if _model_executor is not None:
            _model_executor.shutdown(wait=False, cancel_futures=True)
            _model_executor = None


app = FastAPI(title="mano-asr", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    return api_error(
        422,
        "request validation error",
        detail=json.dumps(exc.errors(), ensure_ascii=False, default=str),
        exc=exc,
        request=request,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return api_error(exc.status_code, str(exc.detail), exc=exc, request=request)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return api_error(500, "internal server error", exc=exc, request=request)


@app.get("/")
def health_check():
    return {"status": 200, "service": "mano-asr", "message": "ok"}


def require_auth(authorization: Optional[str], request: Optional[Request] = None) -> Optional[JSONResponse]:
    if not AUTH_TOKEN:
        return None
    expected = f"Bearer {AUTH_TOKEN}"
    if authorization != expected:
        return api_error(401, "unauthorized", request=request)
    return None


def tail_text(value: Optional[str], limit: int) -> str:
    if not value:
        return ""
    return value[-limit:]


def build_hotword_context(
    chat_context: Optional[str],
    personal_context: Optional[str],
    member_context: Optional[str],
) -> list[str]:
    parts = []
    personal = tail_text(personal_context, PERSONAL_CONTEXT_LIMIT)
    members = tail_text(member_context, MEMBER_CONTEXT_LIMIT)
    chat = tail_text(chat_context, CHAT_CONTEXT_LIMIT)
    if personal:
        parts.append(f"<personal_context>{personal}</personal_context>")
    if members:
        parts.append(f"<member_context>{members}</member_context>")
    if chat:
        parts.append(f"<chat_context>{chat}</chat_context>")
    return ["\n".join(parts)] if parts else []


def validate_audio(audio: Optional[UploadFile], request: Optional[Request] = None) -> Optional[JSONResponse]:
    if audio is None:
        return api_error(400, "audio file is required", request=request)
    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return api_error(400, "unsupported audio file type", request=request)
    return None


async def save_upload(audio: UploadFile) -> Path:
    suffix = Path(audio.filename or "").suffix.lower()
    fd, temp_name = tempfile.mkstemp(prefix="mano_asr_", suffix=suffix)
    size = 0
    try:
        with os.fdopen(fd, "wb") as temp_file:
            while True:
                chunk = await audio.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise ValueError(f"audio file is too large, current bytes {size} constraint is {MAX_FILE_SIZE} bytes")
                temp_file.write(chunk)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
    finally:
        await audio.close()
    if size == 0:
        Path(temp_name).unlink(missing_ok=True)
        raise ValueError("audio file is empty")
    return Path(temp_name)


def probe_duration(audio_path: Path) -> Optional[float]:
    try:
        import soundfile as sf

        with sf.SoundFile(str(audio_path)) as f:
            if f.samplerate > 0:
                return len(f) / f.samplerate
    except Exception:
        pass
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def prepare_audio_for_asr(audio_path: Path) -> Path:
    if audio_path.suffix.lower() == ".wav":
        return audio_path

    fd, wav_name = tempfile.mkstemp(prefix="mano_asr_decode_", suffix=".wav")
    os.close(fd)
    wav_path = Path(wav_name)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-i", str(audio_path),
                "-ac", "1",
                "-ar", "16000",
                "-f", "wav",
                str(wav_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        wav_path.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg is required to decode this audio format") from exc
    except Exception:
        wav_path.unlink(missing_ok=True)
        raise

    if result.returncode != 0:
        wav_path.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout or "").strip()
        raise ValueError(f"failed to decode audio file: {detail}" if detail else "failed to decode audio file")
    return wav_path


def smart_join(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if left[-1] in " \t\n":
        return left + right
    a, b = left[-1], right[0]
    if a.isascii() and b.isascii() and a.isalnum() and b.isalnum():
        return f"{left} {right}"
    return left + right


def apply_mode(mode: str, context_text: str, transcript: str) -> str:
    if mode == "edit_only":
        return transcript
    if mode == "append_only" or mode == "smart":
        return smart_join(context_text, transcript)
    return transcript


@app.post("/v1/voice/transcribe")
async def transcribe_voice(
    request: Request,
    audio: Optional[UploadFile] = File(None),
    context_text: Optional[str] = Form(None),
    chat_context: Optional[str] = Form(None),
    personal_context: Optional[str] = Form(None),
    member_context: Optional[str] = Form(None),
    mode: str = Form("smart"),
    authorization: Optional[str] = Header(None),
):
    started_at = time.time()
    request_info: dict[str, Any] = {
        "audio_filename": audio.filename if audio is not None else None,
        "audio_content_type": audio.content_type if audio is not None else None,
        "context_text_len": len(context_text) if context_text else 0,
        "context_text": tail_text(context_text, CONTEXT_TEXT_LIMIT),
        "chat_context_len": len(chat_context) if chat_context else 0,
        "chat_context": tail_text(chat_context, CHAT_CONTEXT_LIMIT),
        "personal_context_len": len(personal_context) if personal_context else 0,
        "personal_context": tail_text(personal_context, PERSONAL_CONTEXT_LIMIT),
        "member_context_len": len(member_context) if member_context else 0,
        "member_context": tail_text(member_context, MEMBER_CONTEXT_LIMIT),
        "mode": mode,
    }
    extras: dict[str, Any] = {}
    audio_path: Optional[Path] = None
    asr_audio_path: Optional[Path] = None

    async def finalize(response):
        audio_files = []
        if audio_path is not None:
            audio_files.append({
                "role": "original",
                "source_path": str(audio_path),
                "original_filename": audio.filename if audio is not None else None,
                "content_type": audio.content_type if audio is not None else None,
            })
        if asr_audio_path is not None and asr_audio_path != audio_path:
            audio_files.append({
                "role": "asr_input",
                "source_path": str(asr_audio_path),
                "original_filename": f"{Path(audio.filename).stem}.wav" if audio and audio.filename else None,
                "content_type": "audio/wav",
            })

        record: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "elapsed_ms": int((time.time() - started_at) * 1000),
            "request": request_info,
            **extras,
        }
        if audio_files:
            record["_audio_files"] = audio_files
        if isinstance(response, JSONResponse):
            try:
                body = json.loads(response.body.decode("utf-8"))
            except Exception:
                body = None
            record["response"] = {"status_code": response.status_code, "body": body}
        else:
            record["response"] = response
        await asyncio.to_thread(save_session, record)
        return response

    auth_error = require_auth(authorization, request=request)
    if auth_error is not None:
        return await finalize(auth_error)

    if mode not in ALLOWED_MODES:
        return await finalize(api_error(400, "invalid mode", request=request))

    audio_error = validate_audio(audio, request=request)
    if audio_error is not None:
        return await finalize(audio_error)

    context_text = tail_text(context_text, CONTEXT_TEXT_LIMIT)
    if mode == "edit_only" and not context_text:
        return await finalize(api_error(400, "context_text is required for edit_only mode", request=request))

    try:
        audio_path = await save_upload(audio)
        extras["audio_size"] = audio_path.stat().st_size
    except ValueError as exc:
        return await finalize(api_error(400, str(exc), exc=exc, request=request))
    except Exception as exc:
        return await finalize(api_error(500, "failed to read audio file", exc=exc, request=request))

    try:
        duration = await asyncio.to_thread(probe_duration, audio_path)
        if duration is None:
            logger.warning("Could not probe audio duration for %s", audio_path)
        else:
            extras["audio_duration"] = round(duration, 3)
            if duration > MAX_DURATION:
                return await finalize(
                    api_error(400, f"audio duration {duration} exceeds {MAX_DURATION}s limit", request=request)
                )

        try:
            asr_audio_path = await asyncio.to_thread(prepare_audio_for_asr, audio_path)
            if asr_audio_path != audio_path:
                extras["decoded_audio_size"] = asr_audio_path.stat().st_size
        except ValueError as exc:
            return await finalize(api_error(400, str(exc), exc=exc, request=request))
        except RuntimeError as exc:
            return await finalize(api_error(500, str(exc), exc=exc, request=request))

        # hotwords = build_hotword_context(chat_context, personal_context, member_context)
        hotwords = extract_hotwords_from_context(personal_context)
        hotwords = ['@'] + hotwords[:100]
        
        assert _generate_lock is not None
        async with _generate_lock:
            model = await run_model_worker(get_model)
            transcript = await run_model_worker(
                model.generate,
                asr_audio_path,
                # hotwords=hotwords,
                task="transcribe",
                target_language="auto",  # zh
                formal=True,
                merge_vad=True,
        )

        for _src, _dst in TRANSCRIPT_REPLACEMENTS.items():
            transcript = transcript.replace(_src, _dst)
        extras["transcript"] = transcript

        audio_duration = extras.get("audio_duration")
        if not isinstance(audio_duration, (int, float)):
            audio_duration = None
        if has_repetition(transcript, audio_duration=audio_duration):
            repetition_check = check_repetition(transcript, audio_duration=audio_duration)
            extras["repetition_detected"] = True
            extras["repetition_check"] = repetition_check
            return await finalize(
                api_error(
                    500,
                    "model recognition error",
                    detail=repetition_check.get("reason") or "abnormal repetition detected in transcript",
                    request=request,
                )
            )
        extras["repetition_detected"] = False

        elapsed_ms = int((time.time() - started_at) * 1000)
        if DEBUG_MODE:
            logger.info(
                "Transcribe OK elapsed_ms=%d audio=%s duration=%.1fs text=%s",
                elapsed_ms,
                audio.filename if audio else "unknown",
                extras.get("audio_duration", 0),
                transcript[:100] + "..." if len(transcript) > 100 else transcript,
            )
        else:
            logger.info(
                "Transcribe OK elapsed_ms=%d audio=%s duration=%.1fs",
                elapsed_ms,
                audio.filename if audio else "unknown",
                extras.get("audio_duration", 0),
            )
        return await finalize({
            "status": 200,
            "text": apply_mode(mode, context_text, transcript),
            "m": MODEL_NAME,
            "engine": ENGINE_NAME,
        })
    except Exception as exc:
        return await finalize(api_error(500, "transcription service error", exc=exc, request=request))
    finally:
        if asr_audio_path is not None and asr_audio_path != audio_path:
            asr_audio_path.unlink(missing_ok=True)
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)


@app.get("/v1/voice/config")
def voice_config():
    return {
        "enabled": True,
        "max_duration": MAX_DURATION,
        "max_file_size": MAX_FILE_SIZE,
        "engine": ENGINE_NAME,
        "edit_mode": "append",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run mano-asr voice transcription API server")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--vad-model-path", default=VAD_MODEL_PATH)
    parser.add_argument("--max-file-size", type=int, default=MAX_FILE_SIZE)
    parser.add_argument("--max-duration", type=int, default=MAX_DURATION)
    parser.add_argument("--response-model", default=MODEL_NAME)
    parser.add_argument("--model-type", default=MODEL_TYPE, choices=["auto", "funasr", "qwen3_asr"],
                        help="ASR backend type (default: auto-detect from model config.json)")
    parser.add_argument("--engine", default=ENGINE_NAME)
    parser.add_argument("--auth-token", default=AUTH_TOKEN)
    parser.add_argument("--load-on-startup", action=argparse.BooleanOptionalAction, default=LOAD_ON_STARTUP)
    parser.add_argument("--debug", action="store_true", default=DEBUG_MODE, help="启用调试模式，记录详细日志")
    return parser.parse_args()


def configure_runtime(args: argparse.Namespace) -> None:
    global MODEL_PATH, VAD_MODEL_PATH, MAX_FILE_SIZE, MAX_DURATION, MODEL_NAME, MODEL_TYPE, ENGINE_NAME
    global AUTH_TOKEN, HOST, PORT, LOAD_ON_STARTUP, DEBUG_MODE
    MODEL_PATH = args.model_path
    VAD_MODEL_PATH = args.vad_model_path or None
    MAX_FILE_SIZE = args.max_file_size
    MAX_DURATION = args.max_duration
    MODEL_NAME = args.response_model
    MODEL_TYPE = args.model_type
    ENGINE_NAME = args.engine
    AUTH_TOKEN = args.auth_token
    HOST = args.host
    PORT = args.port
    LOAD_ON_STARTUP = args.load_on_startup
    DEBUG_MODE = args.debug


def main() -> None:
    args = parse_args()
    configure_runtime(args)

    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
