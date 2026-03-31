#!/usr/bin/env python3
"""
SJTU 正版软件列表查询工具
目标网站: https://software.sjtu.edu.cn/List/rjlb

该网站为服务器端渲染（SSR），可以直接用 requests + BeautifulSoup 爬取。
HTML 结构:
  div.all-li > a > div.li-tt > h4 (软件名称)
  div.all-li > a > div.li-tt > span (软件类别)
  div.all-li > a > div.li-tt > p (软件描述)
  div.all-li > a[href] (详情链接)

用法:
    python3 sjtu_software.py list
    python3 sjtu_software.py search "MATLAB"
"""

import argparse
import sys
import json
from typing import List, Dict, Optional

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

SOFTWARE_URL = "https://software.sjtu.edu.cn/List/rjlb"
BASE_URL = "https://software.sjtu.edu.cn"

# 类别样式到中文的映射（从 HTML class 名推断）
CATEGORY_CLASSES = {
    "": "系统软件",
    "ban": "办公软件",
    "xue": "科学计算",
    "sha": "网络安全",
}


def fetch_software_list() -> List[Dict]:
    """
    从 software.sjtu.edu.cn 爬取正版软件列表。
    
    Returns:
        软件信息列表，每项包含 name, category, description, url
    """
    if not HAS_DEPS:
        print("⚠️  需要安装依赖: pip install requests beautifulsoup4")
        return _get_fallback_data()

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        resp = requests.get(SOFTWARE_URL, headers=headers, timeout=10)
        resp.encoding = "utf-8"

        if resp.status_code != 200:
            print(f"⚠️  请求失败: HTTP {resp.status_code}")
            return _get_fallback_data()

        soup = BeautifulSoup(resp.text, "html.parser")
        software_list = []

        # 解析 HTML 结构: div.all-li 包含每个软件条目
        for item in soup.select("div.all-li"):
            link = item.find("a")
            if not link:
                continue

            title_div = item.select_one("div.li-tt")
            if not title_div:
                continue

            # 提取软件名称
            h4 = title_div.find("h4")
            name = h4.get_text(strip=True) if h4 else "未知"

            # 提取类别
            span = title_div.find("span")
            category = span.get_text(strip=True) if span else "其他"

            # 提取描述
            p = title_div.find("p")
            description = p.get_text(strip=True) if p else ""

            # 提取链接
            href = link.get("href", "")
            url = f"{BASE_URL}{href}" if href.startswith("/") else href

            # 提取图标
            img = item.find("img")
            icon = img.get("src", "") if img else ""
            if icon.startswith("/"):
                icon = f"{BASE_URL}{icon}"

            software_list.append({
                "name": name,
                "category": category,
                "description": description,
                "url": url,
                "icon": icon,
            })

        if software_list:
            return software_list
        else:
            print("⚠️  未能从页面解析到软件数据，使用缓存数据")
            return _get_fallback_data()

    except requests.RequestException as e:
        print(f"⚠️  网络请求失败: {e}")
        return _get_fallback_data()
    except Exception as e:
        print(f"⚠️  解析失败: {e}")
        return _get_fallback_data()


