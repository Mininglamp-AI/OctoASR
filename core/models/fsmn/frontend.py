"""
FSMN-VAD 前端特征提取: Kaldi-style Fbank + LFR + CMVN

与 FunASR WavFrontendOnline 对齐:
- Kaldi fbank (纯 numpy/scipy 复刻 torchaudio.compliance.kaldi.fbank)
- LFR: lfr_m=5, lfr_n=1
- CMVN: Kaldi Nnet 格式 (AddShift + Rescale)
"""
import re
import numpy as np
from functools import lru_cache
from typing import Tuple, Optional

from scipy.signal.windows import hamming as _scipy_hamming


def load_cmvn(cmvn_path: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    加载 Kaldi Nnet 格式的 CMVN 文件 (am.mvn).

    格式:
        <AddShift> D D
        <LearnRateCoef> 0 [ shift_values ]
        <Rescale> D D
        <LearnRateCoef> 0 [ scale_values ]

    CMVN 操作: output = (input + shift) * scale
    """
    with open(cmvn_path, "r") as f:
        content = f.read()

    # 提取 AddShift 后的数值
    shift_match = re.search(r"<AddShift>.*?\[(.*?)\]", content, re.DOTALL)
    scale_match = re.search(r"<Rescale>.*?\[(.*?)\]", content, re.DOTALL)

    if not shift_match or not scale_match:
        raise ValueError(f"Cannot parse CMVN file: {cmvn_path}")

    shift = np.array([float(x) for x in shift_match.group(1).split()], dtype=np.float32)
    scale = np.array([float(x) for x in scale_match.group(1).split()], dtype=np.float32)

    return shift, scale


_EPSILON = np.finfo(np.float32).eps


def _mel_scale(freq: np.ndarray) -> np.ndarray:
    return 1127.0 * np.log(1.0 + freq / 700.0)


@lru_cache(maxsize=8)
def _get_mel_banks(
    num_bins: int,
    padded_window_size: int,
    sample_rate: int,
    low_freq: float,
    high_freq: float,
) -> np.ndarray:
    """复刻 torchaudio.compliance.kaldi.get_mel_banks (vtln=identity).

    返回 [num_bins, num_fft_bins + 1] 的三角滤波器组 (float32),
    最后一列 (Nyquist) 为 0,与 torch 对功率谱补零列的行为一致。
    """
    num_fft_bins = padded_window_size // 2
    nyquist = 0.5 * sample_rate
    if high_freq <= 0.0:
        high_freq = nyquist

    fft_bin_width = sample_rate / padded_window_size
    mel_low = _mel_scale(np.array(low_freq, dtype=np.float64))
    mel_high = _mel_scale(np.array(high_freq, dtype=np.float64))
    mel_freq_delta = (mel_high - mel_low) / (num_bins + 1)

    bin_idx = np.arange(num_bins, dtype=np.float64).reshape(-1, 1)
    left_mel = mel_low + bin_idx * mel_freq_delta
    center_mel = mel_low + (bin_idx + 1.0) * mel_freq_delta
    right_mel = mel_low + (bin_idx + 2.0) * mel_freq_delta

    mel = _mel_scale(fft_bin_width * np.arange(num_fft_bins, dtype=np.float64)).reshape(1, -1)

    up_slope = (mel - left_mel) / (center_mel - left_mel)
    down_slope = (right_mel - mel) / (right_mel - center_mel)
    bins = np.maximum(0.0, np.minimum(up_slope, down_slope))  # [num_bins, num_fft_bins]

    # 补一个零列 (Nyquist bin),对齐 torch 对功率谱 [.., num_fft_bins+1] 的处理
    bins = np.pad(bins, ((0, 0), (0, 1)))
    return bins.astype(np.float32)


def compute_fbank_kaldi(
    waveform: np.ndarray,
    sample_rate: int = 16000,
    n_mels: int = 80,
    frame_length_ms: int = 25,
    frame_shift_ms: int = 10,
    dither: float = 0.0,
) -> np.ndarray:
    """
    Kaldi-style fbank 特征提取 (纯 numpy/scipy,数值对齐 torchaudio kaldi.fbank).

    复刻 torchaudio.compliance.kaldi.fbank 在以下默认配置下的行为:
    window_type="hamming", dither=0, remove_dc_offset=True,
    preemphasis_coefficient=0.97, round_to_power_of_two=True, snip_edges=True,
    use_power=True, use_log_fbank=True, use_energy=False, low_freq=20,
    high_freq=Nyquist, vtln=identity. 全程 float32。

    Returns:
        fbank: [num_frames, n_mels] float32
    """
    window_size = int(sample_rate * frame_length_ms * 0.001)   # 400
    window_shift = int(sample_rate * frame_shift_ms * 0.001)   # 160
    # round_to_power_of_two: next pow2 >= window_size
    padded_window_size = 1 << (window_size - 1).bit_length()   # 512

    wav = np.asarray(waveform, dtype=np.float32) * np.float32(1 << 15)
    n = wav.shape[0]

    # 分帧 (snip_edges=True)
    if n < window_size:
        return np.zeros((0, n_mels), dtype=np.float32)
    m = 1 + (n - window_size) // window_shift
    frames = np.lib.stride_tricks.sliding_window_view(wav, window_size)[::window_shift][:m].copy()

    # (b) remove_dc_offset: 逐帧去均值
    frames -= frames.mean(axis=1, keepdims=True)

    # (d) preemphasis 0.97, 左侧 replicate pad (首样本以自身为前一帧)
    prev = np.empty_like(frames)
    prev[:, 1:] = frames[:, :-1]
    prev[:, 0] = frames[:, 0]
    frames = frames - np.float32(0.97) * prev

    # (e) Hamming 窗 (对称, N-1 分母)
    window = _scipy_hamming(window_size, sym=True).astype(np.float32)
    frames *= window

    # (f) 补零到 padded_window_size, 功率谱
    spectrum = np.abs(np.fft.rfft(frames, n=padded_window_size, axis=1)) ** 2  # [m, 257]

    # mel 投影 + log floor
    banks = _get_mel_banks(n_mels, padded_window_size, sample_rate, 20.0, 0.0)  # [n_mels, 257]
    mel_energies = spectrum.astype(np.float32) @ banks.T  # [m, n_mels]
    mel_energies = np.log(np.maximum(mel_energies, _EPSILON))

    return mel_energies.astype(np.float32)  # [T, n_mels]


def apply_lfr(
    features: np.ndarray, lfr_m: int = 5, lfr_n: int = 1
) -> np.ndarray:
    """
    Low Frame Rate: 每 lfr_n 帧取一帧, 每帧拼接 lfr_m 帧.

    FunASR 的 LFR 对前几帧做左侧填充 (用第一帧重复).

    Args:
        features: [T, D]
        lfr_m: 拼接帧数
        lfr_n: 步长

    Returns:
        [T', D * lfr_m]
    """
    T, D = features.shape
    # FunASR 左侧 padding: 重复第一帧 (lfr_m - 1) // 2 次
    left_pad = (lfr_m - 1) // 2
    if left_pad > 0:
        pad_frames = np.tile(features[0:1], (left_pad, 1))
        features = np.concatenate([pad_frames, features], axis=0)

    T_padded = features.shape[0]
    T_out = (T_padded + lfr_n - 1) // lfr_n
    out = np.zeros((T_out, D * lfr_m), dtype=np.float32)

    for i in range(T_out):
        start = i * lfr_n
        for j in range(lfr_m):
            idx = start + j
            if idx < T_padded:
                out[i, j * D : (j + 1) * D] = features[idx]
            else:
                out[i, j * D : (j + 1) * D] = features[T_padded - 1]

    return out


def apply_cmvn(
    features: np.ndarray, shift: np.ndarray, scale: np.ndarray
) -> np.ndarray:
    """
    Kaldi CMVN: output = (input + shift) * scale
    """
    return (features + shift) * scale


def extract_features(
    waveform: np.ndarray,
    sample_rate: int = 16000,
    n_mels: int = 80,
    frame_length_ms: int = 25,
    frame_shift_ms: int = 10,
    lfr_m: int = 5,
    lfr_n: int = 1,
    cmvn_path: Optional[str] = None,
) -> np.ndarray:
    """
    完整前端: waveform → Kaldi fbank → LFR → CMVN → [T', 400]
    """
    # 1. Kaldi-style fbank
    fbank = compute_fbank_kaldi(waveform, sample_rate, n_mels, frame_length_ms, frame_shift_ms)

    # 2. LFR
    features = apply_lfr(fbank, lfr_m, lfr_n)

    # 3. CMVN
    if cmvn_path is not None:
        shift, scale = load_cmvn(cmvn_path)
        if len(shift) == features.shape[1]:
            features = apply_cmvn(features, shift, scale)

    return features
