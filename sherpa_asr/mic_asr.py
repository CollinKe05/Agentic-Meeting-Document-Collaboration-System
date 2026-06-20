from __future__ import annotations

import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import sherpa_onnx

ASR_IMPORT_ERROR: BaseException | None = None
try:
    from scipy import signal
except Exception as exc:  # noqa: BLE001
    signal = None  # type: ignore[assignment]
    ASR_IMPORT_ERROR = RuntimeError("缺少 ASR 音频增强依赖 scipy，请先安装：python -m pip install scipy")

try:
    import webrtcvad
except Exception as exc:  # noqa: BLE001
    webrtcvad = None  # type: ignore[assignment]
    if ASR_IMPORT_ERROR is None:
        ASR_IMPORT_ERROR = RuntimeError("缺少 ASR 音频增强依赖 webrtcvad，请先安装：python -m pip install webrtcvad")


BASE_DIR = Path(__file__).resolve().parent
MODEL = Path(os.environ.get("SHERPA_ASR_MODEL", BASE_DIR / "models" / "sensevoice" / "model.int8.onnx"))
TOKENS = Path(os.environ.get("SHERPA_ASR_TOKENS", BASE_DIR / "models" / "sensevoice" / "tokens.txt"))
TARGET_SR = int(os.environ.get("SHERPA_ASR_TARGET_SR", "16000"))
if TARGET_SR not in {8000, 16000, 32000, 48000}:
    raise RuntimeError("SHERPA_ASR_TARGET_SR 必须是 WebRTC VAD 支持的采样率：8000/16000/32000/48000")
BLOCKSIZE = int(os.environ.get("SHERPA_ASR_BLOCKSIZE", "4096"))
PRE_ROLL_MS = int(os.environ.get("SHERPA_ASR_PRE_ROLL_MS", "500"))
TAIL_MS = int(os.environ.get("SHERPA_ASR_TAIL_MS", "700"))
OVERLAP_MS = int(os.environ.get("SHERPA_ASR_OVERLAP_MS", "250"))
MAX_SEGMENT_SECONDS = float(os.environ.get("SHERPA_ASR_MAX_SEGMENT_SECONDS", "12"))
MIN_SEGMENT_SECONDS = float(os.environ.get("SHERPA_ASR_MIN_SEGMENT_SECONDS", "0.35"))
VAD_AGGRESSIVENESS = int(os.environ.get("SHERPA_ASR_VAD_AGGRESSIVENESS", "2"))
AGC_TARGET_RMS = float(os.environ.get("SHERPA_ASR_AGC_TARGET_RMS", "0.07"))
DEBUG_AUDIO = os.environ.get("SHERPA_ASR_DEBUG_AUDIO", "").strip().lower() in {"1", "true", "yes", "on"}
STOP_FILE = Path(os.environ["SHERPA_ASR_STOP_FILE"]) if os.environ.get("SHERPA_ASR_STOP_FILE") else None

FRAME_MS = 30
FRAME_SAMPLES = TARGET_SR * FRAME_MS // 1000


@dataclass
class DecoderState:
    recognizer: sherpa_onnx.OfflineRecognizer | None = None
    ready: bool = False
    error: BaseException | None = None


audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=400)


