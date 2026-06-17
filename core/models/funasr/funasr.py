# Copyright © 2025 FunASR (original model implementation)
# Copyright © Anthony DePasquale (MLX port)
# Ported to MLX from https://github.com/modelscope/FunASR
# License: licenses/funasr.txt

"""
Fun-ASR-Nano model implementation for MLX.

This is the main model class that integrates:
- Audio frontend (mel spectrogram + LFR)
- SenseVoice encoder (SANM-based)
- Audio adaptor (projects to LLM space)
- Qwen3 LLM decoder
"""

import glob
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Generator, List, Optional, Tuple, Union

import mlx.core as mx
import mlx.nn as nn
import numpy as np

from mlx_audio.stt.utils import get_model_path, load_audio

from .adaptor import AudioAdaptor, AudioAdaptorConfig
from .audio import LFR_M, LFR_N, N_MELS, SAMPLE_RATE, preprocess_audio
from .encoder import SenseVoiceEncoder, SenseVoiceEncoderConfig
from .qwen3 import Qwen3Config, Qwen3ForCausalLM


@dataclass
class STTOutput:
    """Output from speech-to-text generation."""

    text: str
    segments: List[dict] = None
    language: str = None
    task: str = None
    duration: float = None
    tokens: List[int] = None


# Supported languages for Fun-ASR (based on Qwen3's multilingual capabilities)
SUPPORTED_LANGUAGES = {
    "en": "English",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "th": "Thai",
    "vi": "Vietnamese",
    "auto": "Auto-detect",
}

# Task types
TASK_TRANSCRIBE = "transcribe"
TASK_TRANSLATE = "translate"


@dataclass
class FunASRConfig:
    """Configuration for Fun-ASR model."""

    # Audio processing
    sample_rate: int = 16000
    n_mels: int = 80
    lfr_m: int = 7
    lfr_n: int = 6
    use_low_frame_rate: bool = True

    # Encoder config
    encoder: SenseVoiceEncoderConfig = field(
        default_factory=lambda: SenseVoiceEncoderConfig()
    )

    # Adaptor config
    adaptor: AudioAdaptorConfig = field(default_factory=lambda: AudioAdaptorConfig())

    # LLM config
    llm: Qwen3Config = field(default_factory=lambda: Qwen3Config())

    # Special tokens
    sos_token: str = "<|startofspeech|>"
    eos_token: str = "<|endofspeech|>"
    im_start_token: str = "<|im_start|>"
    im_end_token: str = "<|im_end|>"

    # Generation defaults
    max_tokens: int = 512
    temperature: float = 0.0

    @classmethod
    def from_dict(cls, config_dict: dict) -> "FunASRConfig":
        """Create config from dictionary."""
        encoder_config = SenseVoiceEncoderConfig(
            input_dim=config_dict.get("encoder", {}).get("input_dim", 560),
            encoder_dim=config_dict.get("encoder", {}).get("encoder_dim", 512),
            num_heads=config_dict.get("encoder", {}).get("num_heads", 4),
            ffn_dim=config_dict.get("encoder", {}).get("ffn_dim", 2048),
            kernel_size=config_dict.get("encoder", {}).get("kernel_size", 11),
            num_encoders0=config_dict.get("encoder", {}).get("num_encoders0", 1),
            num_encoders=config_dict.get("encoder", {}).get("num_encoders", 49),
            num_tp_encoders=config_dict.get("encoder", {}).get("num_tp_encoders", 20),
            dropout=config_dict.get("encoder", {}).get("dropout", 0.0),
        )

        adaptor_config = AudioAdaptorConfig(
            downsample_rate=config_dict.get("adaptor", {}).get("downsample_rate", 2),
            encoder_dim=config_dict.get("adaptor", {}).get("encoder_dim", 512),
            llm_dim=config_dict.get("adaptor", {}).get("llm_dim", 1024),
            ffn_dim=config_dict.get("adaptor", {}).get("ffn_dim", 2048),
            n_layer=config_dict.get("adaptor", {}).get("n_layer", 2),
            attention_heads=config_dict.get("adaptor", {}).get("attention_heads", 8),
            dropout=config_dict.get("adaptor", {}).get("dropout", 0.0),
        )

        llm_config = Qwen3Config(
            vocab_size=config_dict.get("llm", {}).get("vocab_size", 151936),
            hidden_size=config_dict.get("llm", {}).get("hidden_size", 1024),
            num_hidden_layers=config_dict.get("llm", {}).get("num_hidden_layers", 28),
            num_attention_heads=config_dict.get("llm", {}).get(
                "num_attention_heads", 16
            ),
            num_key_value_heads=config_dict.get("llm", {}).get(
                "num_key_value_heads", 8
            ),
            intermediate_size=config_dict.get("llm", {}).get("intermediate_size", 3072),
            max_position_embeddings=config_dict.get("llm", {}).get(
                "max_position_embeddings", 40960
            ),
            rope_theta=config_dict.get("llm", {}).get("rope_theta", 1000000.0),
            rms_norm_eps=config_dict.get("llm", {}).get("rms_norm_eps", 1e-6),
            tie_word_embeddings=config_dict.get("llm", {}).get(
                "tie_word_embeddings", True
            ),
            head_dim=config_dict.get("llm", {}).get("head_dim", 64),
        )

        return cls(
            sample_rate=config_dict.get("sample_rate", 16000),
            n_mels=config_dict.get("n_mels", 80),
            lfr_m=config_dict.get("lfr_m", 7),
            lfr_n=config_dict.get("lfr_n", 6),
            use_low_frame_rate=config_dict.get(
                "use_low_frame_rate",
                config_dict.get("adaptor", {}).get("use_low_frame_rate", True),
            ),
            encoder=encoder_config,
            adaptor=adaptor_config,
            llm=llm_config,
            sos_token=config_dict.get("sos_token", "<|startofspeech|>"),
            eos_token=config_dict.get("eos_token", "<|endofspeech|>"),
            im_start_token=config_dict.get("im_start_token", "<|im_start|>"),
            im_end_token=config_dict.get("im_end_token", "<|im_end|>"),
            max_tokens=config_dict.get("max_tokens", 512),
            temperature=config_dict.get("temperature", 0.0),
        )


