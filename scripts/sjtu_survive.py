#!/usr/bin/env python3
"""
上海交通大学生存手册搜索工具
目标: https://survivesjtu.gitbook.io/survivesjtumanual/
功能: 目录浏览、章节内容获取、关键词搜索
"""

import sys
import re
from typing import Optional
from urllib.parse import quote

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

BASE_URL = "https://survivesjtu.gitbook.io/survivesjtumanual"

# 硬编码目录结构 (基于生存手册实际内容)
TOC = {
    "前言": {
        "url": f"{BASE_URL}",
        "children": {}
    },
    "立志篇": {
        "url": f"{BASE_URL}/li-zhi-pian",
        "children": {
            "欢迎来到上海交通大学": f"{BASE_URL}/li-zhi-pian/huan-ying-lai-dao-shang-hai-jiao-tong-da-xue",
            "关于失败": f"{BASE_URL}/li-zhi-pian/guan-yu-shi-bai",
            "你想要什么": f"{BASE_URL}/li-zhi-pian/ni-xiang-yao-shi-mo",
        }
    },
    "生存技巧": {
        "url": f"{BASE_URL}/sheng-cun-ji-qiao",
        "children": {
            "选课": f"{BASE_URL}/sheng-cun-ji-qiao/xuan-ke",
            "旁听": f"{BASE_URL}/sheng-cun-ji-qiao/pang-ting",
            "GPA": f"{BASE_URL}/sheng-cun-ji-qiao/gpa",
            "社团": f"{BASE_URL}/sheng-cun-ji-qiao/she-tuan",
            "竞赛": f"{BASE_URL}/sheng-cun-ji-qiao/jing-sai",
        }
    },
    "升学与就业": {
        "url": f"{BASE_URL}/sheng-xue-yu-jiu-ye",
        "children": {
            "保研": f"{BASE_URL}/sheng-xue-yu-jiu-ye/bao-yan",
            "考研": f"{BASE_URL}/sheng-xue-yu-jiu-ye/kao-yan",
            "出国": f"{BASE_URL}/sheng-xue-yu-jiu-ye/chu-guo",
            "就业": f"{BASE_URL}/sheng-xue-yu-jiu-ye/jiu-ye",
            "考公": f"{BASE_URL}/sheng-xue-yu-jiu-ye/kao-gong",
        }
    },
    "学术篇": {
        "url": f"{BASE_URL}/xue-shu-pian",
        "children": {
            "科研入门": f"{BASE_URL}/xue-shu-pian/ke-yan-ru-men",
            "转专业": f"{BASE_URL}/xue-shu-pian/zhuan-zhuan-ye",
            "读研": f"{BASE_URL}/xue-shu-pian/du-yan",
        }
    },
    "生活篇": {
        "url": f"{BASE_URL}/sheng-huo-pian",
        "children": {
            "心理健康": f"{BASE_URL}/sheng-huo-pian/xin-li-jian-kang",
            "恋爱": f"{BASE_URL}/sheng-huo-pian/lian-ai",
            "租房": f"{BASE_URL}/sheng-huo-pian/zu-fang",
        }
    },
    "写在最后": {
        "url": f"{BASE_URL}/xie-zai-zui-hou",
        "children": {}
    },
}


# ============================================================
# 目录
# ============================================================

def get_toc() -> dict:
    """获取生存手册目录结构 (优先爬取，降级硬编码)"""
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # gitbook 侧边栏目录
        nav = soup.find("nav") or soup.find("aside")
        if nav:
            links = nav.find_all("a", href=True)
            if len(links) > 3:
                toc_live = {}
                for a in links:
                    text = a.get_text(strip=True)
                    href = a["href"]
                    if text and len(text) > 1:
                        if not href.startswith("http"):
                            href = BASE_URL.rstrip("/") + "/" + href.lstrip("/")
                        toc_live[text] = href
                if toc_live:
                    return {"source": "live", "items": toc_live}
    except Exception:
        pass

    return {"source": "hardcoded", "items": TOC}


# ============================================================
# 章节内容
# ============================================================

def get_section(section_name: str) -> Optional[str]:
    """获取某个章节的内容"""
    # 在硬编码目录中查找 URL
    url = _find_section_url(section_name)
    if not url:
        return f"❌ 未找到章节: {section_name}\n💡 运行 python3 sjtu_survive.py toc 查看目录"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # gitbook 页面内容区域
        content_area = (
            soup.find("main") or
            soup.find("article") or
            soup.find("div", class_=re.compile(r"content|page|body", re.I))
        )

        if content_area:
            # 清理多余元素
            for tag in content_area.find_all(["nav", "aside", "header", "footer", "script", "style"]):
                tag.decompose()
            text = content_area.get_text("\n", strip=True)
            # 清理多余空行
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text[:5000]  # 限制长度

        # 降级: 返回纯文本
        text = soup.get_text("\n", strip=True)
        return text[:3000]

    except Exception as e:
        return f"⚠️ 获取章节内容失败: {e}\n🔗 请直接访问: {url}"


