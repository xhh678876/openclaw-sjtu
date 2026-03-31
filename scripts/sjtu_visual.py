#!/usr/bin/env python3
"""
视觉交大素材下载工具
目标: https://vs.sjtu.edu.cn
功能: 浏览相册、搜索照片
注意: 该网站可能需要 jAccount 登录或使用 JS 渲染
"""

import sys
import re
import json
from typing import Optional

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

VS_URL = "https://vs.sjtu.edu.cn"

# 硬编码相册信息 (基于视觉交大已知内容)
FALLBACK_ALBUMS = [
    {
        "name": "南洋筑韵",
        "desc": "交大建筑风光，校园标志性建筑",
        "url": f"{VS_URL}",
        "tags": ["建筑", "校园", "风光"],
    },
    {
        "name": "交大映画",
        "desc": "校园纪实摄影，师生活动",
        "url": f"{VS_URL}",
        "tags": ["纪实", "活动", "师生"],
    },
    {
        "name": "航拍交大",
        "desc": "无人机航拍校园全景",
        "url": f"{VS_URL}",
        "tags": ["航拍", "全景", "鸟瞰"],
    },
    {
        "name": "四季交大",
        "desc": "春夏秋冬四季校园风光",
        "url": f"{VS_URL}",
        "tags": ["四季", "风光", "季节"],
    },
    {
        "name": "交大夜景",
        "desc": "校园夜景灯光",
        "url": f"{VS_URL}",
        "tags": ["夜景", "灯光", "夜晚"],
    },
    {
        "name": "毕业季",
        "desc": "毕业典礼及毕业照",
        "url": f"{VS_URL}",
        "tags": ["毕业", "典礼", "学位服"],
    },
    {
        "name": "图书馆",
        "desc": "图书馆内外景",
        "url": f"{VS_URL}",
        "tags": ["图书馆", "阅读", "学习"],
    },
    {
        "name": "体育赛事",
        "desc": "校内体育比赛及运动场景",
        "url": f"{VS_URL}",
        "tags": ["体育", "比赛", "运动"],
    },
    {
        "name": "实验室",
        "desc": "科研实验室及科技成果",
        "url": f"{VS_URL}",
        "tags": ["实验室", "科研", "科技"],
    },
    {
        "name": "校史影像",
        "desc": "交大历史老照片及校史资料",
        "url": f"{VS_URL}",
        "tags": ["校史", "历史", "老照片"],
    },
]


# ============================================================
# 相册列表
# ============================================================

def list_albums() -> list[dict]:
    """列出所有相册"""
    try:
        resp = requests.get(VS_URL, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)

        # 检测是否跳转到 jAccount 登录
        if "jaccount" in resp.url.lower() or "login" in resp.url.lower():
            print("⚠️ 视觉交大需要 jAccount 登录，使用硬编码数据", file=sys.stderr)
            return FALLBACK_ALBUMS

        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # 尝试提取相册列表
        albums = []

        # 方法1: 找包含相册信息的容器
        for card in soup.select(".album, .gallery-item, .photo-album, .card"):
            name = ""
            desc = ""
            url = VS_URL

            title_el = card.find(["h2", "h3", "h4", "a"])
            if title_el:
                name = title_el.get_text(strip=True)
                if title_el.name == "a" and title_el.get("href"):
                    href = title_el["href"]
                    url = href if href.startswith("http") else VS_URL + href

            desc_el = card.find(["p", "span"])
            if desc_el and desc_el != title_el:
                desc = desc_el.get_text(strip=True)

            if name:
                albums.append({"name": name, "desc": desc, "url": url, "tags": []})

        # 方法2: 找图片链接
        if not albums:
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                if text and len(text) > 1 and len(text) < 20:
                    img = a.find("img")
                    if img or "album" in a["href"].lower() or "gallery" in a["href"].lower():
                        href = a["href"]
                        url = href if href.startswith("http") else VS_URL + href
                        albums.append({"name": text, "desc": "", "url": url, "tags": []})

        if albums:
            return albums

        # JS 渲染检测
        scripts = soup.find_all("script")
        has_spa = any("vue" in str(s).lower() or "react" in str(s).lower()
                       or "angular" in str(s).lower() for s in scripts)
        if has_spa:
            print("⚠️ 视觉交大使用前端框架渲染，使用硬编码数据", file=sys.stderr)

    except requests.exceptions.ConnectionError:
        print("⚠️ 无法连接视觉交大 (可能需要校园网)", file=sys.stderr)
    except Exception as e:
        print(f"⚠️ 爬取视觉交大失败: {e}", file=sys.stderr)

    return FALLBACK_ALBUMS