class Model(nn.Module):
    """
    Fun-ASR-Nano main model.

    Combines audio encoder, adaptor, and LLM decoder for end-to-end
    speech recognition.
    """

    def __init__(self, config: FunASRConfig):
        super().__init__()
        self.config = config

        # Audio encoder
        self.audio_encoder = SenseVoiceEncoder(config.encoder)

        # Audio adaptor
        self.audio_adaptor = AudioAdaptor(config.adaptor)

        # LLM decoder
        self.llm = Qwen3ForCausalLM(config.llm)

        # Tokenizer (will be set during loading)
        self._tokenizer = None

        # Special token IDs (will be set during loading)
        self._sos_token_id = None
        self._eos_token_id = None
        self._eos_token_ids = None

    @staticmethod
    def _low_frame_audio_token_len(frame_len: int) -> int:
        """
        Match the original FunASR Nano fake_token_len calculation.

        The adaptor still emits one vector per frontend frame, but the LLM
        prompt consumes the low-frame-rate token count derived here.
        """
        olens = 1 + (frame_len - 3 + 2 * 1) // 2
        olens = 1 + (olens - 3 + 2 * 1) // 2
        return (olens - 1) // 2 + 1

    def encode_audio(
        self,
        audio: Union[str, np.ndarray, mx.array],
    ) -> mx.array:
        """
        Encode audio to embeddings.

        Parameters
        ----------
        audio : Union[str, np.ndarray, mx.array]
            Audio input (path or waveform)

        Returns
        -------
        mx.array
            Audio embeddings projected to LLM space
        """
        # Preprocess audio
        features = preprocess_audio(
            audio,
            n_mels=self.config.n_mels,
            lfr_m=self.config.lfr_m,
            lfr_n=self.config.lfr_n,
        )

        # Add batch dimension
        if features.ndim == 2:
            features = features[None, ...]

        # Encode
        encoder_out, lengths = self.audio_encoder(features)

        # Adapt to LLM space (adaptor returns tuple of (embeddings, lengths))
        adapted, _ = self.audio_adaptor(encoder_out, lengths)

        if self.config.use_low_frame_rate:
            audio_token_len = self._low_frame_audio_token_len(features.shape[1])
            adapted = adapted[:, : min(audio_token_len, adapted.shape[1]), :]

        return adapted

    @staticmethod
    def _find_token_sequence(ids: List[int], pattern: List[int], start: int = 0) -> int:
        """Return the first index of a token subsequence, or -1 if absent."""
        if not pattern:
            return -1
        last = len(ids) - len(pattern)
        for pos in range(start, last + 1):
            if ids[pos : pos + len(pattern)] == pattern:
                return pos
        return -1

    def _merge_embeddings(
        self,
        input_ids: mx.array,
        audio_embeddings: mx.array,
    ) -> mx.array:
        """
        Merge audio embeddings with text embeddings.

        The audio embeddings replace the speech token placeholder region.

        Parameters
        ----------
        input_ids : mx.array
            Token IDs with speech placeholders
        audio_embeddings : mx.array
            Encoded audio embeddings

        Returns
        -------
        mx.array
            Combined embeddings
        """
        # Get text embeddings
        text_embeddings = self.llm.get_input_embeddings()(input_ids)

        # Speech markers are multi-token strings with the Qwen tokenizer, so
        # locate the full token sequences instead of matching only the first id.
        speech_placeholder_ids = self._speech_placeholder_token_ids
        speech_start_ids = self._speech_start_token_ids
        speech_end_ids = self._speech_end_token_ids
        if not speech_placeholder_ids and (not speech_start_ids or not speech_end_ids):
            raise ValueError("Speech marker token sequences are not initialized")

        batch_size = input_ids.shape[0]
        all_embeddings = []

        for b in range(batch_size):
            ids = input_ids[b]
            ids_list = [int(x) for x in ids.tolist()]
            text_emb = text_embeddings[b]
            audio_emb = (
                audio_embeddings[b] if audio_embeddings.ndim == 3 else audio_embeddings
            )

            speech_start = self._find_token_sequence(ids_list, speech_placeholder_ids)
            if speech_start >= 0:
                text_after = speech_start + len(speech_placeholder_ids)
            else:
                speech_start = self._find_token_sequence(ids_list, speech_start_ids)
                speech_end = self._find_token_sequence(
                    ids_list, speech_end_ids, speech_start + len(speech_start_ids)
                )
                if speech_start < 0 or speech_end < 0:
                    raise ValueError(
                        "Could not find complete speech marker token sequences in prompt"
                    )
                text_after = speech_end + len(speech_end_ids)

            # Build merged embeddings
            # [text_before_marker, audio_emb, text_after_marker]
            parts = []

            if speech_start > 0:
                parts.append(text_emb[:speech_start])

            parts.append(audio_emb)

            if text_after < text_emb.shape[0]:
                parts.append(text_emb[text_after:])

            merged = mx.concatenate(parts, axis=0)
            all_embeddings.append(merged)

        # Pad to same length
        max_len = max(e.shape[0] for e in all_embeddings)
        padded = []
        for emb in all_embeddings:
            if emb.shape[0] < max_len:
                padding = mx.zeros((max_len - emb.shape[0], emb.shape[1]))
                emb = mx.concatenate([emb, padding], axis=0)
            padded.append(emb)

        return mx.stack(padded, axis=0)

    def _merge_prompt_parts(
        self,
        prompt_before_audio: str,
        prompt_after_audio: str,
        audio_embeddings: mx.array,
    ) -> mx.array:
        """
        Merge prompt text and audio embeddings without searching marker tokens.

        Tokenizers can merge marker boundary text such as
        "：<|startofspeech|>", so callers that already know the marker span
        should tokenize the text before and after the marker separately.
        """
        before_ids = self._tokenizer.encode(prompt_before_audio)
        after_ids = self._tokenizer.encode(prompt_after_audio)
        before_emb = self.llm.get_input_embeddings()(mx.array([before_ids]))[0]
        after_emb = self.llm.get_input_embeddings()(mx.array([after_ids]))[0]
        audio_emb = audio_embeddings[0] if audio_embeddings.ndim == 3 else audio_embeddings

        parts = []
        if before_emb.shape[0] > 0:
            parts.append(before_emb)
        parts.append(audio_emb)
        if after_emb.shape[0] > 0:
            parts.append(after_emb)
        return mx.stack([mx.concatenate(parts, axis=0)], axis=0)

    def _build_system_prompt(
        self,
        task: str = TASK_TRANSCRIBE,
        language: str = "auto",
        target_language: str = "en",
        initial_prompt: Optional[str] = None,
    ) -> str:
        """
        Build the system prompt based on task and language settings.

        Parameters
        ----------
        task : str
            Task type: "transcribe" or "translate"
        language : str
            Source language (or "auto" for detection)
        target_language : str
            Target language for translation
        initial_prompt : str, optional
            Custom instructions to prepend

        Returns
        -------
        str
            System prompt for the LLM
        """
        if task == TASK_TRANSLATE:
            target_lang_name = SUPPORTED_LANGUAGES.get(target_language, target_language)
            if language == "auto":
                base_prompt = f"You are a speech translation assistant. Listen to the audio and translate the speech into {target_lang_name}. Output only the translation, nothing else."
            else:
                source_lang_name = SUPPORTED_LANGUAGES.get(language, language)
                base_prompt = f"You are a speech translation assistant. The audio is in {source_lang_name}. Translate it into {target_lang_name}. Output only the translation, nothing else."
        else:  # transcribe
            if language == "auto":
                base_prompt = "You are a speech recognition assistant. Transcribe the audio accurately. Output only the transcription, nothing else."
            else:
                lang_name = SUPPORTED_LANGUAGES.get(language, language)
                base_prompt = f"You are a speech recognition assistant. The audio is in {lang_name}. Transcribe it accurately. Output only the transcription, nothing else."

        if initial_prompt:
            return f"{initial_prompt}\n\n{base_prompt}"
        return base_prompt

    def _prepare_prompt(
        self,
        audio_embeddings: mx.array,
        language: str = "auto",
        task: str = TASK_TRANSCRIBE,
        target_language: str = "en",
        initial_prompt: Optional[str] = None,
        formal: bool = False,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> mx.array:
        """
        Prepare input embeddings with prompt template.

        Parameters
        ----------
        audio_embeddings : mx.array
            Encoded audio embeddings
        language : str
            Source language for transcription (or "auto" for detection)
        task : str
            Task type: "transcribe" or "translate"
        target_language : str
            Target language for translation (default: "en")
        initial_prompt : str, optional
            Custom instructions or context to include

        Returns
        -------
        mx.array
            Input embeddings for generation
        """
        
        if task == TASK_TRANSCRIBE:
            if language in ("zh", "中文", "Chinese"):
                transcribe_prompt = "语音转写成中文"
            elif language == "auto":
                transcribe_prompt = "语音转写"
            else:
                lang_name = SUPPORTED_LANGUAGES.get(language, language)
                transcribe_prompt = f"语音转写成{lang_name}"
            # if formal:
            #     transcribe_prompt += "，实现口语转书面语，转写结果需要结构化表达、去除口语冗余，并在保留原始语气和情绪的前提下输出可直接用于书面文档的规范文字"
            transcribe_prompt += "："
            if user_prompt is not None:
                transcribe_prompt = user_prompt

            if initial_prompt:
                transcribe_prompt = f"{initial_prompt}\n{transcribe_prompt}"
            
            system_prompt = system_prompt if system_prompt is not None else 'You are a helpful assistant.'

            prompt_before_audio = (
                f"{self.config.im_start_token}system\n"
                f"{system_prompt}{self.config.im_end_token}\n"
                f"{self.config.im_start_token}user\n"
                f"{transcribe_prompt}"
            )
            
            prompt_after_audio = (
                f"{self.config.im_end_token}\n"
                f"{self.config.im_start_token}assistant\n"
            )
            return self._merge_prompt_parts(
                prompt_before_audio, prompt_after_audio, audio_embeddings
            )

        system_prompt = self._build_system_prompt(
            task=task,
            language=language,
            target_language=target_language,
            initial_prompt=initial_prompt,
        )
        prompt_before_audio = (
            f"{self.config.im_start_token}system\n"
            f"{system_prompt}{self.config.im_end_token}\n"
            f"{self.config.im_start_token}user\n"
        )
        prompt_after_audio = (
            f"{self.config.im_end_token}\n"
            f"{self.config.im_start_token}assistant\n"
        )
        return self._merge_prompt_parts(
            prompt_before_audio, prompt_after_audio, audio_embeddings
        )

    def _sample_next_token(
        self,
        logits: mx.array,
        temperature: float = 0.0,
        top_p: float = 0.95,
        top_k: int = 0,
    ) -> mx.array:
        """
        Sample next token from logits.

        Parameters
        ----------
        logits : mx.array
            Logits from the model
        temperature : float
            Sampling temperature (0 for greedy)
        top_p : float
            Top-p (nucleus) sampling threshold
        top_k : int
            Top-k sampling (0 to disable)

        Returns
        -------
        mx.array
            Sampled token ID
        """
        # Get logits for last position
        logits = logits[:, -1, :]

        if temperature == 0:
            # Greedy decoding
            return mx.argmax(logits, axis=-1)

        # Apply temperature
        logits = logits / temperature

        # Apply top-k
        if top_k > 0:
            top_k_logits, top_k_indices = mx.topk(logits, k=top_k)
            logits = mx.full_like(logits, float("-inf"))
            logits = logits.at[..., top_k_indices].set(top_k_logits)

        # Apply top-p (nucleus sampling)
        if top_p < 1.0:
            sorted_logits = mx.sort(logits, axis=-1)[:, ::-1]
            sorted_indices = mx.argsort(logits, axis=-1)[:, ::-1]
            cumulative_probs = mx.cumsum(mx.softmax(sorted_logits, axis=-1), axis=-1)

            # Remove tokens with cumulative probability above threshold
            sorted_indices_to_remove = cumulative_probs > top_p
            # Shift to keep at least one token
            sorted_indices_to_remove = mx.concatenate(
                [
                    mx.zeros((logits.shape[0], 1), dtype=mx.bool_),
                    sorted_indices_to_remove[:, :-1],
                ],
                axis=-1,
            )

            for b in range(logits.shape[0]):
                indices_to_remove = sorted_indices[b][sorted_indices_to_remove[b]]
                logits = logits.at[b, indices_to_remove].set(float("-inf"))

        # Sample
        probs = mx.softmax(logits, axis=-1)
        token = mx.random.categorical(mx.log(probs + 1e-10))

        return token

    def stream_generate(
        self,
        audio: Union[str, np.ndarray, mx.array],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        top_p: float = 0.95,
        top_k: int = 0,
        language: str = "auto",
        task: str = TASK_TRANSCRIBE,
        target_language: str = "en",
        initial_prompt: Optional[str] = None,
        formal: bool = False,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> Generator[Tuple[int, mx.array], None, None]:
        """
        Stream tokens during generation.

        Parameters
        ----------
        audio : Union[str, np.ndarray, mx.array]
            Audio input
        max_tokens : int
            Maximum tokens to generate
        temperature : float
            Sampling temperature
        top_p : float
            Top-p sampling threshold
        top_k : int
            Top-k sampling
        language : str
            Source language (or "auto" for detection)
        task : str
            Task type: "transcribe" or "translate"
        target_language : str
            Target language for translation
        initial_prompt : str, optional
            Custom instructions or context

        Yields
        ------
        Tuple[int, mx.array]
            Token ID and logits
        """

        # Encode audio
        audio_embeddings = self.encode_audio(audio)

        # Prepare initial embeddings with task-specific prompt
        input_embeddings = self._prepare_prompt(
            audio_embeddings,
            language=language,
            task=task,
            target_language=target_language,
            initial_prompt=initial_prompt,
            formal=formal,
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

        # Initialize cache
        cache = None

        # Compute first step (prefill)
        logits, cache = self.llm(
            input_embeddings=input_embeddings,
            cache=cache,
        )
        mx.async_eval(logits, cache)

        # Generate tokens
        for _ in range(max_tokens):
            # Sample current token
            token = self._sample_next_token(logits, temperature, top_p, top_k)

            # Prepare next input and start computing ahead (before extracting token ID)
            input_embeddings = self.llm.get_input_embeddings()(token.reshape(1, 1))
            logits, cache = self.llm(
                input_embeddings=input_embeddings,
                cache=cache,
            )

            # Pipeline: evaluate async while preparing next iteration
            mx.async_eval(logits, cache)

            # NOW extract token ID - GPU is already computing next step
            token_id = token.item()

            # Check for EOS
            if token_id in self._eos_token_ids:
                break

            yield token_id, logits

    def generate(
        self,
        audio: Union[str, np.ndarray, mx.array, Path],
        *,
        max_tokens: int = None,
        temperature: float = None,
        top_p: float = 0.95,
        top_k: int = 0,
        language: str = "auto",
        task: str = TASK_TRANSCRIBE,
        target_language: str = "en",
        initial_prompt: Optional[str] = None,
        verbose: bool = False,
        stream: bool = False,
        formal: bool = False,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        **kwargs,
    ) -> Union[STTOutput, Generator[str, None, STTOutput]]:
        """
        Generate transcription or translation from audio.

        This is an LLM-based speech recognition model that supports:
        - Transcription in multiple languages
        - Translation to a target language
        - Custom prompting for specialized tasks

        Parameters
        ----------
        audio : Union[str, np.ndarray, mx.array, Path]
            Audio input (file path or waveform)
        max_tokens : int, optional
            Maximum tokens to generate (default: from config)
        temperature : float, optional
            Sampling temperature, 0 for greedy (default: from config)
        top_p : float
            Top-p (nucleus) sampling threshold
        top_k : int
            Top-k sampling (0 to disable)
        language : str
            Source language code (e.g., "en", "zh", "ja") or "auto" for detection.
            Supported: en, zh, ja, ko, es, fr, de, it, pt, ru, ar, th, vi
        task : str
            Task type: "transcribe" (default) or "translate"
        target_language : str
            Target language for translation (default: "en")
        initial_prompt : str, optional
            Custom instructions or context to guide the model.
            Example: "This is a medical consultation." or "Technical vocabulary: API, SDK"
        verbose : bool
            Print tokens as they're generated
        stream : bool
            If True, return a generator yielding text chunks instead of waiting
            for complete output

        Returns
        -------
        STTOutput or Generator
            If stream=False: STTOutput with text, language, task, and tokens
            If stream=True: Generator yielding text chunks, final yield is STTOutput

        Examples
        --------
        Basic transcription:
            >>> result = model.generate("audio.wav")
            >>> print(result.text)

        Translation to English:
            >>> result = model.generate("chinese_audio.wav", task="translate")
            >>> print(result.text)

        With custom context:
            >>> result = model.generate(
            ...     "meeting.wav",
            ...     initial_prompt="Meeting participants: Alice, Bob. Topic: Q4 planning."
            ... )

        Streaming output:
            >>> for chunk in model.generate("audio.wav", stream=True, verbose=True):
            ...     pass  # chunks printed automatically when verbose=True
        """
        import time

        # Use config defaults if not specified
        if max_tokens is None:
            max_tokens = self.config.max_tokens
        if temperature is None:
            temperature = self.config.temperature

        # Handle Path objects
        if isinstance(audio, Path):
            audio = str(audio)

        # Track timing
        start_time = time.time()

        if stream:
            return self._generate_stream(
                audio=audio,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                language=language,
                task=task,
                target_language=target_language,
                initial_prompt=initial_prompt,
                verbose=verbose,
                formal=formal,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

        # Generate tokens
        tokens = []
        for token_id, _ in self.stream_generate(
            audio,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            language=language,
            task=task,
            target_language=target_language,
            initial_prompt=initial_prompt,
            formal=formal,
            system_prompt=system_prompt,
            user_prompt=user_prompt
        ):
            tokens.append(token_id)
            if verbose:
                print(self._tokenizer.decode([token_id]), end="", flush=True)

        if verbose:
            print()

        # Calculate duration
        duration = time.time() - start_time

        # Decode tokens
        text = self._tokenizer.decode(tokens)

        # Clean up text (remove thinking tokens, etc.)
        text = self._clean_output(text)

        # Determine detected language (for "auto" mode, we infer from output)
        detected_language = (
            language if language != "auto" else self._detect_language_from_text(text)
        )

        # Clear memory
        mx.clear_cache()

        return STTOutput(
            text=text,
            language=detected_language,
            task=task,
            duration=duration,
            tokens=tokens,
            segments=None,  # LLM-based model doesn't produce word-level timestamps
        )

    def _generate_stream(
        self,
        audio: Union[str, np.ndarray, mx.array],
        max_tokens: int,
        temperature: float,
        top_p: float,
        top_k: int,
        language: str,
        task: str,
        target_language: str,
        initial_prompt: Optional[str],
        verbose: bool,
        formal: bool = False,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> Generator[str, None, STTOutput]:
        """Internal streaming generator."""
        import time

        start_time = time.time()
        tokens = []
        buffer = ""

        for token_id, _ in self.stream_generate(
            audio,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            language=language,
            task=task,
            target_language=target_language,
            initial_prompt=initial_prompt,
            formal=formal,
            system_prompt=system_prompt,
            user_prompt=user_prompt
        ):
            tokens.append(token_id)
            chunk = self._tokenizer.decode([token_id])
            buffer += chunk

            if verbose:
                print(chunk, end="", flush=True)

            yield chunk

        if verbose:
            print()

        duration = time.time() - start_time
        text = self._clean_output(self._tokenizer.decode(tokens))
        detected_language = (
            language if language != "auto" else self._detect_language_from_text(text)
        )

        mx.clear_cache()

        # Final yield is the complete output
        return STTOutput(
            text=text,
            language=detected_language,
            task=task,
            duration=duration,
            tokens=tokens,
            segments=None,
        )

    def _detect_language_from_text(self, text: str) -> str:
        """
        Simple heuristic to detect language from output text.

        For more accurate detection, consider using a dedicated language
        detection library.
        """
        if not text:
            return "unknown"

        # Simple character-based heuristics
        # Check for CJK characters
        cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        japanese_count = sum(1 for c in text if "\u3040" <= c <= "\u30ff")
        korean_count = sum(1 for c in text if "\uac00" <= c <= "\ud7af")
        arabic_count = sum(1 for c in text if "\u0600" <= c <= "\u06ff")
        thai_count = sum(1 for c in text if "\u0e00" <= c <= "\u0e7f")
        cyrillic_count = sum(1 for c in text if "\u0400" <= c <= "\u04ff")

        total = len(text)
        if total == 0:
            return "unknown"

        # Determine language based on script
        if japanese_count / total > 0.1:
            return "ja"
        if korean_count / total > 0.1:
            return "ko"
        if cjk_count / total > 0.2:
            return "zh"
        if arabic_count / total > 0.2:
            return "ar"
        if thai_count / total > 0.2:
            return "th"
        if cyrillic_count / total > 0.2:
            return "ru"

        # Default to English for Latin script
        return "en"

    def _clean_output(self, text: str) -> str:
        """
        Clean up generated text.

        Removes thinking blocks and other artifacts.

        Parameters
        ----------
        text : str
            Raw generated text

        Returns
        -------
        str
            Cleaned text
        """
        import re

        # Remove thinking blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

        # Remove special tokens
        special_tokens = [
            self.config.im_start_token,
            self.config.im_end_token,
            self.config.sos_token,
            self.config.eos_token,
            "<|endoftext|>",
        ]
        for token in special_tokens:
            text = text.replace(token, "")

        return text.strip()

    def sanitize(self, weights: Dict) -> Dict:
        """
        Sanitize weights for loading.

        Handles Conv1d weight transposition and key remapping.

        Parameters
        ----------
        weights : Dict
            Raw weights dictionary

        Returns
        -------
        Dict
            Sanitized weights
        """
        sanitized = {}
        for k, v in weights.items():
            # Handle FSMN conv weights (PyTorch: [out, 1, kernel] -> MLX: [out, kernel, 1])
            if "fsmn_block" in k and "conv.weight" in k:
                # Check if transposition is needed
                if v.ndim == 3 and v.shape[1] == 1:
                    v = v.squeeze(1)[..., None]
            # Handle other conv weights
            elif "conv" in k and "weight" in k:
                if v.ndim == 3:
                    # Check shape to determine if transposition needed
                    if v.shape[-1] < v.shape[-2]:
                        v = v.swapaxes(-1, -2)

            sanitized[k] = v

        return sanitized

    @classmethod
    def from_pretrained(
        cls,
        path_or_hf_repo: str,
        *,
        dtype: mx.Dtype = mx.bfloat16,
        **kwargs,
    ) -> "Model":
        """
        Load model from pretrained weights.

        Parameters
        ----------
        path_or_hf_repo : str
            Local path or HuggingFace repository ID
        dtype : mx.Dtype
            Data type for model weights

        Returns
        -------
        Model
            Loaded model
        """
        from transformers import AutoTokenizer

        # Get model path
        revision = kwargs.get("revision", None)
        force_download = kwargs.get("force_download", False)
        model_path = get_model_path(
            path_or_hf_repo, revision=revision, force_download=force_download
        )

        # Load config
        config_path = model_path / "config.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                config_dict = json.load(f)
            config = FunASRConfig.from_dict(config_dict)
        else:
            # Use defaults
            config = FunASRConfig()

        # Create model
        model = cls(config)

        # Apply quantization if specified in config
        if "quantization" in config_dict:
            q_config = config_dict["quantization"]
            q_bits = q_config.get("bits", 4)
            q_group_size = q_config.get("group_size", 64)
            q_components = set(q_config.get("quantized_components", []))

            def class_predicate(path: str, module) -> bool:
                """Only quantize Linear layers in specified components."""
                if isinstance(module, nn.Linear):
                    for component in q_components:
                        if component in path:
                            return True
                return False

            nn.quantize(
                model,
                bits=q_bits,
                group_size=q_group_size,
                class_predicate=class_predicate,
            )

        # Load tokenizer
        try:
            model._tokenizer = AutoTokenizer.from_pretrained(
                path_or_hf_repo, trust_remote_code=True, fix_mistral_regex=True
            )
        except Exception:
            model._tokenizer = AutoTokenizer.from_pretrained(
                str(model_path), trust_remote_code=True, fix_mistral_regex=True
            )

        # Set up special tokens
        model._setup_special_tokens()

        # Load weights
        weight_files = list(model_path.glob("*.safetensors"))
        if not weight_files:
            weight_files = list(model_path.glob("*.npz"))

        weights = {}
        for wf in weight_files:
            weights.update(mx.load(str(wf)))

        # Cast to dtype (skip quantized weights which have specific dtypes)
        def should_cast(key: str, value: mx.array) -> bool:
            # Don't cast quantization scales/biases or already-quantized weights
            if key.endswith((".scales", ".biases")):
                return False
            if value.dtype == mx.uint32:  # Quantized weights
                return False
            return True

        weights = {
            k: v.astype(dtype) if should_cast(k, v) else v for k, v in weights.items()
        }

        # Load weights into model
        model.load_weights(list(weights.items()))

        model.eval()

        return model

    def _setup_special_tokens(self):
        """Set up special token IDs from tokenizer."""
        if self._tokenizer is None:
            return

        # Speech marker strings are not registered as single tokenizer tokens in
        # Qwen3, so keep their full token sequences for prompt span matching.
        try:
            self._speech_placeholder_token_ids = self._tokenizer.encode(
                self.config.sos_token + self.config.eos_token,
                add_special_tokens=False,
            )
            self._speech_start_token_ids = self._tokenizer.encode(
                self.config.sos_token, add_special_tokens=False
            )
            self._sos_token_id = (
                self._speech_start_token_ids[0]
                if len(self._speech_start_token_ids) == 1
                else None
            )
        except Exception:
            self._speech_placeholder_token_ids = []
            self._speech_start_token_ids = []
            self._sos_token_id = None

        try:
            self._speech_end_token_ids = self._tokenizer.encode(
                self.config.eos_token, add_special_tokens=False
            )
            self._eos_token_id = (
                self._speech_end_token_ids[0]
                if len(self._speech_end_token_ids) == 1
                else None
            )
        except Exception:
            self._speech_end_token_ids = []
            self._eos_token_id = None

        # Set up EOS token IDs for stopping
        self._eos_token_ids = set()
        if hasattr(self._tokenizer, "eos_token_id") and self._tokenizer.eos_token_id:
            self._eos_token_ids.add(self._tokenizer.eos_token_id)

        # Add common EOS tokens
        for token in ["<|endoftext|>", "<|im_end|>", "</s>"]:
            try:
                token_id = self._tokenizer.encode(token, add_special_tokens=False)
                if token_id:
                    self._eos_token_ids.add(token_id[0])
            except Exception:
                pass
