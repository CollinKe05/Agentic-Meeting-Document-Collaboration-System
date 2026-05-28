import queue
from datetime import datetime

import numpy as np
import sounddevice as sd
import sherpa_onnx

# ========= 模型路径 ==========
MODEL = "models/sensevoice/model.int8.onnx"
TOKENS = "models/sensevoice/tokens.txt"

# ========= 麦克风配置 ==========
DEVICE_ID = 1       # FYSP002 麦克风
INPUT_SR = 48000   # FYSP002 默认采样率
TARGET_SR = 16000  # SenseVoice要求16k

# ========= 自动生成文件名 ==========
current_time = datetime.now().strftime(
    "%Y-%m-%d_%H-%M-%S"
)

OUTPUT_FILE = (
    f"录音记录_{current_time}.txt"
)

# ========= 静音检测 ==========
SILENCE_THRESHOLD = 0.01
MAX_SILENCE = 15

q = queue.Queue()


def callback(indata, frames, time, status):
    if status:
        print(status)

    q.put(indata.copy())


# ========= SenseVoice ==========
recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
    model=MODEL,
    tokens=TOKENS,
    language="zh",
    use_itn=True,
    num_threads=4,
)

print("=" * 50)
print("开始实时语音识别")
print("停顿后自动输出完整句子")
print(f"麦克风设备: FYSP002 (ID={DEVICE_ID})")
print(f"保存文件: {OUTPUT_FILE}")
print("按 Ctrl+C 退出")
print("=" * 50)
print()


# ========= 创建文档 ==========
with open(
    OUTPUT_FILE,
    "a",
    encoding="utf-8"
) as f:

    f.write("=" * 60 + "\n")
    f.write("录音记录\n")
    f.write(
        f"开始时间："
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    f.write("=" * 60 + "\n\n")


audio_buffer = []
silence_count = 0

try:
    with sd.InputStream(
        samplerate=INPUT_SR,
        channels=1,
        dtype="float32",
        callback=callback,
        device=DEVICE_ID,
    ):

        while True:
            audio = q.get()

            volume = np.abs(audio).mean()

            # ===== 有声音 =====
            if volume > SILENCE_THRESHOLD:
                audio_buffer.append(audio)
                silence_count = 0

            # ===== 静音 =====
            else:
                if len(audio_buffer) > 0:
                    silence_count += 1

            # ===== 停顿后识别 =====
            if silence_count > MAX_SILENCE:

                samples = np.concatenate(
                    audio_buffer,
                    axis=0
                ).flatten()

                # 48k -> 16k 重采样
                factor = INPUT_SR // TARGET_SR
                samples = samples[::factor]

                stream = recognizer.create_stream()

                stream.accept_waveform(
                    sample_rate=TARGET_SR,
                    waveform=samples
                )

                recognizer.decode_stream(stream)

                text = stream.result.text.strip()

                if text:
                    timestamp = datetime.now().strftime(
                        "%H:%M:%S"
                    )

                    line = (
                        f"[{timestamp}] "
                        f"{text}"
                    )

                    # 控制台输出
                    print(line)

                    # 写入文档
                    with open(
                        OUTPUT_FILE,
                        "a",
                        encoding="utf-8"
                    ) as f:

                        f.write(line + "\n")

                # 清空缓存
                audio_buffer = []
                silence_count = 0

except KeyboardInterrupt:
    print("\n\n录音结束")
    print(f"文件已保存：{OUTPUT_FILE}")