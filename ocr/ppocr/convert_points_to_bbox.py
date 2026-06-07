#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将PPOCR结果中的points转换为bbox格式
"""

import json
import os
import re

def extract_page_index(page_key):
    """
    从page_key中提取页码信息
    例如: 'page_0' -> 0, 'page_1' -> 1
    """
    if isinstance(page_key, str):
        # 使用正则表达式提取数字
        match = re.search(r'page_(\d+)', page_key)
        if match:
            return int(match.group(1))
    
    # 如果无法提取，返回0作为默认值
    return 0

def extract_bbox_from_points(points):
    """
    从points数组中提取bbox坐标
    根据观察，points的格式似乎是嵌套数组，包含坐标信息
    """
    # 检查points是否为空或格式异常
    if not points or len(points) == 0:
        return None
    
    # 提取所有有效的坐标值
    coords = []
    for point in points:
        if isinstance(point, list) and len(point) > 0:
            coords.extend([coord for coord in point if isinstance(coord, (int, float))])
    
    # 如果没有足够的坐标，返回None
    if len(coords) < 4:
        return None
    
    # 根据坐标数量处理
    if len(coords) >= 4:
        # 假设前两个是左上角坐标，后两个是右下角坐标
        # 或者取最小最大值构成bbox
        x_coords = []
        y_coords = []
        
        # 将坐标按照x,y交替排列的方式处理
        for i in range(0, len(coords), 2):
            if i + 1 < len(coords):
                x_coords.append(coords[i])
                y_coords.append(coords[i + 1])
        
        if x_coords and y_coords:
            x_min = min(x_coords)
            y_min = min(y_coords)
            x_max = max(x_coords)
            y_max = max(y_coords)
            return [int(x_min), int(y_min), int(x_max), int(y_max)]
    
    return None

def estimate_bbox_from_text_position(index, total_items):
    """
    当points数据缺失时，根据文本在页面中的位置估算bbox
    """
    # 假设页面尺寸为A4 (大约595x842点)
    page_width = 595
    page_height = 842
    
    # 每行文本的大概高度
    line_height = 20
    
    # 估算行数和位置
    estimated_line = index
    y_start = 50 + estimated_line * line_height
    y_end = y_start + 15  # 文本高度
    
    # 估算x坐标（大部分文本从左边距开始）
    x_start = 50
    x_end = page_width - 50  # 假设文本占据大部分宽度
    
    return [x_start, y_start, x_end, y_end]

def convert_ppocr_to_bbox_format(input_file, output_file):
    """
    将PPOCR结果文件转换为bbox格式
    """
    # print(f"正在读取文件: {input_file}")
    
    # 读取原始文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    converted_data = {}
    
    for page_key, ocr_results in data.items():
        # print(f"正在处理页面: {page_key}, 包含 {len(ocr_results)} 个文本块")
        converted_results = []
        
        # 从page_key中提取页码
        page_idx = extract_page_index(page_key)
        # print(f"  页码: {page_idx}")
        
        for i, item in enumerate(ocr_results):
            # 尝试从points提取bbox
            bbox = extract_bbox_from_points(item.get('points', []))
            
            # 如果无法从points提取bbox，使用估算方法
            if bbox is None:
                bbox = estimate_bbox_from_text_position(i, len(ocr_results))
                # print(f"  文本块 {i+1}: 使用估算bbox {bbox}")
            # else:
                # print(f"  文本块 {i+1}: 提取bbox {bbox}")
            
            # 创建新的数据项
            converted_item = {
                "class_name": "text",
                "bbox": bbox,
                "text": item.get('transcription', ''),
                "score": item.get('score', 0.0),
                "illegibility": item.get('illegibility', False),
                "page_idx": page_idx,  # 使用提取的页码
                "block_id": f"{page_key}_text_{i+1}"
            }
            
            converted_results.append(converted_item)
        
        converted_data[page_key] = converted_results
    
    # 保存转换后的文件
    # print(f"正在保存转换结果到: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(converted_data, f, ensure_ascii=False, indent=2)
    
    return converted_data

def convert_to_flat_format(input_file, output_file):
    """
    转换为扁平化的格式，类似于blocks_info.json
    """
    # print(f"正在创建扁平化格式...")
    
    # 读取原始文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    flat_results = []
    
    for page_key, ocr_results in data.items():
        # 从page_key中提取页码
        page_idx = extract_page_index(page_key)
        
        for i, item in enumerate(ocr_results):
            # 尝试从points提取bbox
            bbox = extract_bbox_from_points(item.get('points', []))
            
            # 如果无法从points提取bbox，使用估算方法
            if bbox is None:
                bbox = estimate_bbox_from_text_position(i, len(ocr_results))
            
            # 创建新的数据项
            converted_item = {
                "class_name": "text",
                "bbox": bbox,
                "text": item.get('transcription', ''),
                "score": item.get('score', 0.0),
                "page_idx": page_idx  # 使用提取的页码
            }
            
            flat_results.append(converted_item)
    
    # 保存转换后的文件
    # print(f"正在保存扁平化结果到: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(flat_results, f, ensure_ascii=False, indent=2)
    
    return flat_results

def analyze_points_structure(input_file):
    """
    分析points的数据结构
    """
    # print("正在分析points数据结构...")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for page_key, ocr_results in data.items():
        # print(f"\n页面 {page_key}:")
        
        for i, item in enumerate(ocr_results[:5]):  # 只分析前5个项目
            points = item.get('points', [])
            text = item.get('transcription', '')
            
            # print(f"  文本块 {i+1}: '{text[:30]}...'")
            # print(f"    points: {points}")
            # print(f"    points长度: {len(points)}")
            
            # if points:
            #     for j, point in enumerate(points):
                    # print(f"      point[{j}]: {point} (类型: {type(point)})")
        
        break  # 只分析第一个页面

def main():
    """
    主函数
    """
    input_file = "/home/m/Documents/office-AI/layout/ppocr/ppocr_system_results.json"
    
    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        print(f"错误: 输入文件不存在 {input_file}")
        return
    
    # 先分析数据结构
    analyze_points_structure(input_file)
    
    # 转换为带页面分组的格式
    output_file1 = "/home/m/Documents/office-AI/layout/layoutreader/ppocr_bbox_format.json"
    result1 = convert_ppocr_to_bbox_format(input_file, output_file1)
    
    # 转换为扁平化格式
    output_file2 = "/home/m/Documents/office-AI/layout/layoutreader/ppocr_flat_bbox.json"
    result2 = convert_to_flat_format(input_file, output_file2)
    
    print(f"\n转换完成!")
    print(f"原始数据包含页面数: {len(result1)}")
    total_blocks = sum(len(blocks) for blocks in result1.values())
    print(f"总文本块数: {total_blocks}")
    print(f"转换后的分组格式保存到: {output_file1}")
    print(f"转换后的扁平格式保存到: {output_file2}")
    
    # 显示转换示例
    if result2:
        print(f"\n转换示例:")
        first_item = result2[0]
        print(f"bbox: {first_item['bbox']}")
        print(f"text: {first_item['text'][:50]}...")
        print(f"score: {first_item['score']}")

if __name__ == "__main__":
    main()
