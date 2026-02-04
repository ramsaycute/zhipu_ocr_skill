#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智谱 GLM-OCR 文档解析脚本 (并发增强版)

支持输入:
  - 图片文件 (JPG, PNG)
  - PDF 文件 (自动转图片并并发处理)

使用方法:
  python zhipu_ocr.py <文件路径>
"""

import sys
import os
import base64
import json
import mimetypes
import io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import fitz  # PyMuPDF
import re

def load_config() -> dict:
    """从 config.json 加载配置"""
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# 加载配置
CONFIG = load_config()
ZHIPU_API_KEY = CONFIG["api_key"]
API_ENDPOINT = CONFIG["api_endpoint"]
MODEL_NAME = CONFIG["model_name"]
MAX_CONCURRENCY = CONFIG.get("max_concurrency", 10)  # 从配置读取，默认10

def clean_markdown_text(text: str) -> str:
    """
    清理 OCR 结果中的 LaTeX 痕迹和不必要的公式符号
    """
    if not text:
        return ""
    
    # 1. 移除页面开头或结尾可能出现的横线 (---) 等占位符
    lines = text.split('\n')
    while lines and re.match(r'^\s*[-*_]{3,}\s*$', lines[0]):
        lines.pop(0)
    while lines and re.match(r'^\s*[-*_]{3,}\s*$', lines[-1]):
        lines.pop(-1)
    text = '\n'.join(lines).strip()

    # 2. 处理带 mathrm 的单位: $15\mathrm{g}$ -> 15g
    text = re.sub(r'\$\s*(\d+(?:\.\d+)?)\s*\\mathrm\{([a-zA-Z]+)\}\s*\$', r'\1\2', text)
    # 3. 处理单独在公式里的单位: 15$\mathrm{g}$ -> 15g
    text = re.sub(r'(\d+(?:\.\d+)?)\s*\$\s*\\mathrm\{([a-zA-Z]+)\}\s*\$', r'\1\2', text)
    # 4. 处理简单的数字公式包裹: $15$ -> 15
    text = re.sub(r'\$\s*(\d+(?:\.\d+)?)\s*\$', r'\1', text)
    # 5. 处理一些 OCR 可能出现的特殊字符残留
    text = text.replace('\\mathrm{g}', 'g')
    
    return text

def is_chinese_char(c: str) -> bool:
    """判断字符是否为中文"""
    if not c: return False
    return '\u4e00' <= c <= '\u9fff'

def get_image_base64(image_bytes: bytes, mime_type: str = "image/png") -> str:
    """将图片字节转换为 Base64 字符串"""
    base64_content = base64.b64encode(image_bytes).decode('utf-8')
    return f"data:{mime_type};base64,{base64_content}"

def call_ocr_api_with_data(data_uri: str, label: str = "page") -> dict:
    """调用智谱 OCR API 处理 Base64 数据"""
    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_NAME,
        "file": data_uri
    }
    
    response = requests.post(
        API_ENDPOINT,
        headers=headers,
        json=payload,
        timeout=120
    )
    
    if response.status_code != 200:
        raise Exception(f"API请求失败 [{response.status_code}] ({label}): {response.text}")
    
    return response.json()

def process_single_image(file_path: str):
    """处理单个图片文件"""
    path = Path(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    
    with open(file_path, 'rb') as f:
        img_bytes = f.read()
    
    data_uri = get_image_base64(img_bytes, mime_type)
    print(f"📤 正在处理图片: {path.name}")
    result = call_ocr_api_with_data(data_uri, path.name)
    md_text = clean_markdown_text(result.get("md_results", ""))
    return md_text, result.get("usage", {})

def check_environment():
    """检查运行环境依赖"""
    dependencies = ["requests", "fitz"]
    missing = []
    for dep in dependencies:
        try:
            __import__(dep if dep != "fitz" else "fitz")
        except ImportError:
            missing.append("PyMuPDF" if dep == "fitz" else dep)
    
    if missing:
        print(f"❌ 缺少必要的依赖环境: {', '.join(missing)}")
        print("请先运行: pip install requests pymupdf")
        sys.exit(1)
    
    # 检查当前工作目录写权限
    if not os.access(os.getcwd(), os.W_OK):
        print(f"❌ 错误: 对当前工作目录 {os.getcwd()} 没有写权限，无法创建缓存和结果文件。")
        sys.exit(1)

def process_batch_concurrently(image_tasks: list, cache_dir: Path, smart_merge: bool = True):
    """
    通用并发处理一批图片任务
    image_tasks: list of dict { "label": str, "get_data_uri": callable, "index": int }
    smart_merge: PDF使用True(流式拼接), 文件夹图片使用False(带文件名分隔符)
    """
    if not cache_dir.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        
    total = len(image_tasks)
    # 使用类型明确的初始化，消除某些 IDE 的类型警告
    results: list[str] = [""] * total
    usages = []

    def process_task(task):
        idx = task["index"]
        label = task["label"]
        cache_file = cache_dir / f"page_{idx+1}.json"
        
        # 1. 检查缓存
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    print(f"♻️  [{label}] 已从缓存读取")
                    return idx, cached_data['md_text'], cached_data.get('usage', {})
            except Exception:
                pass

        # 2. 获取数据 
        data_uri = task["get_data_uri"]()
        print(f"⏳ 正在识别 {idx+1}/{total} ({label})...")
        res = call_ocr_api_with_data(data_uri, label)
        md_text = clean_markdown_text(res.get("md_results", ""))
        usage = res.get("usage", {})
        
        # 3. 持久化
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({"md_text": md_text, "usage": usage}, f, ensure_ascii=False)
            
        return idx, md_text, usage

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
        future_to_task = {executor.submit(process_task, task): task for task in image_tasks}
        for future in as_completed(future_to_task):
            try:
                idx, md_text, usage = future.result()
                results[idx] = md_text
                usages.append(usage)
                print(f"✅ 处理完成: {image_tasks[idx]['label']}")
            except Exception as e:
                print(f"❌ 任务失败: {e}")

    # 合并结果
    full_markdown = ""
    for i, page_text in enumerate(results):
        if not page_text: continue
        page_text = page_text.strip()
        label = image_tasks[i]["label"]
        
        if not smart_merge:
            # 文件夹图片模式：统一使用 ### 文件名 作为每页标题
            header = f"### {label}\n\n"
            if not full_markdown:
                full_markdown = header + page_text
            else:
                full_markdown += "\n\n---\n\n" + header + page_text
        else:
            # PDF 智能合并模式
            if not full_markdown:
                full_markdown = page_text
            else:
                if page_text.startswith('#'):
                    full_markdown += "\n\n" + page_text
                else:
                    last_char = full_markdown[-1] if full_markdown else ""
                    first_char = page_text[0] if page_text else ""
                    if is_chinese_char(last_char) and is_chinese_char(first_char):
                        full_markdown += page_text
                    else:
                        full_markdown += " " + page_text
    
    total_usage = {
        "prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usages),
        "completion_tokens": sum(u.get("completion_tokens", 0) for u in usages),
        "total_tokens": sum(u.get("total_tokens", 0) for u in usages)
    }
    
    return full_markdown, total_usage

def process_pdf(pdf_path: str):
    path = Path(pdf_path)
    doc = fitz.open(pdf_path)
    # 缓存目录统一在当前执行命令的目录下
    cache_dir = Path.cwd() / f".{path.stem}_cache"
    
    tasks = []
    for i in range(len(doc)):
        def get_uri(p_num=i):
            page = doc.load_page(p_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            return get_image_base64(pix.tobytes("png"), "image/png")
        
        tasks.append({
            "index": i,
            "label": f"Page {i+1}",
            "get_data_uri": get_uri
        })
    
    return process_batch_concurrently(tasks, cache_dir, smart_merge=True)

def process_directory(dir_path: str):
    path = Path(dir_path)
    valid_suffixes = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}
    image_files = sorted([
        f for f in path.iterdir() 
        if f.is_file() and f.suffix.lower() in valid_suffixes
    ])
    
    if not image_files:
        raise Exception(f"目录中未找到支持的图片文件: {dir_path}")
    
    print(f"📸 文件夹模式: {path.name}, 发现 {len(image_files)} 张图片")
    # 缓存目录统一在当前执行命令的目录下
    cache_dir = Path.cwd() / f".{path.name}_cache"
    
    tasks = []
    for i, img_path in enumerate(image_files):
        def get_uri(p=img_path):
            mime_type, _ = mimetypes.guess_type(str(p))
            if not mime_type: mime_type = "image/png"
            with open(p, 'rb') as f:
                return get_image_base64(f.read(), mime_type)
        
        tasks.append({
            "index": i,
            "label": img_path.name,
            "get_data_uri": get_uri
        })
    
    return process_batch_concurrently(tasks, cache_dir, smart_merge=False)

def main():
    if len(sys.argv) < 2:
        print("使用方法: python zhipu_ocr.py <文件路径或目录>")
        sys.exit(1)
    
    # 环境检查
    check_environment()
    
    input_path = sys.argv[1]
    path = Path(input_path)
    
    if not path.exists():
        print(f"❌ 错误: 路径不存在 {input_path}")
        sys.exit(1)
    
    try:
        if path.is_dir():
            print(f"🚀 开始并发处理文件夹 (并发数: {MAX_CONCURRENCY})...")
            markdown_result, usage = process_directory(input_path)
        elif path.suffix.lower() == ".pdf":
            print(f"🚀 开始并发处理 PDF (并发数: {MAX_CONCURRENCY})...")
            markdown_result, usage = process_pdf(input_path)
        else:
            print("🔍 开始识别单张图片...")
            markdown_result, usage = process_single_image(input_path)
        
        # 输出与保存：统一保存在当前工作目录
        output_path = Path.cwd() / (path.stem + "_ocr_result.md")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_result)
        
        # 输出与保存
        print("\n" + "="*60)
        print("📝 OCR 处理完成")
        print("="*60)
        
        if usage:
            print(f"\n📊 总 Token 使用统计:")
            print(f"   - 输入: {usage.get('prompt_tokens')}")
            print(f"   - 输出: {usage.get('completion_tokens')}")
            print(f"   - 总计: {usage.get('total_tokens')}")
            
        print(f"\n✅ 结果已保存至: {output_path}")
        
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)



if __name__ == "__main__":
    main()