def main() -> int:
    device_id = _select_input_device()
    input_sr = int(os.environ.get("SHERPA_ASR_INPUT_SR") or _device_sample_rate(device_id) or 48000)
    output_file = BASE_DIR / f"录音记录_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    state = DecoderState()

    _write_header(output_file)
    if ASR_IMPORT_ERROR is not None:
        _append_status(output_file, "ASR_ERROR", str(ASR_IMPORT_ERROR))
        _append_status(output_file, "ASR_STOPPED", "录音结束")
        _log(str(ASR_IMPORT_ERROR))
        _log(f"录音结束，文件已保存：{output_file}")
        return 2
    _append_status(output_file, "ASR_LOADING", "麦克风已开始缓存，正在加载 SenseVoice 模型")
    _log("=" * 50)
    _log("开始实时语音识别")
    _log("麦克风会先启动缓存，模型加载期间的音频不会丢弃")
    _log(f"麦克风设备 ID: {device_id}")
    _log(f"采样率: {input_sr} -> {TARGET_SR}")
    _log(f"保存文件: {output_file}")
    _log("=" * 50)

    loader = threading.Thread(target=_load_recognizer, args=(state, output_file), daemon=True)
    loader.start()

    raw_buffer: list[np.ndarray] = []
    processed_tail = np.zeros(0, dtype=np.float32)
    segment_frames: list[np.ndarray] = []
    pre_roll: deque[np.ndarray] = deque(maxlen=max(1, PRE_ROLL_MS // FRAME_MS))
    speech_active = False
    silence_ms = 0
    last_debug_at = 0.0

    try:
        with sd.InputStream(
            samplerate=input_sr,
            channels=1,
            dtype="float32",
            callback=_audio_callback,
            device=device_id,
            blocksize=BLOCKSIZE,
        ):
            while not _should_stop():
                try:
                    audio = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    if state.error:
                        raise state.error
                    continue

                raw_buffer.append(audio.flatten().astype(np.float32))
                if not state.ready:
                    if state.error:
                        raise state.error
                    continue

                chunk = np.concatenate(raw_buffer, axis=0)
                raw_buffer = []
                processed = _prepare_audio(chunk, input_sr=input_sr)
                if processed_tail.size:
                    processed = np.concatenate([processed_tail, processed])

                frames, processed_tail = _split_frames(processed)
                for frame in frames:
                    is_speech = _is_speech_frame(frame)
                    if DEBUG_AUDIO and time.monotonic() - last_debug_at > 1:
                        _log(f"audio rms={_rms(frame):.6f}, speech={is_speech}, segment={len(segment_frames) * FRAME_MS / 1000:.2f}s")
                        last_debug_at = time.monotonic()

                    if is_speech:
                        if not speech_active:
                            segment_frames.extend(list(pre_roll))
                            speech_active = True
                        segment_frames.append(frame)
                        silence_ms = 0
                    else:
                        pre_roll.append(frame)
                        if speech_active:
                            segment_frames.append(frame)
                            silence_ms += FRAME_MS

                    segment_seconds = len(segment_frames) * FRAME_MS / 1000.0
                    if speech_active and (silence_ms >= TAIL_MS or segment_seconds >= MAX_SEGMENT_SECONDS):
                        _decode_and_write(
                            state.recognizer,
                            segment_frames,
                            output_file=output_file,
                            reason="silence" if silence_ms >= TAIL_MS else "max-window",
                        )
                        overlap_frames = max(0, OVERLAP_MS // FRAME_MS)
                        pre_roll.clear()
                        for item in segment_frames[-overlap_frames:]:
                            pre_roll.append(item)
                        segment_frames = []
                        speech_active = False
                        silence_ms = 0
    except KeyboardInterrupt:
        _log("收到 Ctrl+C，准备退出")
    finally:
        if not state.ready and not state.error and raw_buffer:
            wait_seconds = float(os.environ.get("ASR_MODEL_LOAD_STOP_WAIT_SECONDS", "20"))
            _append_status(output_file, "ASR_LOADING", f"正在等待模型加载完成以识别已缓存音频，最多等待 {wait_seconds:g} 秒")
            loader.join(timeout=wait_seconds)
        else:
            loader.join(timeout=0.1)
        if state.error:
            _append_status(output_file, "ASR_ERROR", f"{type(state.error).__name__}: {state.error}")
        if state.ready and raw_buffer:
            processed = _prepare_audio(np.concatenate(raw_buffer, axis=0), input_sr=input_sr)
            frames, _ = _split_frames(processed)
            segment_frames.extend(frames)
        if state.ready and segment_frames:
            _decode_and_write(state.recognizer, segment_frames, output_file=output_file, reason="stop")
        _append_status(output_file, "ASR_STOPPED", "录音结束")
        _log(f"录音结束，文件已保存：{output_file}")
    return 0


def _load_recognizer(state: DecoderState, output_file: Path) -> None:
    try:
        state.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(MODEL),
            tokens=str(TOKENS),
            language="zh",
            use_itn=True,
            num_threads=int(os.environ.get("SHERPA_ASR_THREADS", "4")),
        )
        state.ready = True
        _append_status(output_file, "ASR_READY", "SenseVoice 模型加载完成，正在转写")
        _log("ASR_READY SenseVoice 模型加载完成，正在转写")
    except BaseException as exc:  # noqa: BLE001
        state.error = exc
        _append_status(output_file, "ASR_ERROR", f"{type(exc).__name__}: {exc}")


def _audio_callback(indata, frames, callback_time, status) -> None:
    if status:
        _log(str(status))
    try:
        audio_queue.put_nowait(indata.copy())
    except queue.Full:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            pass
        audio_queue.put_nowait(indata.copy())


def _select_input_device() -> int | None:
    configured = os.environ.get("SHERPA_ASR_DEVICE_ID", "").strip()
    devices = sd.query_devices()
    if configured:
        return int(configured)
    try:
        default_input = sd.default.device[0]
        if default_input is not None and int(default_input) >= 0:
            device = devices[int(default_input)]
            if int(device.get("max_input_channels", 0)) > 0:
                return int(default_input)
    except Exception:
        pass
    preferred_names = ("microphone", "mic array", "mic", "usb audio", "duplex")
    for index, device in enumerate(devices):
        name = str(device.get("name", "")).lower()
        if int(device.get("max_input_channels", 0)) > 0 and any(key in name for key in preferred_names):
            return index
    for index, device in enumerate(devices):
        if int(device.get("max_input_channels", 0)) > 0:
            return index
    raise RuntimeError("未检测到可用麦克风输入设备")


def _device_sample_rate(device_id: int | None) -> int | None:
    try:
        device = sd.query_devices(device_id, "input")
        return int(float(device.get("default_samplerate") or 0)) or None
    except Exception:
        return None


def _prepare_audio(samples: np.ndarray, *, input_sr: int) -> np.ndarray:
    samples = np.nan_to_num(samples.astype(np.float32), copy=False)
    samples = samples - float(np.mean(samples))
    samples = _high_pass(samples, input_sr=input_sr)
    samples = _noise_gate(samples)
    samples = _resample(samples, input_sr=input_sr, target_sr=TARGET_SR)
    samples = _agc(samples)
    return np.clip(samples, -0.98, 0.98).astype(np.float32)


def _high_pass(samples: np.ndarray, *, input_sr: int) -> np.ndarray:
    if samples.size < 8:
        return samples
    cutoff = 80.0
    alpha = np.exp(-2.0 * np.pi * cutoff / float(input_sr))
    output = np.empty_like(samples)
    previous_x = samples[0]
    previous_y = 0.0
    for index, sample in enumerate(samples):
        y = alpha * (previous_y + sample - previous_x)
        output[index] = y
        previous_x = sample
        previous_y = y
    return output


def _noise_gate(samples: np.ndarray) -> np.ndarray:
    if samples.size < 256:
        return samples
    frame = 512
    usable = samples[: samples.size - (samples.size % frame)]
    if usable.size < frame:
        return samples
    rms_values = np.sqrt(np.mean(usable.reshape(-1, frame) ** 2, axis=1) + 1e-9)
    noise_floor = float(np.percentile(rms_values, 20))
    threshold = max(noise_floor * 1.6, 0.001)
    gain = np.where(np.abs(samples) < threshold, 0.35, 1.0)
    return (samples * gain).astype(np.float32)


def _resample(samples: np.ndarray, *, input_sr: int, target_sr: int) -> np.ndarray:
    if input_sr == target_sr:
        return samples.astype(np.float32)
    gcd = int(np.gcd(input_sr, target_sr))
    up = target_sr // gcd
    down = input_sr // gcd
    return signal.resample_poly(samples, up, down).astype(np.float32)


def _agc(samples: np.ndarray) -> np.ndarray:
    rms = _rms(samples)
    if rms <= 1e-5:
        return samples
    gain = min(8.0, max(0.5, AGC_TARGET_RMS / rms))
    return (samples * gain).astype(np.float32)


def _split_frames(samples: np.ndarray) -> tuple[list[np.ndarray], np.ndarray]:
    frame_count = samples.size // FRAME_SAMPLES
    frames = [
        samples[index * FRAME_SAMPLES : (index + 1) * FRAME_SAMPLES].astype(np.float32)
        for index in range(frame_count)
    ]
    tail = samples[frame_count * FRAME_SAMPLES :].astype(np.float32)
    return frames, tail


def _is_speech_frame(frame: np.ndarray) -> bool:
    pcm = np.clip(frame, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16).tobytes()
    vad = _vad()
    if vad.is_speech(pcm16, TARGET_SR):
        return True
    return _rms(frame) > float(os.environ.get("SHERPA_ASR_BACKUP_RMS_THRESHOLD", "0.006"))


def _vad() -> webrtcvad.Vad:
    if not hasattr(_vad, "_instance"):
        _vad._instance = webrtcvad.Vad(VAD_AGGRESSIVENESS)  # type: ignore[attr-defined]
    return _vad._instance  # type: ignore[attr-defined]


def _decode_and_write(
    recognizer: sherpa_onnx.OfflineRecognizer | None,
    frames: list[np.ndarray],
    *,
    output_file: Path,
    reason: str,
) -> None:
    if recognizer is None or not frames:
        return
    samples = np.concatenate(frames, axis=0).astype(np.float32)
    if samples.size < int(TARGET_SR * MIN_SEGMENT_SECONDS):
        return
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate=TARGET_SR, waveform=samples)
    recognizer.decode_stream(stream)
    text = stream.result.text.strip()
    if not text:
        _log(f"未识别到有效文本，reason={reason}, seconds={samples.size / TARGET_SR:.2f}")
        return
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {text}"
    _log(line)
    with output_file.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2) + 1e-12))


def _write_header(output_file: Path) -> None:
    with output_file.open("a", encoding="utf-8") as handle:
        handle.write("=" * 60 + "\n")
        handle.write("录音记录\n")
        handle.write(f"开始时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        handle.write("=" * 60 + "\n\n")


def _append_status(output_file: Path, status: str, message: str) -> None:
    line = f"[[{status}]] {datetime.now().strftime('%H:%M:%S')} {message}"
    with output_file.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _should_stop() -> bool:
    return STOP_FILE is not None and STOP_FILE.exists()


def _log(message: str) -> None:
    print(message, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
