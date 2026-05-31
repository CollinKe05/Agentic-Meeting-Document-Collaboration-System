from __future__ import annotations

import os
import queue
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import sherpa_onnx


BASE_DIR = Path(__file__).resolve().parent
MODEL = Path(os.environ.get("SHERPA_ASR_MODEL", BASE_DIR / "models" / "sensevoice" / "model.int8.onnx"))
TOKENS = Path(os.environ.get("SHERPA_ASR_TOKENS", BASE_DIR / "models" / "sensevoice" / "tokens.txt"))
TARGET_SR = int(os.environ.get("SHERPA_ASR_TARGET_SR", "16000"))
BLOCKSIZE = int(os.environ.get("SHERPA_ASR_BLOCKSIZE", "4096"))

# Built-in laptop microphones can be quiet. A low default plus max-window flushing
# is more reliable than waiting forever for a perfect speech/silence boundary.
SILENCE_THRESHOLD = float(os.environ.get("SHERPA_ASR_SILENCE_THRESHOLD", "0.0008"))
MAX_SILENCE_CHUNKS = int(os.environ.get("SHERPA_ASR_MAX_SILENCE_CHUNKS", "8"))
MIN_SEGMENT_SECONDS = float(os.environ.get("SHERPA_ASR_MIN_SEGMENT_SECONDS", "0.35"))
MAX_SEGMENT_SECONDS = float(os.environ.get("SHERPA_ASR_MAX_SEGMENT_SECONDS", "20"))
DEBUG_AUDIO = os.environ.get("SHERPA_ASR_DEBUG_AUDIO", "").strip().lower() in {"1", "true", "yes", "on"}
STOP_FILE = Path(os.environ["SHERPA_ASR_STOP_FILE"]) if os.environ.get("SHERPA_ASR_STOP_FILE") else None

audio_queue: queue.Queue[np.ndarray] = queue.Queue()


def main() -> int:
    device_id = _select_input_device()
    input_sr = int(os.environ.get("SHERPA_ASR_INPUT_SR") or _device_sample_rate(device_id) or 48000)
    output_file = BASE_DIR / f"录音记录_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"

    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(MODEL),
        tokens=str(TOKENS),
        language="zh",
        use_itn=True,
        num_threads=int(os.environ.get("SHERPA_ASR_THREADS", "4")),
    )

    _write_header(output_file)
    _log("=" * 50)
    _log("开始实时语音识别")
    _log("收到停止信号时会先识别剩余音频，再退出")
    _log(f"麦克风设备 ID: {device_id}")
    _log(f"采样率: {input_sr} -> {TARGET_SR}")
    _log(f"保存文件: {output_file}")
    _log("=" * 50)

    audio_buffer: list[np.ndarray] = []
    silence_chunks = 0
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
                    continue

                volume = float(np.abs(audio).mean())
                if DEBUG_AUDIO and time.monotonic() - last_debug_at > 1:
                    _log(f"audio volume={volume:.6f}, buffered={_buffer_seconds(audio_buffer, input_sr):.2f}s")
                    last_debug_at = time.monotonic()

                if volume > SILENCE_THRESHOLD:
                    audio_buffer.append(audio)
                    silence_chunks = 0
                elif audio_buffer:
                    # Keep a little trailing silence so the recognizer gets natural endings.
                    audio_buffer.append(audio)
                    silence_chunks += 1

                if audio_buffer and silence_chunks > MAX_SILENCE_CHUNKS:
                    _decode_and_write(
                        recognizer,
                        audio_buffer,
                        input_sr=input_sr,
                        output_file=output_file,
                        reason="silence",
                    )
                    audio_buffer = []
                    silence_chunks = 0
                    continue

                if _buffer_seconds(audio_buffer, input_sr) >= MAX_SEGMENT_SECONDS:
                    _decode_and_write(
                        recognizer,
                        audio_buffer,
                        input_sr=input_sr,
                        output_file=output_file,
                        reason="max-window",
                    )
                    audio_buffer = []
                    silence_chunks = 0
    except KeyboardInterrupt:
        _log("收到 Ctrl+C，准备退出")
    finally:
        if audio_buffer:
            _decode_and_write(
                recognizer,
                audio_buffer,
                input_sr=input_sr,
                output_file=output_file,
                reason="stop",
            )
        _log(f"录音结束，文件已保存：{output_file}")
    return 0


def _audio_callback(indata, frames, callback_time, status) -> None:
    if status:
        _log(str(status))
    audio_queue.put(indata.copy())


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

    preferred_names = ("麦克风", "microphone", "mic array", "mic")
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


def _decode_and_write(
    recognizer: sherpa_onnx.OfflineRecognizer,
    audio_buffer: list[np.ndarray],
    *,
    input_sr: int,
    output_file: Path,
    reason: str,
) -> None:
    if not audio_buffer:
        return

    samples = np.concatenate(audio_buffer, axis=0).flatten().astype(np.float32)
    if len(samples) < int(input_sr * MIN_SEGMENT_SECONDS):
        return

    samples = _resample_if_needed(samples, input_sr=input_sr, target_sr=TARGET_SR)
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate=TARGET_SR, waveform=samples)
    recognizer.decode_stream(stream)
    text = stream.result.text.strip()

    if not text:
        _log(f"未识别到有效文本，reason={reason}, seconds={len(samples) / TARGET_SR:.2f}")
        return

    line = f"[{datetime.now().strftime('%H:%M:%S')}] {text}"
    _log(line)
    with output_file.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _resample_if_needed(samples: np.ndarray, *, input_sr: int, target_sr: int) -> np.ndarray:
    if input_sr == target_sr:
        return samples
    if input_sr % target_sr == 0:
        return samples[:: input_sr // target_sr].astype(np.float32)

    duration = len(samples) / float(input_sr)
    target_len = max(1, int(duration * target_sr))
    old_x = np.linspace(0, len(samples), num=len(samples), endpoint=False)
    new_x = np.linspace(0, len(samples), num=target_len, endpoint=False)
    return np.interp(new_x, old_x, samples).astype(np.float32)


def _buffer_seconds(audio_buffer: list[np.ndarray], input_sr: int) -> float:
    if not audio_buffer:
        return 0.0
    return sum(len(item) for item in audio_buffer) / float(input_sr)


def _write_header(output_file: Path) -> None:
    with output_file.open("a", encoding="utf-8") as handle:
        handle.write("=" * 60 + "\n")
        handle.write("录音记录\n")
        handle.write(f"开始时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        handle.write("=" * 60 + "\n\n")


def _should_stop() -> bool:
    return STOP_FILE is not None and STOP_FILE.exists()


def _log(message: str) -> None:
    print(message, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
