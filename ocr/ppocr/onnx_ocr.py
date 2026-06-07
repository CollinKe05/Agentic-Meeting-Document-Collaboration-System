# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：onnx_ocr_pipeline
# @Date   ：2025/3/18 12:15
# @Author ：leemysw

# 2025/3/18 12:15   Create
# 2025/4/7         添加命令行参数和日志记录
# 2025/6/26        修改为与pipeline.py兼容的版本
# =====================================================

import time
import cv2
import os
import sys
import numpy as np
import argparse
import datetime
import json
import fitz  # PyMuPDF
import shutil

from paddleocr import ONNXPaddleOcr

def clean_output_directory(output_dir, log_file="ocr_log.txt"):
    """
    清理输出目录中的文件
    
    Args:
        output_dir: 输出目录路径
        log_file: 日志文件路径
    """
    if os.path.exists(output_dir):
        try:
            # 获取目录中的文件列表
            files_to_remove = []
            for item in os.listdir(output_dir):
                item_path = os.path.join(output_dir, item)
                if os.path.isfile(item_path):
                    files_to_remove.append(item_path)
                elif os.path.isdir(item_path):
                    # 如果是子目录，也清理
                    try:
                        shutil.rmtree(item_path)
                        log_message(f"已清理子目录: {item_path}", log_file)
                    except Exception as e:
                        log_message(f"清理子目录失败 {item_path}: {e}", log_file)
            
            # 删除文件
            for file_path in files_to_remove:
                try:
                    os.remove(file_path)
                except Exception as e:
                    log_message(f"删除文件失败 {file_path}: {e}", log_file)
            
            if files_to_remove:
                log_message(f"已清理输出目录 {output_dir}，删除了 {len(files_to_remove)} 个文件", log_file)
            else:
                log_message(f"输出目录 {output_dir} 为空，无需清理", log_file)
                
        except Exception as e:
            log_message(f"清理输出目录时出错: {e}", log_file)
    else:
        log_message(f"输出目录 {output_dir} 不存在，将创建新目录", log_file)

def pdf_to_images(pdf_path, output_dir=None, dpi=200):
    """
    将PDF转换为图像列表
    
    Args:
        pdf_path: PDF文件路径
        output_dir: 输出目录（可选）
        dpi: 图像分辨率
    
    Returns:
        list: 图像数组列表
    """
    images = []
    
    try:
        # 打开PDF文件
        doc = fitz.open(pdf_path)
        
        for page_num in range(doc.page_count):
            # 获取页面
            page = doc.load_page(page_num)
            
            # 设置缩放因子（提高分辨率）
            zoom = dpi / 72.0  # 72是PDF的默认DPI
            mat = fitz.Matrix(zoom, zoom)
            
            # 渲染页面为图像
            pix = page.get_pixmap(matrix=mat)
            
            # 转换为numpy数组
            img_data = pix.tobytes("png")
            img_array = np.frombuffer(img_data, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            
            if img is not None:
                images.append(img)
                
                # 如果指定了输出目录，保存图像文件
                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)
                    output_path = os.path.join(output_dir, f"page_{page_num}.png")
                    cv2.imwrite(output_path, img)
        
        doc.close()
        return images
        
    except Exception as e:
        print(f"错误: 无法处理PDF文件 '{pdf_path}': {e}")
        return []