def _find_section_url(name: str) -> Optional[str]:
    """在目录中查找章节 URL"""
    name_lower = name.lower()
    for chapter, info in TOC.items():
        if name_lower in chapter.lower():
            return info["url"]
        children = info.get("children", {})
        for child_name, child_url in children.items():
            if name_lower in child_name.lower():
                return child_url
    return None


# ============================================================
# 搜索
# ============================================================

def search_handbook(keyword: str) -> list[dict]:
    """搜索生存手册内容"""
    results = []
    keyword_lower = keyword.lower()

    # 1. 在硬编码目录中搜索标题
    for chapter, info in TOC.items():
        if keyword_lower in chapter.lower():
            results.append({
                "title": chapter,
                "url": info["url"],
                "type": "章节",
                "match": "标题匹配",
            })
        children = info.get("children", {})
        for child_name, child_url in children.items():
            if keyword_lower in child_name.lower():
                results.append({
                    "title": f"{chapter} > {child_name}",
                    "url": child_url,
                    "type": "子章节",
                    "match": "标题匹配",
                })

    # 2. 尝试在每个章节页面内容中搜索（带总超时保护）
    if len(results) < 3:
        import time
        search_start = time.time()
        MAX_SEARCH_TIME = 15  # 最多花15秒搜索页面内容

        for chapter, info in TOC.items():
            if time.time() - search_start > MAX_SEARCH_TIME:
                break
            children = info.get("children", {})
            urls_to_check = [(chapter, info["url"])]
            urls_to_check += [(f"{chapter} > {k}", v) for k, v in children.items()]

            for title, url in urls_to_check:
                if time.time() - search_start > MAX_SEARCH_TIME:
                    break
                if any(r["url"] == url for r in results):
                    continue
                try:
                    resp = requests.get(url, headers=HEADERS, timeout=5)
                    if resp.status_code == 200 and keyword_lower in resp.text.lower():
                        # 提取匹配上下文
                        text = BeautifulSoup(resp.text, "html.parser").get_text()
                        idx = text.lower().find(keyword_lower)
                        if idx >= 0:
                            start = max(0, idx - 30)
                            end = min(len(text), idx + len(keyword) + 50)
                            snippet = text[start:end].replace("\n", " ").strip()
                            results.append({
                                "title": title,
                                "url": url,
                                "type": "内容",
                                "match": f"...{snippet}...",
                            })
                except Exception:
                    continue

                if len(results) >= 10:
                    break
            if len(results) >= 10:
                break

        if not results:
            # gitbook 可能被墙或加载慢，给一个提示
            results.append({
                "title": f"在线搜索 \"{keyword}\"",
                "url": f"{BASE_URL}",
                "type": "提示",
                "match": "未在本地章节中找到匹配，建议直接访问网站搜索",
            })

    return results


# ============================================================
# 输出
# ============================================================

def print_toc():
    """打印目录"""
    toc = get_toc()
    print(f"\n📖 上海交通大学生存手册")
    print(f"   {BASE_URL}")
    print(f"   数据来源: {'在线' if toc['source'] == 'live' else '硬编码'}")
    print("─" * 60)

    if toc["source"] == "live":
        for name, url in toc["items"].items():
            print(f"  • {name}")
            print(f"    🔗 {url}")
    else:
        for chapter, info in toc["items"].items():
            print(f"\n  📂 {chapter}")
            print(f"     🔗 {info['url']}")
            children = info.get("children", {})
            for child_name, child_url in children.items():
                print(f"     ├─ {child_name}")
    print()


def print_search(keyword: str):
    """打印搜索结果"""
    results = search_handbook(keyword)
    print(f"\n🔍 搜索: \"{keyword}\"")
    print("─" * 60)
    if not results:
        print(f"  未找到与 \"{keyword}\" 相关的内容")
        print(f"  💡 建议直接访问: {BASE_URL}")
    else:
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r['type']}] {r['title']}")
            if r.get("match") and r["match"] != "标题匹配":
                print(f"     📝 {r['match']}")
            print(f"     🔗 {r['url']}")
    print()


def print_section(name: str):
    """打印章节内容"""
    print(f"\n📖 章节: {name}")
    print("─" * 60)
    content = get_section(name)
    print(content)
    print()


# ============================================================
# CLI
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("用法: python3 sjtu_survive.py <命令> [参数]")
        print()
        print("命令:")
        print("  toc              查看目录结构")
        print("  search <关键词>  搜索手册内容")
        print("  read <章节名>    阅读章节内容")
        print()
        print("示例:")
        print('  python3 sjtu_survive.py search "转专业"')
        print('  python3 sjtu_survive.py read "保研"')
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "toc":
        print_toc()
    elif cmd == "search":
        if len(sys.argv) < 3:
            print("❌ 请提供搜索关键词")
            sys.exit(1)
        print_search(sys.argv[2])
    elif cmd == "read":
        if len(sys.argv) < 3:
            print("❌ 请提供章节名")
            sys.exit(1)
        print_section(sys.argv[2])
    else:
        print(f"❌ 未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
