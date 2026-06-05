#!/bin/bash
# 在 RDK X5 上运行此脚本下载 BPU OCR 模型
# 用法: bash download_bpu_models.sh

MODEL_DIR="$(cd "$(dirname "$0")" && pwd)/models"

echo "下载 BPU OCR 模型到 $MODEL_DIR ..."

wget -P "$MODEL_DIR" https://archive.d-robotics.cc/downloads/rdk_model_zoo/rdk_x5/en_PP-OCRv3_det_640x640_nv12.bin
wget -P "$MODEL_DIR" https://archive.d-robotics.cc/downloads/rdk_model_zoo/rdk_x5/en_PP-OCRv3_rec_48x320_rgb.bin

echo "完成。模型已保存到 $MODEL_DIR"
ls -lh "$MODEL_DIR"/*.bin
