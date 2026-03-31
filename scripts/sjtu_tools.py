#!/usr/bin/env python3
"""
交大在线工具集合
整合多个交大在线服务的入口和使用指引
"""

import sys
import requests
from bs4 import BeautifulSoup

# ============================================================
# 常量
# ============================================================

TIMEOUT = 10
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


# ============================================================
# 工具信息
# ============================================================

def _check_url(url: str) -> str:
    """检测 URL 是否可访问"""
    try:
        resp = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        if resp.status_code < 400:
            return "✅ 在线"
        return f"⚠️ HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return "❌ 无法连接 (可能需要校园网)"
    except Exception:
        return "❓ 未知状态"


def get_latex_info() -> str:
    """LaTeX 在线编辑器使用指引"""
    url = "https://latex.sjtu.edu.cn"
    status = _check_url(url)

    return f"""
╔══════════════════════════════════════════════════════════╗
║  📝 LaTeX 在线编辑器 (Overleaf)                          ║
╚══════════════════════════════════════════════════════════╝

  🔗 地址: {url}
  📊 状态: {status}

  📖 简介:
  交大自建的 Overleaf 实例，提供在线 LaTeX 编辑和编译。
  支持多人协作、实时预览、丰富的模板库。

  🔑 登录:
  使用 jAccount 账号登录

  💡 使用技巧:
  • 支持 SJTUThesis 论文模板（毕业论文/学位论文）
  • 支持 SJTUBeamer 演示文稿模板
  • 编译器推荐选择 XeLaTeX（中文支持更好）
  • 可从 GitHub 导入项目
  • 支持 Git 版本管理

  📦 常用模板:
  • SJTUThesis — 上海交通大学学位论文模板
  • SJTUBeamer — 交大风格 Beamer 演示模板
  • 课程报告模板 — 各类课程大作业
""".strip()


def get_notes_info() -> str:
    """水源文档使用指引"""
    url = "https://notes.sjtu.edu.cn"
    status = _check_url(url)

    return f"""
╔══════════════════════════════════════════════════════════╗
║  📄 水源文档 (CodiMD/HackMD)                             ║
╚══════════════════════════════════════════════════════════╝

  🔗 地址: {url}
  📊 状态: {status}

  📖 简介:
  交大自建的协作 Markdown 文档平台 (基于 CodiMD/HackMD)。
  支持实时多人协作编辑、Markdown 语法、数学公式。

  🔑 登录:
  使用 jAccount 账号登录

  💡 使用技巧:
  • 支持 Markdown + LaTeX 数学公式
  • 支持 Mermaid 流程图、时序图
  • 可设置文档权限（私有/可查看/可编辑）
  • 支持幻灯片模式 (用 --- 分隔幻灯片)
  • 适合课堂笔记、会议记录、小组讨论

  📝 快捷键:
  • Ctrl+B 加粗 | Ctrl+I 斜体
  • Ctrl+/ 切换编辑/预览模式
""".strip()


def get_ocr_info() -> str:
    """OCR 服务使用指引"""
    url = "https://ocr.sjtu.edu.cn"
    status = _check_url(url)

    return f"""
╔══════════════════════════════════════════════════════════╗
║  🔍 OCR 文字识别服务                                     ║
╚══════════════════════════════════════════════════════════╝

  🔗 地址: {url}
  📊 状态: {status}

  📖 简介:
  交大提供的在线 OCR (光学字符识别) 服务。
  支持图片中的文字提取，包括中英文、手写体等。

  🔑 登录:
  使用 jAccount 账号登录

  💡 使用场景:
  • 拍照提取课件/黑板上的文字
  • 扫描纸质文档转电子版
  • 识别 PDF 中的图片文字
  • 手写笔记数字化

  ⚠️ 注意:
  • 可能需要校园网环境
  • 识别准确率取决于图片质量
""".strip()


def get_tts_info() -> str:
    """文字转语音使用指引"""
    url = "https://speech.sjtu.edu.cn"
    status = _check_url(url)

    return f"""
╔══════════════════════════════════════════════════════════╗
║  🔊 文字转语音 (TTS) 服务                                ║
╚══════════════════════════════════════════════════════════╝

  🔗 地址: {url}
  📊 状态: {status}

  📖 简介:
  交大语音实验室提供的文字转语音 (Text-to-Speech) 服务。
  支持多种语言和语音风格。

  🔑 登录:
  使用 jAccount 账号登录

  💡 使用场景:
  • 论文/报告的语音版生成
  • 多语言发音参考
  • 无障碍辅助阅读
  • 语音合成研究
""".strip()


def get_ai_platform_info() -> str:
    """交大 AI 平台使用指引"""
    url = "https://my.sjtu.edu.cn/ai"
    status = _check_url(url)

    return f"""
╔══════════════════════════════════════════════════════════╗
║  🤖 交大 AI 平台                                         ║
╚══════════════════════════════════════════════════════════╝

  🔗 地址: {url}
  📊 状态: {status}

  📖 简介:
  交大为师生提供的 AI 对话平台，集成多个大语言模型。

  🔑 登录:
  使用 jAccount 账号登录

  💡 功能:
  • 支持多种 AI 模型 (GPT、文心一言等)
  • 免费使用，无需额外付费
  • 对话记录保存
  • 支持长文本处理

  🎓 使用建议:
  • 适合论文写作辅助、代码调试、翻译等
  • 注意学术诚信，AI 生成内容需标注
  • 敏感信息不要输入平台
""".strip()


