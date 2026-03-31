#!/usr/bin/env python3
"""
手写风格 PDF 生成器

将文本内容渲染为逼真的手写 PDF，支持：
- 中文手写字体渲染
- 随机字间距、行间距抖动
- 随机字体大小微调
- 随机倾斜角度
- 墨水深浅变化
- 支持数学公式（纯文本格式）
- 信纸/白纸背景

用法:
  python3 handwrite_pdf.py <input.txt> <output.pdf> [--style casual|neat|messy]
  python3 handwrite_pdf.py --text "要写的内容" <output.pdf>
"""

import os
import sys
import random
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from handright import Template, handwrite

# 字体路径（优先级: 自定义手写体 > 楷体 > 宋体）
FONT_CANDIDATES = [
    os.path.expanduser("~/.openclaw/workspace/skills/sjtu-canvas/fonts/MaokenYingBiKaiShu.ttf"),  # 猫啃硬笔楷书（最逼真）
    os.path.expanduser("~/.openclaw/workspace/skills/sjtu-canvas/fonts/ZCOOLKuaiLe-Regular.ttf"),  # 站酷快乐体（备选）
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]

def find_font():
    """找到可用的中文字体"""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                ImageFont.truetype(path, 30, index=0)
                return path
            except:
                continue
    raise FileNotFoundError("找不到可用的中文字体")


def generate_handwrite_images(text, style="casual"):
    """
    使用 handright 生成手写风格图片

    style: casual(随意), neat(工整), messy(潦草)
    """
    font_path = find_font()

    # 不同风格的参数
    styles = {
        "neat": {
            "font_size": 40,
            "word_spacing": 3,
            "line_spacing": 72,
            "word_spacing_sigma": 1,
            "line_spacing_sigma": 2,
            "font_size_sigma": 0.5,
            "perturb_x_sigma": 1,
            "perturb_y_sigma": 1,
            "perturb_theta_sigma": 0.01,
        },
        "casual": {
            "font_size": 38,
            "word_spacing": 4,
            "line_spacing": 70,
            "word_spacing_sigma": 3,
            "line_spacing_sigma": 4,
            "font_size_sigma": 1,
            "perturb_x_sigma": 3,
            "perturb_y_sigma": 3,
            "perturb_theta_sigma": 0.03,
        },
        "messy": {
            "font_size": 36,
            "word_spacing": 5,
            "line_spacing": 68,
            "word_spacing_sigma": 5,
            "line_spacing_sigma": 6,
            "font_size_sigma": 2,
            "perturb_x_sigma": 5,
            "perturb_y_sigma": 5,
            "perturb_theta_sigma": 0.05,
        },
    }

    s = styles.get(style, styles["casual"])

    template = Template(
        background=Image.new("RGB", (2480, 3508), "white"),  # A4 300dpi
        font=ImageFont.truetype(font_path, size=s["font_size"], index=0),
        line_spacing=s["line_spacing"],
        word_spacing=s["word_spacing"],
        left_margin=200,
        top_margin=230,
        right_margin=200,
        bottom_margin=200,
        word_spacing_sigma=s["word_spacing_sigma"],
        line_spacing_sigma=s["line_spacing_sigma"],
        font_size_sigma=s["font_size_sigma"],
        perturb_x_sigma=s["perturb_x_sigma"],
        perturb_y_sigma=s["perturb_y_sigma"],
        perturb_theta_sigma=s["perturb_theta_sigma"],
    )

    images = handwrite(text, template)
    return list(images)


def add_paper_texture(image):
    """添加轻微的纸张纹理"""
    draw = ImageDraw.Draw(image)
    width, height = image.size

    # 随机添加几条淡淡的水平线（模拟横线纸）
    # 不加线 = 白纸效果
    return image


def add_ruled_lines(image, line_spacing=58, top_margin=230, left_margin=150, right_margin=150):
    """添加信纸横线"""
    draw = ImageDraw.Draw(image)
    width, height = image.size

    y = top_margin + line_spacing
    while y < height - 200:
        # 淡蓝色横线
        draw.line(
            [(left_margin, y), (width - right_margin, y)],
            fill=(200, 220, 240),
            width=1
        )
        y += line_spacing

    return image


def images_to_pdf(images, output_path, add_ruled=False):
    """将图片列表保存为 PDF"""
    if not images:
        raise ValueError("没有图片可保存")

    processed = []
    for img in images:
        if add_ruled:
            img = add_ruled_lines(img.copy())
        # 转为 RGB（确保兼容）
        if img.mode != "RGB":
            img = img.convert("RGB")
        processed.append(img)

    # 保存为 PDF
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if len(processed) == 1:
        processed[0].save(output_path, "PDF", resolution=300)
    else:
        processed[0].save(
            output_path, "PDF", resolution=300,
            save_all=True, append_images=processed[1:]
        )

    return output_path


def text_to_handwrite_pdf(text, output_path, style="casual", ruled=False):
    """
    一步到位：文本 → 手写风格 PDF

    参数:
        text: 要写的文本内容
        output_path: PDF 保存路径
        style: casual/neat/messy
        ruled: 是否添加信纸横线
    """
    print(f"📝 生成手写 PDF (风格: {style})...")

    # 预处理文本
    # 确保每行不太长（模拟手写换行）
    processed_lines = []
    for line in text.split("\n"):
        if not line.strip():
            processed_lines.append("")
            continue
        # 长行自动折行（约 28 个中文字符一行）
        while len(line) > 30:
            processed_lines.append(line[:30])
            line = line[30:]
        processed_lines.append(line)

    processed_text = "\n".join(processed_lines)

    images = generate_handwrite_images(processed_text, style)
    pdf_path = images_to_pdf(images, os.path.abspath(output_path), add_ruled=ruled)

    file_size = os.path.getsize(pdf_path)
    print(f"✅ 已生成: {pdf_path} ({len(images)} 页, {file_size/1024:.1f} KB)")
    return pdf_path


# ===== CLI =====
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="手写风格 PDF 生成器")
    parser.add_argument("input", nargs="?", help="输入文本文件路径")
    parser.add_argument("output", nargs="?", default="output.pdf", help="输出 PDF 路径")
    parser.add_argument("--text", "-t", help="直接传入文本内容")
    parser.add_argument("--style", "-s", choices=["casual", "neat", "messy"], default="casual", help="手写风格")
    parser.add_argument("--ruled", "-r", action="store_true", help="添加信纸横线")

    args = parser.parse_args()

    if args.text:
        text = args.text
    elif args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        print("请提供输入文件或 --text 参数")
        sys.exit(1)

    text_to_handwrite_pdf(text, args.output, style=args.style, ruled=args.ruled)