def _get_fallback_data() -> List[Dict]:
    """返回硬编码的软件数据作为备用"""
    return [
        {
            "name": "微软Windows操作系统",
            "category": "系统软件",
            "description": "微软Windows操作系统是由美国Microsoft公司以图形用户界面为基础研发的操作系统，最新版本为Windows11",
            "url": f"{BASE_URL}/List/windows/11",
        },
        {
            "name": "微软Office办公软件",
            "category": "办公软件",
            "description": "微软Office是由美国Microsoft公司开发的办公软件套装，常用组件有 Word、Excel、PowerPoint、Outlook、OneNote等",
            "url": f"{BASE_URL}/List/Office/2021",
        },
        {
            "name": "WPS Office",
            "category": "办公软件",
            "description": "WPS Office是由北京金山办公软件公司自主研发的办公软件套装，兼容Word、Excel、PowerPoint三大办公组件的不同格式",
            "url": f"{BASE_URL}/List/wpsoffice/wpsoffice",
        },
        {
            "name": "福昕高级PDF编辑器",
            "category": "办公软件",
            "description": "福昕高级PDF编辑器是由福建福昕软件公司研发的专业级PDF编辑工具，涵盖了PDF编辑，格式转换，合并分拆，加密等诸多功能",
            "url": f"{BASE_URL}/List/Foxit/PDF",
        },
        {
            "name": "MATLAB",
            "category": "科学计算",
            "description": "MATLAB是由美国MathWorks公司出品的商业数学软件",
            "url": f"{BASE_URL}/List/MATLAB/R2024",
        },
        {
            "name": "Labview",
            "category": "科学计算",
            "description": "LabVIEW是由美国国家仪器（NI）公司研制开发的程序开发环境",
            "url": f"{BASE_URL}/List/Labview/Labview",
        },
        {
            "name": "ChemDraw",
            "category": "科学计算",
            "description": "ChemDraw是由美国Revvity公司出品的一款化学结构绘图软件",
            "url": f"{BASE_URL}/List/ChemDraw/ChemDraw",
        },
        {
            "name": "Siemens NX",
            "category": "科学计算",
            "description": "Siemens NX是由德国Siemens PLM软件公司开发的一款数字化设计与仿真软件",
            "url": f"{BASE_URL}/List/SiemensNX/SiemensNX",
        },
        {
            "name": "Gaussian",
            "category": "科学计算",
            "description": "Gaussian是由美国Gaussian Inc.公司研发的一款量子化学软件",
            "url": f"{BASE_URL}/List/Gaussian/Gaussian",
        },
        {
            "name": "ESET NOD32",
            "category": "网络安全",
            "description": "ESET NOD32 是由斯洛伐克ESET公司推出的一款防病毒软件",
            "url": f"{BASE_URL}/List/ESET/ESET",
        },
        {
            "name": "金山文档",
            "category": "办公软件",
            "description": "金山文档是由北京金山办公软件公司推出的在线合作办公软件，绑定激活交大企业账号可享有交大专属存储空间",
            "url": f"{BASE_URL}/List/jinshan/doc",
        },
        {
            "name": "北太天元",
            "category": "科学计算",
            "description": "北太天元是由北太振寰公司出品的国产数值计算通用软件，提供科学计算、可视化交互式程序设计",
            "url": f"{BASE_URL}/List/Baltamatica/Baltamatica",
        },
        {
            "name": "VirtualBox",
            "category": "系统软件",
            "description": "VirtualBox是由美国Oracle公司推出的开源虚拟机软件，可虚拟的系统包括Windows, Mac, Linux等",
            "url": f"{BASE_URL}/List/VirtualBox/VirtualBox",
        },
    ]


def list_software() -> List[Dict]:
    """列出所有可用软件"""
    return fetch_software_list()


def search_software(keyword: str) -> List[Dict]:
    """
    搜索软件。
    
    Args:
        keyword: 搜索关键词
    
    Returns:
        匹配的软件列表
    """
    all_software = fetch_software_list()
    keyword_lower = keyword.lower()
    
    results = []
    for sw in all_software:
        searchable = (
            sw["name"].lower()
            + sw["category"].lower()
            + sw["description"].lower()
        )
        if keyword_lower in searchable:
            results.append(sw)
    
    return results


def print_software(sw: Dict, index: int = 0):
    """格式化输出软件信息"""
    prefix = f"{index:>2}. " if index > 0 else "  "
    print(f"{prefix}💿 {sw['name']}")
    print(f"      类别: {sw['category']}")
    print(f"      描述: {sw['description']}")
    if sw.get("url"):
        print(f"      链接: {sw['url']}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="SJTU 正版软件列表查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 sjtu_software.py list                 # 列出所有正版软件
  python3 sjtu_software.py search "MATLAB"      # 搜索软件
  python3 sjtu_software.py search "办公"         # 按类别搜索
  python3 sjtu_software.py list --json           # JSON 格式输出

网站: https://software.sjtu.edu.cn/List/rjlb
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="操作类型")

    # list 子命令
    list_parser = subparsers.add_parser("list", help="列出所有正版软件")
    list_parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    list_parser.add_argument("--category", "-c", help="按类别筛选")

    # search 子命令
    search_parser = subparsers.add_parser("search", help="搜索软件")
    search_parser.add_argument("keyword", help="搜索关键词")
    search_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    args = parser.parse_args()

    if args.command == "list":
        software = list_software()

        if hasattr(args, "category") and args.category:
            software = [s for s in software if args.category in s["category"]]

        if args.json:
            print(json.dumps(software, ensure_ascii=False, indent=2))
        else:
            print(f"\n🖥️  上海交通大学正版软件列表")
            print(f"{'─'*60}")

            # 按类别分组
            categories = {}
            for sw in software:
                cat = sw["category"]
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(sw)

            for cat, cat_software in categories.items():
                print(f"\n📁 {cat} ({len(cat_software)} 款)")
                print(f"   {'─'*50}")
                for sw in cat_software:
                    desc = sw["description"][:50] + "..." if len(sw["description"]) > 50 else sw["description"]
                    print(f"   • {sw['name']:<20} {desc}")

            print(f"\n共 {len(software)} 款正版软件可用")
            print(f"下载地址: {SOFTWARE_URL}")

    elif args.command == "search":
        results = search_software(args.keyword)

        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(f"\n🔍 搜索: {args.keyword}")
            print(f"{'─'*60}")

            if results:
                print(f"找到 {len(results)} 款相关软件:\n")
                for i, sw in enumerate(results, 1):
                    print_software(sw, i)
            else:
                print(f"未找到与 \"{args.keyword}\" 相关的软件")
                print(f"\n💡 提示: 访问 {SOFTWARE_URL} 查看完整列表")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