def get_feedback_info() -> str:
    """生活服务反馈使用指引"""
    url = "https://feedback.sjtu.edu.cn"
    status = _check_url(url)

    return f"""
╔══════════════════════════════════════════════════════════╗
║  💬 生活服务反馈平台                                      ║
╚══════════════════════════════════════════════════════════╝

  🔗 地址: {url}
  📊 状态: {status}

  📖 简介:
  交大后勤及校园生活服务反馈平台。
  可以提交校园生活中遇到的各类问题和建议。

  🔑 登录:
  使用 jAccount 账号登录

  📋 可反馈的问题类型:
  • 宿舍维修 — 水电、家具、网络等
  • 食堂问题 — 菜品质量、价格、卫生等
  • 校园设施 — 教室、图书馆、运动场等
  • 交通出行 — 校车、道路、停车等
  • 安全问题 — 消防、治安等

  💡 提交技巧:
  • 描述问题时附上照片
  • 注明具体位置（楼号+房间号）
  • 一般 1-3 个工作日内会有回复
""".strip()


def get_all_tools() -> list[dict]:
    """列出所有可用工具"""
    tools = [
        {"name": "LaTeX 在线编辑器", "url": "https://latex.sjtu.edu.cn", "cmd": "latex",
         "desc": "Overleaf 在线 LaTeX 编辑器，支持多人协作"},
        {"name": "水源文档", "url": "https://notes.sjtu.edu.cn", "cmd": "notes",
         "desc": "协作 Markdown 文档平台 (CodiMD)"},
        {"name": "OCR 文字识别", "url": "https://ocr.sjtu.edu.cn", "cmd": "ocr",
         "desc": "图片文字识别服务"},
        {"name": "文字转语音", "url": "https://speech.sjtu.edu.cn", "cmd": "tts",
         "desc": "TTS 文字转语音服务"},
        {"name": "AI 平台", "url": "https://my.sjtu.edu.cn/ai", "cmd": "ai",
         "desc": "交大 AI 对话平台，多模型支持"},
        {"name": "生活服务反馈", "url": "https://feedback.sjtu.edu.cn", "cmd": "feedback",
         "desc": "校园生活问题反馈"},
        {"name": "jAccount", "url": "https://jaccount.sjtu.edu.cn", "cmd": "",
         "desc": "交大统一身份认证"},
        {"name": "教学信息服务网", "url": "https://i.sjtu.edu.cn", "cmd": "",
         "desc": "选课、成绩、课表查询"},
        {"name": "交大邮箱", "url": "https://mail.sjtu.edu.cn", "cmd": "",
         "desc": "交大企业邮箱 (Outlook)"},
        {"name": "交大云盘", "url": "https://pan.sjtu.edu.cn", "cmd": "",
         "desc": "Seafile 云存储服务"},
        {"name": "SJTUG 镜像站", "url": "https://mirror.sjtu.edu.cn", "cmd": "",
         "desc": "开源软件镜像 (pip/conda/brew/docker)"},
        {"name": "Canvas", "url": "https://oc.sjtu.edu.cn", "cmd": "",
         "desc": "课程管理系统 (作业/课件/成绩)"},
    ]
    return tools


# ============================================================
# 输出
# ============================================================

def print_all_tools():
    """打印所有工具列表"""
    tools = get_all_tools()
    print("\n🧰 交大在线工具集合")
    print("─" * 60)
    for i, tool in enumerate(tools, 1):
        cmd_hint = f" (命令: {tool['cmd']})" if tool.get("cmd") else ""
        print(f"  {i:>2}. {tool['name']}{cmd_hint}")
        print(f"      {tool['desc']}")
        print(f"      🔗 {tool['url']}")
    print()
    print("💡 使用 python3 sjtu_tools.py <命令> 查看详细信息")
    print("   例如: python3 sjtu_tools.py latex")
    print()


# ============================================================
# CLI
# ============================================================

def main():
    tool_map = {
        "latex": get_latex_info,
        "notes": get_notes_info,
        "ocr": get_ocr_info,
        "tts": get_tts_info,
        "ai": get_ai_platform_info,
        "feedback": get_feedback_info,
    }

    if len(sys.argv) < 2:
        print("用法: python3 sjtu_tools.py <命令>")
        print()
        print("命令:")
        print("  list      列出所有可用工具")
        print("  latex     LaTeX 在线编辑器")
        print("  notes     水源文档")
        print("  ocr       OCR 文字识别")
        print("  tts       文字转语音")
        print("  ai        交大 AI 平台")
        print("  feedback  生活服务反馈")
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "list":
        print_all_tools()
    elif cmd in tool_map:
        print(tool_map[cmd]())
    else:
        print(f"❌ 未知命令: {cmd}")
        print("运行 python3 sjtu_tools.py 查看帮助")
        sys.exit(1)


if __name__ == "__main__":
    main()