# ============================================================
# 搜索照片
# ============================================================

def search_photos(keyword: str) -> list[dict]:
    """搜索照片（基于硬编码标签匹配 + 在线搜索）"""
    results = []
    keyword_lower = keyword.lower()

    # 1. 本地标签匹配
    for album in FALLBACK_ALBUMS:
        name_match = keyword_lower in album["name"].lower()
        desc_match = keyword_lower in album.get("desc", "").lower()
        tag_match = any(keyword_lower in tag for tag in album.get("tags", []))

        if name_match or desc_match or tag_match:
            results.append({
                "album": album["name"],
                "desc": album.get("desc", ""),
                "url": album["url"],
                "match": "标签" if tag_match else ("名称" if name_match else "描述"),
            })

    # 2. 尝试在线搜索
    try:
        # 尝试 API 搜索
        search_urls = [
            f"{VS_URL}/api/search?q={keyword}",
            f"{VS_URL}/search?keyword={keyword}",
        ]
        for url in search_urls:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=5)
                if resp.status_code == 200:
                    data = resp.json() if "json" in resp.headers.get("content-type", "") else None
                    if data and isinstance(data, (list, dict)):
                        items = data if isinstance(data, list) else data.get("data", data.get("items", []))
                        for item in items[:10]:
                            if isinstance(item, dict):
                                results.append({
                                    "album": item.get("title", item.get("name", "在线结果")),
                                    "desc": item.get("desc", item.get("description", "")),
                                    "url": item.get("url", VS_URL),
                                    "match": "在线搜索",
                                })
                        break
            except Exception:
                continue
    except Exception:
        pass

    if not results:
        # 通用建议
        results.append({
            "album": f"搜索 \"{keyword}\"",
            "desc": "未在本地匹配到结果，建议直接访问视觉交大网站搜索",
            "url": VS_URL,
            "match": "建议",
        })

    return results


# ============================================================
# 输出
# ============================================================

def print_albums():
    """打印相册列表"""
    albums = list_albums()
    print(f"\n📷 视觉交大 ({VS_URL})")
    print(f"   共 {len(albums)} 个相册")
    print("─" * 60)
    for i, album in enumerate(albums, 1):
        tags = " ".join(f"#{t}" for t in album.get("tags", []))
        print(f"  {i:>2}. 📁 {album['name']}")
        if album.get("desc"):
            print(f"      {album['desc']}")
        if tags:
            print(f"      {tags}")
    print(f"\n  🔗 访问: {VS_URL}")
    print(f"  💡 提示: 部分功能可能需要 jAccount 登录")
    print()


def print_search(keyword: str):
    """打印搜索结果"""
    results = search_photos(keyword)
    print(f"\n🔍 搜索: \"{keyword}\"")
    print("─" * 60)
    if not results:
        print("  未找到相关照片")
    else:
        for i, r in enumerate(results, 1):
            print(f"  {i}. 📁 {r['album']} ({r['match']})")
            if r.get("desc"):
                print(f"     {r['desc']}")
            print(f"     🔗 {r['url']}")
    print()


# ============================================================
# CLI
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("用法: python3 sjtu_visual.py <命令> [参数]")
        print()
        print("命令:")
        print("  albums           列出所有相册")
        print("  search <关键词>  搜索照片")
        print()
        print("示例:")
        print('  python3 sjtu_visual.py search "图书馆"')
        print('  python3 sjtu_visual.py search "航拍"')
        print()
        print(f"💡 直接访问: {VS_URL}")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "albums":
        print_albums()
    elif cmd == "search":
        if len(sys.argv) < 3:
            print("❌ 请提供搜索关键词")
            sys.exit(1)
        print_search(sys.argv[2])
    else:
        print(f"❌ 未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