def log_message(message, log_file="ocr_log.txt"):
    """记录带时间戳的日志消息"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    
    print(log_entry)
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")

def convert_ocr_to_json_format(ocr_results, page_id=0):
    """
    将OCR结果转换为与ppocr系统兼容的JSON格式
    
    Args:
        ocr_results: OCR识别结果
        page_id: 页面ID，默认为0
    
    Returns:
        dict: 格式化的JSON结果
    """
    json_result = {f"page_{page_id}": []}
    
    if not ocr_results or len(ocr_results) == 0:
        return json_result
    
    # OCR结果通常是三层嵌套的列表：[[[bbox, (text, score)]]]
    page_results = ocr_results[0] if isinstance(ocr_results[0], list) else ocr_results
    
    for item in page_results:
        if len(item) >= 2:
            bbox = item[0]  # 边界框坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            text_info = item[1]  # (文本, 置信度)
            
            # 提取文本和置信度
            if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                text = text_info[0]
                score = float(text_info[1])
            else:
                text = str(text_info)
                score = 1.0
            
            # 转换边界框格式 - 根据JSON示例，保留完整的坐标信息
            points = []
            if isinstance(bbox, list) and len(bbox) >= 4:
                for point in bbox:
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        # 保留完整的x,y坐标
                        points.append([float(point[0]), float(point[1])])
                    else:
                        points.append([])
            
            # 确保有4个点
            while len(points) < 4:
                points.append([])
            
            json_item = {
                "illegibility": False,
                "points": points,
                "score": score,
                "transcription": text
            }
            
            json_result[f"page_{page_id}"].append(json_item)
    
    return json_result

def save_batch_results_as_json(all_results, output_path):
    """
    保存所有OCR结果到一个JSON文件中
    
    Args:
        all_results: 所有OCR结果的字典，格式为 {page_id: ocr_results}
        output_path: 输出文件路径
    
    Returns:
        str: 输出文件路径
    """
    json_data = {}
    
    for page_id, ocr_results in all_results.items():
        page_data = convert_ocr_to_json_format(ocr_results, page_id)
        json_data.update(page_data)
    
    # 保存JSON文件
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)
    
    return output_path

def get_image_files(directory):
    """
    获取目录下所有图片文件，或处理PDF文件
    
    Args:
        directory: 目录路径或文件路径
    
    Returns:
        list: 图片文件路径列表或PDF转换的图像列表
    """
    supported_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}
    image_files = []
    
    if os.path.isfile(directory):
        # 如果是PDF文件，转换为图像
        if directory.lower().endswith('.pdf'):
            print(f"检测到PDF文件，正在转换为图像...")
            images = pdf_to_images(directory)
            return images  # 返回图像数组列表
        else:
            # 如果是单个图像文件，直接返回
            return [directory]
    
    # 如果是目录，查找所有图片文件
    for filename in os.listdir(directory):
        if any(filename.lower().endswith(ext) for ext in supported_extensions):
            image_files.append(os.path.join(directory, filename))
    
    return sorted(image_files)

def process_single_image(model, image_path, args, page_index=0):
    """
    处理单张图片
    
    Args:
        model: OCR模型
        image_path: 图片路径或图像数组
        args: 命令行参数
        page_index: 页面索引，用于生成唯一的文件名
    
    Returns:
        tuple: (是否成功, 处理时间, 结果数量, OCR结果)
    """
    try:
        # 支持直接传入图像数组
        if isinstance(image_path, np.ndarray):
            img = image_path
            image_name = f"page_{page_index}"
        else:
            img = cv2.imread(image_path)
            image_name = os.path.basename(image_path)
            
        if img is None:
            log_message(f"错误: 无法读取图像 '{image_name}'", args.log)
            return False, 0, 0, None

        s = time.time()
        results = model.ocr(img, det=True, rec=True, cls=True)
        e = time.time()
        
        processing_time = e - s
        result_count = len(results[0]) if results and len(results) > 0 else 0
        
        log_message(f"图片: {image_name} - 耗时: {processing_time:.3f}秒 - 识别文本数: {result_count}", args.log)

        # 可视化结果已禁用 - 仅保存JSON结果

        return True, processing_time, result_count, results
        
    except Exception as e:
        image_name = f"page_{page_index}" if isinstance(image_path, np.ndarray) else os.path.basename(image_path)
        log_message(f"处理图片 '{image_name}' 时出错: {e}", args.log)
        return False, 0, 0, None

if __name__ == '__main__':
    # 解析命令行参数 - 与pipeline.py兼容
    parser = argparse.ArgumentParser(description='ONNX OCR处理工具')
    parser.add_argument('--input', type=str, required=True,
                        help='输入图片路径、文件夹路径或PDF文件路径')
    parser.add_argument('--output_name', type=str, 
                        help='输出文件名前缀（用于生成兼容的文件名）')
    parser.add_argument('--bmodel_det', type=str, 
                        help='检测模型路径（兼容性参数，ONNX版本不使用）')
    parser.add_argument('--bmodel_rec', type=str,
                        help='识别模型路径（兼容性参数，ONNX版本不使用）')
    parser.add_argument('--img_size', type=str,
                        help='图像尺寸（兼容性参数，ONNX版本不使用）')
    parser.add_argument('--char_dict_path', type=str,
                        help='字符字典路径（兼容性参数，ONNX版本不使用）')
    parser.add_argument('--log', type=str, default="ocr_log.txt",
                        help='日志文件路径')
    parser.add_argument('--output_dir', type=str, default="results",
                        help='输出目录')
    args = parser.parse_args()
    
    # 清理输出目录中的旧文件
    clean_output_directory(args.output_dir, args.log)
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 获取要处理的图片文件列表
    image_files = get_image_files(args.input)
    
    if not image_files:
        log_message(f"在 '{args.input}' 中未找到支持的图片文件或PDF文件", args.log)
        exit(1)
    
    # 根据输入类型确定处理的项目数量
    if isinstance(image_files[0], np.ndarray):
        # PDF转换的图像数组
        total_files = len(image_files)
        log_message(f"从PDF转换得到 {total_files} 页图像，开始批量处理...", args.log)
    else:
        # 图片文件
        total_files = len(image_files)
        log_message(f"找到 {total_files} 个图片文件，开始批量处理...", args.log)
    
    # 初始化OCR模型
    model = ONNXPaddleOcr(use_angle_cls=True, use_gpu=True)
    model.load_model()
    log_message("模型加载完成", args.log)

    # 批量处理统计信息
    success_count = 0
    total_time = 0
    total_texts = 0
    all_ocr_results = {}  # 存储所有OCR结果
    
    for idx, image_path in enumerate(image_files):
        if isinstance(image_path, np.ndarray):
            display_name = f"page_{idx}"
        else:
            display_name = os.path.basename(image_path)
            
        log_message(f"[{idx+1}/{total_files}] 开始处理: {display_name}", args.log)
        
        success, processing_time, text_count, ocr_results = process_single_image(model, image_path, args, idx)
        
        if success:
            success_count += 1
            total_time += processing_time
            total_texts += text_count
            # 按顺序存储OCR结果，页面ID从0开始
            all_ocr_results[idx] = ocr_results
    
    # 保存批量JSON结果 - 使用与ppocr系统兼容的文件名格式
    if all_ocr_results:
        # 生成与pipeline.py期望的文件名格式兼容的输出文件名
        if args.output_name:
            json_filename = f"{args.output_name}_ppocr_results.json"
        else:
            # 如果没有指定output_name，从输入文件推断
            if os.path.isfile(args.input):
                base_name = os.path.splitext(os.path.basename(args.input))[0]
                json_filename = f"{base_name}_ppocr_results.json"
            else:
                folder_name = os.path.basename(args.input.rstrip('/')) or "batch"
                json_filename = f"{folder_name}_ppocr_results.json"
        
        json_output_path = os.path.join(args.output_dir, json_filename)
        save_batch_results_as_json(all_ocr_results, json_output_path)
        log_message(f"批量JSON结果已保存到: {json_output_path}", args.log)
    
    # 输出处理统计信息
    log_message("=" * 50, args.log)
    log_message("批量处理完成！", args.log)
    log_message(f"总文件数: {total_files}", args.log)
    log_message(f"成功处理: {success_count}", args.log)
    log_message(f"失败文件: {total_files - success_count}", args.log)
    log_message(f"总耗时: {total_time:.3f}秒", args.log)
    log_message(f"平均耗时: {total_time/success_count:.3f}秒/文件" if success_count > 0 else "平均耗时: N/A", args.log)
    log_message(f"识别文本总数: {total_texts}", args.log)
    log_message(f"结果保存在: {args.output_dir}", args.log)