# coding=utf-8
"""MLX ASR transcription with optional FunASR VAD.

This wrapper supports multiple ASR backends (funasr, qwen3_asr) and
keeps only the runtime path needed by this project:

1. when ``vad_model`` is configured, run FunASR fsmn-vad and recognize each
   speech segment;
2. when ``vad_model`` is ``None``, recognize the whole audio file directly;
3. return the final text string.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import numpy as np
import mlx.core as mx

# Lazy imports — only loaded when actually needed
from utils.load_utils import load_audio
from core.models.funasr import Model as FunASRMLXModel


MODEL_REGISTRY = {
    "funasr": {
        "cls": FunASRMLXModel,
        "prompt_key": "initial_prompt",
        "supports_task": True,
        "supports_formal": True,
    },
}


ASR_GENERATE_KEYS = {
    "max_tokens",
    "temperature",
    "top_p",
    "top_k",
    "language",
    "task",
    "target_language",
    "initial_prompt",
    "system_prompt",
    "verbose",
}

CONTROL_KEYS = {
    "merge_vad",
    "merge_length_s",
    "min_segment_ms",
    "min_tail_segment_ms",
    "segment_separator",
}


class AutoModel:
    """MLX ASR with an optional FunASR VAD front-end. Supports funasr and qwen3_asr backends."""

    @staticmethod
    def _detect_model_type(model_path: str) -> Optional[str]:
        config_file = Path(model_path) / "config.json"
        if not config_file.exists():
            return None
        try:
            with open(config_file) as f:
                config = json.load(f)
            mt = config.get("model_type")
            if mt and mt in MODEL_REGISTRY:
                return mt
            thinker = config.get("thinker_config", {})
            mt = thinker.get("model_type")
            if mt and mt in MODEL_REGISTRY:
                return mt
        except Exception:
            pass
        return None

    def __init__(
        self,
        model: str,
        model_type: str = "auto",
        vad_model: Optional[str] = None,
        vad_kwargs: Optional[Dict[str, Any]] = None,
        disable_update: bool = True,
        fs: int = 16000,
        merge_vad_default: bool = False,
        merge_length_s: int = 15,
        min_segment_ms: int = 200,
        min_tail_segment_ms: int = 5000,
        enable_cider: bool = False,
        **asr_defaults: Any,
    ):
        detected = self._detect_model_type(model)
        if model_type == "auto":
            model_type = detected or "funasr"
            logging.info("Auto-detected model_type=%s from config.json", model_type)
        elif detected and detected != model_type:
            logging.info(
                "Auto-detected model_type=%s from config.json (overriding %s)",
                detected, model_type,
            )
            model_type = detected

        if model_type not in MODEL_REGISTRY:
            raise ValueError(f"Unknown model_type: {model_type!r}, choose from {list(MODEL_REGISTRY)}")

        spec = MODEL_REGISTRY[model_type]
        self._model_type = model_type
        self._prompt_key = spec["prompt_key"]
        self._supports_task = spec["supports_task"]
        self._supports_formal = spec["supports_formal"]

        self.fs = fs
        self.merge_vad_default = merge_vad_default
        self.merge_length_s = merge_length_s
        self.min_segment_ms = min_segment_ms
        self.min_tail_segment_ms = min_tail_segment_ms
        self.asr_defaults = {
            k: v for k, v in asr_defaults.items() if k in ASR_GENERATE_KEYS
        }

        logging.info("Loading %s model from %s", model_type, model)
        self.model = spec["cls"].from_pretrained(model)
        self.model_path = model

        if isinstance(vad_model, str) and vad_model.lower() in {
            "",
            "none",
            "null",
            "false",
            "no",
        }:
            vad_model = None

        self.vad_model = None
        if vad_model is not None:
            from core.models.fsmn.model import Model as FunASRAutoModel
            self.vad_model = FunASRAutoModel.from_pretrained(vad_model)
        
        if enable_cider:
            from cider import convert_model, is_available
            if is_available():
                convert_model(self.model.llm.model)

        # Speaker diarizer (lazy-init)
        self._diarizer: Optional[SpeakerDiarizer] = None

    def generate(self, input: Union[str, Path], formal=False, hotwords: Optional[List[str] | str] = None, **cfg: Any) -> str:
        """Transcribe one local audio file and return only the text."""
        mx.reset_peak_memory()
        
        if hotwords is not None and len(hotwords) > 0:
            if isinstance(hotwords, str):
                hotwords = [hotwords]
            hotwords = ", ".join(hotwords)
            context = "请结合上下文信息，更加准确地完成语音转写任务。如果没有相关信息，我们会留空。\n\n\n**上下文信息：**\n\n\n"
            if formal:
                context += f"{hotwords}\n"
            else:
                context += f"热词列表：[{hotwords}]\n"
        else:
            context = None

        audio_path = Path(input).expanduser()
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if self.vad_model is None:
            return self._recognize_file(audio_path, cfg, context=context, formal=formal)

        vad_segments = self._detect_segments(audio_path, cfg)
        if not vad_segments:
            return ""
        waveform = self._load_waveform(audio_path)

        texts = self._recognize_segments(waveform, vad_segments, cfg, context=context, formal=formal)
        separator = str(cfg.get("segment_separator", " "))
        return separator.join(texts).strip()

    transcribe = generate

    # ── Speaker diarization ─────────────────────────────────────

    def transcribe_with_diarization(
        self,
        input: Union[str, Path],
        formal=False,
        hotwords: Optional[List[str] | str] = None,
        **cfg: Any,
    ) -> Dict[str, Any]:
        """Transcribe audio and assign speaker labels to each segment.

        Requires the ``funasr`` and ``soundfile`` packages.

        Parameters
        ----------
        input : str or Path
            Path to a local audio file (WAV / MP3 / FLAC / …).
        formal : bool
            Whether to use formal ASR mode.
        hotwords : list of str or str, optional
            Hotwords / context to improve accuracy.
        **cfg
            Additional keyword arguments forwarded to the ASR pipeline.

        Returns
        -------
        dict with keys:
            - "text" : str — full concatenated transcript
            - "segments" : list of dict — per-segment details, each with
                ``start_s``, ``end_s``, ``text``, ``speaker`` (int label).
            - "num_speakers" : int
        """
        audio_path = Path(input).expanduser()
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if self.vad_model is None:
            # No VAD → transcribe whole file, no diarization
            text = self._recognize_file(audio_path, cfg, formal=formal)
            return {
                "text": text,
                "segments": [{"start_s": 0, "end_s": 0, "text": text, "speaker": 0}],
                "num_speakers": 1,
            }

        # Detect VAD segments
        vad_segments = self._detect_segments(audio_path, cfg)
        if not vad_segments:
            return {"text": "", "segments": [], "num_speakers": 0}

        waveform = self._load_waveform(audio_path)

        # Build context from hotwords
        context = self._build_context(hotwords, formal)

        # Transcribe each segment
        kwargs = self._build_generate_kwargs(cfg, context, formal=formal)
        raw_segments: List[Dict[str, Any]] = []
        min_segment_samples = max(
            int(int(cfg.get("min_segment_ms", self.min_segment_ms)) * self.fs / 1000),
            1,
        )
        for start_ms, end_ms in vad_segments:
            start = max(int(start_ms * self.fs / 1000), 0)
            end = min(int(end_ms * self.fs / 1000), len(waveform))
            if end - start < min_segment_samples:
                continue
            clip = waveform[start:end].astype(np.float32, copy=False)
            output = self.model.generate(clip, **kwargs)
            text = (getattr(output, "text", "") or "").strip()
            raw_segments.append({
                "start_s": start_ms / 1000.0,
                "end_s": end_ms / 1000.0,
                "text": text,
                "speaker": 0,
            })

        if not raw_segments:
            return {"text": "", "segments": [], "num_speakers": 0}

        # Diarization
        try:
            self._init_diarizer()
            labels, num_spk = self._diarizer.diarize(
                str(audio_path),
                vad_segments,
                audio_array=waveform,
                sample_rate=self.fs,
            )
            for idx, seg in enumerate(raw_segments):
                seg["speaker"] = labels[idx] if idx < len(labels) else 0
        except ImportError as exc:
            logging.warning("Diarization disabled: %s", exc)
            num_spk = 1
        except Exception as exc:
            logging.warning("Diarization failed (%s), using single speaker", exc)
            num_spk = 1

        # Build labeled text
        lines: List[str] = []
        current_spk = None
        for seg in raw_segments:
            if not seg["text"]:
                continue
            spk = seg["speaker"]
            if num_spk > 1 and spk != current_spk:
                lines.append(f"\n[讲话人{spk}]：{seg['text']}")
                current_spk = spk
            elif num_spk > 1:
                lines.append(seg["text"])
            else:
                lines.append(seg["text"])

        separator = str(cfg.get("segment_separator", " "))
        full_text = separator.join(lines).strip()

        return {
            "text": full_text,
            "segments": raw_segments,
            "num_speakers": num_spk,
        }

    # ── Private helpers ─────────────────────────────────────────

    def _build_context(self, hotwords, formal):
        if hotwords is not None and len(hotwords) > 0:
            if isinstance(hotwords, str):
                hotwords = [hotwords]
            hotwords = ", ".join(hotwords)
            context = (
                "请结合上下文信息，更加准确地完成语音转写任务。"
                "如果没有相关信息，我们会留空。\n\n\n**上下文信息：**\n\n\n"
            )
            if formal:
                context += f"{hotwords}\n"
            else:
                context += f"热词列表：[{hotwords}]\n"
            return context
        return None

    def _init_diarizer(self):
        if self._diarizer is None:
            from core.diarization import SpeakerDiarizer
            self._diarizer = SpeakerDiarizer()
            logging.info("Speaker diarizer initialised")

    def _build_generate_kwargs(
        self,
        cfg: Dict[str, Any],
        context: Optional[str] = None,
        formal: bool = False,
    ) -> Dict[str, Any]:
        """Build kwargs for model.generate(), adapting to the active backend."""
        kwargs = self._asr_kwargs(cfg)
        kwargs[self._prompt_key] = context
        if not self._supports_task:
            kwargs.pop("task", None)
            kwargs.pop("target_language", None)
        if self._supports_formal:
            kwargs["formal"] = formal
        return kwargs

    def _recognize_file(self, audio_path: Path, cfg: Dict[str, Any], context: Optional[str] = None, formal: bool = False) -> str:
        kwargs = self._build_generate_kwargs(cfg, context, formal=formal)
        output = self.model.generate(str(audio_path), **kwargs)
        return (getattr(output, "text", "") or "").strip()

    def _detect_segments(self, audio_path: Path, cfg: Dict[str, Any]) -> List[List[int]]:
        if self.vad_model is None:
            return []

        vad_cfg = {
            k: v
            for k, v in cfg.items()
            if k not in ASR_GENERATE_KEYS and k not in CONTROL_KEYS
        }

        result = self.vad_model.generate(str(audio_path))
        if not result:
            return []

        segments = result
        should_merge = bool(cfg.get("merge_vad", self.merge_vad_default))

        if should_merge and segments:
            merge_length_s = int(cfg.get("merge_length_s", self.merge_length_s))
            segments = self._safe_merge_vad(segments, merge_length_s * 1000)
            segments = self._merge_short_tail_segment(segments, cfg)
        return self._filter_short_segments(segments, cfg)

    def _safe_merge_vad(
        self,
        segments: Iterable[List[int]],
        max_length_ms: int,
    ) -> List[List[int]]:
        clean_segments = self._normalize_segments(segments)
        if len(clean_segments) <= 1 or max_length_ms <= 0:
            return clean_segments

        merged: List[List[int]] = []
        cur_start, cur_end = clean_segments[0]
        for start, end in clean_segments[1:]:
            if end - cur_start <= max_length_ms:
                cur_end = max(cur_end, end)
                continue

            merged.append([cur_start, cur_end])
            cur_start, cur_end = start, end

        merged.append([cur_start, cur_end])
        return merged

    def _merge_short_tail_segment(
        self,
        segments: Iterable[List[int]],
        cfg: Dict[str, Any],
    ) -> List[List[int]]:
        merged = self._normalize_segments(segments)
        min_tail_segment_ms = int(
            cfg.get("min_tail_segment_ms", self.min_tail_segment_ms)
        )
        if len(merged) < 2 or min_tail_segment_ms <= 0:
            return merged

        tail_start, tail_end = merged[-1]
        if tail_end - tail_start >= min_tail_segment_ms:
            return merged

        merged[-2][1] = max(merged[-2][1], tail_end)
        return merged[:-1]

    def _normalize_segments(self, segments: Iterable[List[int]]) -> List[List[int]]:
        normalized = []
        for segment in segments:
            if len(segment) < 2:
                continue
            start, end = int(segment[0]), int(segment[1])
            if end > start:
                normalized.append([start, end])
        return sorted(normalized, key=lambda item: item[0])

    def _filter_short_segments(
        self,
        segments: Iterable[List[int]],
        cfg: Dict[str, Any],
    ) -> List[List[int]]:
        min_segment_ms = int(cfg.get("min_segment_ms", self.min_segment_ms))
        if min_segment_ms <= 0:
            return self._normalize_segments(segments)
        return [
            [start, end]
            for start, end in self._normalize_segments(segments)
            if end - start >= min_segment_ms
        ]

    def _load_waveform(self, audio_path: Path) -> np.ndarray:
        waveform = load_audio(
            str(audio_path),
            fs=self.fs,
            audio_fs=self.fs,
        )
        if hasattr(waveform, "detach"):
            waveform = waveform.detach().cpu().numpy()
        waveform = np.asarray(waveform, dtype=np.float32).squeeze()
        if waveform.ndim != 1:
            raise ValueError(f"Expected mono waveform, got shape {waveform.shape}")
        return waveform

    def _recognize_segments(
        self,
        waveform: np.ndarray,
        vad_segments: Iterable[List[int]],
        cfg: Dict[str, Any],
        context: Optional[str] = None,
        formal: bool = False
    ) -> List[str]:
        kwargs = self._build_generate_kwargs(cfg, context, formal=formal)
        texts: List[str] = []
        min_segment_samples = max(
            int(int(cfg.get("min_segment_ms", self.min_segment_ms)) * self.fs / 1000),
            1,
        )
        
        for start_ms, end_ms in vad_segments:
            start = max(int(start_ms * self.fs / 1000), 0)
            end = min(int(end_ms * self.fs / 1000), len(waveform))
            if end - start < min_segment_samples:
                continue

            clip = waveform[start:end].astype(np.float32, copy=False)
            output = self.model.generate(clip, **kwargs)
            text = (getattr(output, "text", "") or "").strip()
            if text:
                texts.append(text)
        return texts

    def _asr_kwargs(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        asr_kwargs = dict(self.asr_defaults)
        asr_kwargs.update({k: v for k, v in cfg.items() if k in ASR_GENERATE_KEYS})
        return asr_kwargs
