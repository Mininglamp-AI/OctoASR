# coding=utf-8
"""Speaker diarization module for mano-asr.

Uses FunASR CAM++ (iic/speech_campplus_sv_zh-cn_16k-common) for speaker
embedding extraction and clustering. Integrates with the VAD-based
segmentation from AutoModel to provide sentence-level speaker labels.

Typical usage::

    from core.diarization import SpeakerDiarizer

    diarizer = SpeakerDiarizer()
    segments = [(0, 25800), (26100, 86100)]  # VAD segments in ms
    labels, num_speakers = diarizer.diarize("audio.wav", segments)
    # labels[i] = speaker_id for segments[i]
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import warnings
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: FunASR (CAM++ model)
# ---------------------------------------------------------------------------
try:

    def _get_funasr_model():
        from funasr import AutoModel

        return AutoModel(
            model="iic/speech_campplus_sv_zh-cn_16k-common",
            disable_update=True,
            log_level="ERROR",
        )

    _HAS_FUNASR = True
except ImportError:
    _HAS_FUNASR = False

    def _get_funasr_model():
        raise ImportError(
            "funasr is required for speaker diarization. "
            "Install it via: pip install funasr"
        )


# ---------------------------------------------------------------------------
# Optional dependency: soundfile (for sliding window extraction)
# ---------------------------------------------------------------------------
try:
    import soundfile as sf

    _HAS_SOUNDFILE = True
except ImportError:
    _HAS_SOUNDFILE = False


# ===================================================================
# SpeakerDiarizer
# ===================================================================


class SpeakerDiarizer:
    """Speaker diarization using CAM++ speaker embeddings + clustering.

    Parameters
    ----------
    merge_thr : float, optional
        Clustering merge threshold (default 0.70). Lower values produce
        more speaker clusters; higher values merge more segments together.
    window_s : float, optional
        Sliding window duration in seconds (default 3.0). Smaller windows
        give finer-grained speaker separation but are slower.
    shift_s : float, optional
        Sliding window shift in seconds (default 1.5). Overlap between
        consecutive windows.
    """

    def __init__(
        self,
        merge_thr: float = 0.70,
        window_s: float = 3.0,
        shift_s: float = 1.5,
    ):
        if not _HAS_FUNASR:
            raise ImportError(
                "funasr is required. Install it via: pip install funasr"
            )

        self.merge_thr = merge_thr
        self.window_s = window_s
        self.shift_s = shift_s
        self._model = None

    # ── Public API ──────────────────────────────────────────────

    def diarize(
        self,
        audio_path: str,
        segments: Sequence[Tuple[int, int]],
        audio_array: Optional[np.ndarray] = None,
        sample_rate: int = 16000,
    ) -> Tuple[List[int], int]:
        """Run speaker diarization on VAD segments.

        Parameters
        ----------
        audio_path : str
            Path to the audio file (used to load waveform if audio_array
            is not provided, and per-segment WAV writes).
        segments : list of (start_ms, end_ms)
            VAD segments in milliseconds, as produced by AutoModel._detect_segments().
        audio_array : np.ndarray, optional
            Pre-loaded mono waveform. If not given, loaded from audio_path.
        sample_rate : int
            Sample rate of the audio (default 16000).

        Returns
        -------
        labels : list of int
            Speaker label (0, 1, …) for each input segment.
        num_speakers : int
            Number of distinct speakers found.
        """
        self._lazy_init()

        if audio_array is None:
            audio_array, sample_rate = self._load_audio(audio_path)

        # Split VAD segments into smaller overlapping chunks
        chunks = self._split_segments(segments, sample_rate)

        # Write chunk WAVs to a temp dir
        temp_dir = tempfile.mkdtemp(prefix="mano_diar_")
        try:
            chunk_paths = []
            for ci, (start_samp, end_samp) in enumerate(chunks):
                clip = audio_array[start_samp:end_samp].astype(np.float32, copy=False)
                wav_path = os.path.join(temp_dir, f"chunk_{ci:04d}.wav")
                sf.write(wav_path, clip, sample_rate)
                chunk_paths.append(wav_path)

            # Extract CAM++ embeddings (sliding window per chunk)
            all_embs = []
            segment_map = []  # which segment each embedding window maps to
            for seg_idx in range(len(segments)):
                for ci in range(len(chunks)):
                    # Determine which segment this chunk belongs to
                    pass  # handled by chunk ordering

            # Actually: chunks are ordered sequentially by segment,
            # then by time within segment. So chunk i corresponds to
            # the i-th chunk, and we need to know which segment.
            # Let's rebuild the mapping more carefully.
            all_embs = []
            seg_map = []
            seg_ranges = self._compute_seg_chunk_ranges(segments, sample_rate)

            for seg_idx, (seg_start_samp, seg_end_samp) in enumerate(seg_ranges):
                seg_path = os.path.join(
                    temp_dir, f"seg_{seg_idx:04d}.wav"
                )
                clip = audio_array[seg_start_samp:seg_end_samp].astype(
                    np.float32, copy=False
                )
                sf.write(seg_path, clip, sample_rate)

                embs = self._extract_embeddings_sliding(seg_path)
                if embs.shape[0] > 0:
                    all_embs.append(embs)
                    seg_map.extend([seg_idx] * embs.shape[0])
                else:
                    # Fallback: one global embedding per segment
                    embs_fb = self._extract_embedding_single(seg_path)
                    all_embs.append(embs_fb.reshape(1, -1))
                    seg_map.append(seg_idx)

            if not all_embs:
                return [0] * len(segments), 1

            all_embs = np.vstack(all_embs)
            n_windows = all_embs.shape[0]

            if n_windows < 3:
                win_labels = [0] * n_windows
            else:
                win_labels = self._cluster(all_embs)

            # Majority vote per segment
            seg_votes: Dict[int, List[int]] = {}
            for win_idx, seg_idx in enumerate(seg_map):
                seg_votes.setdefault(seg_idx, []).append(win_labels[win_idx])

            final_labels: List[int] = []
            for seg_idx in range(len(segments)):
                if seg_idx in seg_votes:
                    cnt = Counter(seg_votes[seg_idx])
                    final_labels.append(cnt.most_common(1)[0][0])
                else:
                    final_labels.append(0)

            num_speakers = len(set(final_labels))
            return final_labels, num_speakers

        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    # ── Internal helpers ────────────────────────────────────────

    def _lazy_init(self):
        if self._model is None:
            logger.info("Loading CAM++ speaker model...")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self._model = _get_funasr_model()
            logger.info("CAM++ model loaded")

    @staticmethod
    def _load_audio(path: str) -> Tuple[np.ndarray, int]:
        """Load mono audio with soundfile."""
        if not _HAS_SOUNDFILE:
            raise ImportError("soundfile is required. Install: pip install soundfile")
        audio, sr = sf.read(path)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio, sr

    def _split_segments(
        self,
        segments: Sequence[Tuple[int, int]],
        sr: int,
    ) -> List[Tuple[int, int]]:
        """Split VAD segments into smaller overlapping chunks (samples)."""
        chunk_samp = int(self.window_s * sr)
        shift_samp = int(self.shift_s * sr)
        stride = chunk_samp - shift_samp

        chunks = []
        for start_ms, end_ms in segments:
            seg_start = int(start_ms * sr / 1000)
            seg_end = min(int(end_ms * sr / 1000), 2**31 - 1)

            t = seg_start
            while t < seg_end:
                ce = min(t + chunk_samp, seg_end)
                if ce - t >= sr:  # at least 1s
                    chunks.append((t, ce))
                t += stride
                if seg_end - t < sr and chunks:
                    # Merge remaining into last chunk
                    prev_t, prev_ce = chunks[-1]
                    chunks[-1] = (prev_t, seg_end)
                    break

        return chunks

    def _compute_seg_chunk_ranges(
        self,
        segments: Sequence[Tuple[int, int]],
        sr: int,
    ) -> List[Tuple[int, int]]:
        """Return (start_samp, end_samp) for each segment (copied)."""
        ranges = []
        for start_ms, end_ms in segments:
            s = int(start_ms * sr / 1000)
            e = min(int(end_ms * sr / 1000), 2**31 - 1)
            ranges.append((s, e))
        return ranges

    def _extract_embeddings_sliding(self, wav_path: str) -> np.ndarray:
        """Extract CAM++ embeddings with sliding window over one audio file."""
        audio, sr = sf.read(wav_path)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        window_len = int(self.window_s * sr)
        shift_len = int(self.shift_s * sr)

        embeddings = []
        for start in range(0, len(audio) - window_len + 1, shift_len):
            end = start + window_len
            chunk = audio[start:end]

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()
            sf.write(tmp_path, chunk, sr)
            try:
                result = self._model.generate(tmp_path)
                emb = result[0]["spk_embedding"].cpu().numpy().flatten()
                embeddings.append(emb)
            finally:
                os.unlink(tmp_path)

        if embeddings:
            return np.stack(embeddings)
        return np.array([])

    def _extract_embedding_single(self, wav_path: str) -> np.ndarray:
        """Extract a single CAM++ embedding for an entire audio file."""
        result = self._model.generate(wav_path)
        return result[0]["spk_embedding"].cpu().numpy().flatten()

    def _cluster(self, embeddings: np.ndarray) -> List[int]:
        """Cluster embeddings using FunASR ClusterBackend.

        Falls back to all-zero labels if clustering fails.
        """
        try:
            from funasr.auto.auto_model import ClusterBackend

            cb = ClusterBackend(merge_thr=self.merge_thr)
            labels = cb.forward(embeddings, oracle_num=None)
            if hasattr(labels, "tolist"):
                labels = labels.tolist()
            return [int(l) for l in labels]
        except Exception as exc:
            logger.warning("Clustering failed (%s), fallback to single speaker", exc)
            return [0] * embeddings.shape[0]
