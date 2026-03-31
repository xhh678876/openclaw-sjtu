#!/usr/bin/env python3
"""
SJTUG 镜像源换源工具
目标: https://mirror.sjtu.edu.cn
功能: 列出可用镜像、生成换源配置、自动换源
"""

import sys
import json
import requests
from bs4 import BeautifulSoup

# ============================================================
# 常量
# ============================================================

MIRROR_BASE = "https://mirror.sjtu.edu.cn"
TIMEOUT = 10
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 硬编码的镜像列表（降级用）
FALLBACK_MIRRORS = [
    {"name": "pypi", "url": "https://mirror.sjtu.edu.cn/pypi/web/simple", "desc": "PyPI 软件包"},
    {"name": "anaconda", "url": "https://mirror.sjtu.edu.cn/anaconda", "desc": "Anaconda 仓库"},
    {"name": "homebrew-bottles", "url": "https://mirror.sjtu.edu.cn/homebrew-bottles", "desc": "Homebrew Bottles"},
    {"name": "docker-registry", "url": "https://docker.mirrors.sjtug.sjtu.edu.cn", "desc": "Docker Hub 镜像"},
    {"name": "ubuntu", "url": "https://mirror.sjtu.edu.cn/ubuntu", "desc": "Ubuntu 软件源"},
    {"name": "debian", "url": "https://mirror.sjtu.edu.cn/debian", "desc": "Debian 软件源"},
    {"name": "npm", "url": "https://mirror.sjtu.edu.cn/npm-registry", "desc": "npm 软件包"},
    {"name": "crates.io", "url": "https://mirror.sjtu.edu.cn/crates.io-index", "desc": "Rust crates"},
    {"name": "ghcup", "url": "https://mirror.sjtu.edu.cn/ghcup", "desc": "GHCup (Haskell)"},
    {"name": "rust-static", "url": "https://mirror.sjtu.edu.cn/rust-static", "desc": "Rust 工具链"},
    {"name": "nix-channels", "url": "https://mirror.sjtu.edu.cn/nix-channels", "desc": "Nix Channels"},
    {"name": "flathub", "url": "https://mirror.sjtu.edu.cn/flathub", "desc": "Flathub"},
    {"name": "CPAN", "url": "https://mirror.sjtu.edu.cn/cpan", "desc": "CPAN (Perl)"},
    {"name": "CTAN", "url": "https://mirror.sjtu.edu.cn/ctan", "desc": "CTAN (TeX)"},
    {"name": "manjaro", "url": "https://mirror.sjtu.edu.cn/manjaro", "desc": "Manjaro Linux"},
    {"name": "archlinux", "url": "https://mirror.sjtu.edu.cn/archlinux", "desc": "Arch Linux"},
]


# ============================================================
# 镜像列表
# ============================================================

def list_mirrors() -> list[dict]:
    """爬取 SJTUG 镜像站，列出所有可用镜像"""
    try:
        # SJTUG 镜像站使用前端渲染，尝试 API
        resp = requests.get(
            "https://mirror.sjtu.edu.cn/sjtug-mirror-backend/mirrors",
            headers=HEADERS, timeout=TIMEOUT
        )
        if resp.status_code == 200:
            data = resp.json()
            mirrors = []
            for item in data:
                mirrors.append({
                    "name": item.get("name", ""),
                    "url": item.get("upstream", ""),
                    "desc": item.get("desc", ""),
                    "status": item.get("status", "unknown"),
                })
            return mirrors
    except Exception:
        pass

    # 降级：尝试爬取 HTML
    try:
        resp = requests.get(MIRROR_BASE, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        mirrors = []
        for link in soup.select("a[href]"):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if href.startswith("/") and len(text) > 1 and text not in ("Home", "About"):
                mirrors.append({
                    "name": text,
                    "url": MIRROR_BASE + href,
                    "desc": "",
                })
        if mirrors:
            return mirrors
    except Exception:
        pass

    # 最终降级：硬编码
    return FALLBACK_MIRRORS


# ============================================================
# 各工具换源配置
# ============================================================

def get_pip_config() -> str:
    """返回 pip 换源命令和配置"""
    return """
╔══════════════════════════════════════════════════════════╗
║  pip 换源到 SJTUG 镜像                                   ║
╚══════════════════════════════════════════════════════════╝

▶ 临时使用:
  pip install <包名> -i https://mirror.sjtu.edu.cn/pypi/web/simple

▶ 永久配置 (推荐):
  pip config set global.index-url https://mirror.sjtu.edu.cn/pypi/web/simple

▶ 或手动编辑 ~/.pip/pip.conf:
  [global]
  index-url = https://mirror.sjtu.edu.cn/pypi/web/simple
  trusted-host = mirror.sjtu.edu.cn
""".strip()


def get_conda_config() -> str:
    """返回 conda 换源命令和配置"""
    return """
╔══════════════════════════════════════════════════════════╗
║  conda 换源到 SJTUG 镜像                                 ║
╚══════════════════════════════════════════════════════════╝

▶ 编辑 ~/.condarc，写入以下内容:

channels:
  - defaults
show_channel_urls: true
default_channels:
  - https://mirror.sjtu.edu.cn/anaconda/pkgs/main
  - https://mirror.sjtu.edu.cn/anaconda/pkgs/r
  - https://mirror.sjtu.edu.cn/anaconda/pkgs/msys2
custom_channels:
  conda-forge: https://mirror.sjtu.edu.cn/anaconda/cloud
  pytorch: https://mirror.sjtu.edu.cn/anaconda/cloud

▶ 清除缓存:
  conda clean -i
""".strip()


def get_brew_config() -> str:
    """返回 brew 换源命令和配置"""
    return """
╔══════════════════════════════════════════════════════════╗
║  Homebrew 换源到 SJTUG 镜像                               ║
╚══════════════════════════════════════════════════════════╝

▶ 设置环境变量 (添加到 ~/.zshrc 或 ~/.bashrc):

  export HOMEBREW_API_DOMAIN="https://mirror.sjtu.edu.cn/homebrew-bottles/api"
  export HOMEBREW_BOTTLE_DOMAIN="https://mirror.sjtu.edu.cn/homebrew-bottles/bottles"
  export HOMEBREW_BREW_GIT_REMOTE="https://mirror.sjtu.edu.cn/git/brew.git"
  export HOMEBREW_CORE_GIT_REMOTE="https://mirror.sjtu.edu.cn/git/homebrew-core.git"
  export HOMEBREW_PIP_INDEX_URL="https://mirror.sjtu.edu.cn/pypi/web/simple"

▶ 生效:
  source ~/.zshrc
""".strip()


def get_docker_config() -> str:
    """返回 docker 换源命令和配置"""
    return """
╔══════════════════════════════════════════════════════════╗
║  Docker 换源到 SJTUG 镜像                                 ║
╚══════════════════════════════════════════════════════════╝

▶ 编辑 /etc/docker/daemon.json (Linux) 
  或 Docker Desktop → Settings → Docker Engine:

{
  "registry-mirrors": [
    "https://docker.mirrors.sjtug.sjtu.edu.cn"
  ]
}

▶ 重启 Docker:
  sudo systemctl restart docker    # Linux
  # macOS: 重启 Docker Desktop
""".strip()


def get_npm_config() -> str:
    """返回 npm 换源配置"""
    return """
╔══════════════════════════════════════════════════════════╗
║  npm 换源到 SJTUG 镜像                                    ║
╚══════════════════════════════════════════════════════════╝

▶ 临时使用:
  npm install <包名> --registry https://mirror.sjtu.edu.cn/npm-registry

▶ 永久配置:
  npm config set registry https://mirror.sjtu.edu.cn/npm-registry
""".strip()


def auto_setup(tool: str) -> str:
    """根据工具名返回对应配置"""
    configs = {
        "pip": get_pip_config,
        "conda": get_conda_config,
        "brew": get_brew_config,
        "docker": get_docker_config,
        "npm": get_npm_config,
    }
    func = configs.get(tool.lower())
    if func:
        return func()
    return f"❌ 不支持的工具: {tool}\n支持的工具: {', '.join(configs.keys())}"


# ============================================================
# CLI
# ============================================================

def print_mirrors():
    """打印镜像列表"""
    mirrors = list_mirrors()
    print(f"\n🪞 SJTUG 镜像站 ({MIRROR_BASE})")
    print(f"   共 {len(mirrors)} 个镜像\n")
    print(f"{'序号':<4} {'名称':<25} {'描述'}")
    print("─" * 70)
    for i, m in enumerate(mirrors, 1):
        name = m.get("name", "")
        desc = m.get("desc", "") or m.get("url", "")
        status = m.get("status", "")
        flag = "✅" if status in ("success", "") else "⏳"
        print(f"{i:<4} {flag} {name:<23} {desc[:40]}")


def main():
    if len(sys.argv) < 2:
        print("用法: python3 sjtu_mirror.py <命令>")
        print()
        print("命令:")
        print("  list    列出所有可用镜像")
        print("  pip     pip 换源配置")
        print("  conda   conda 换源配置")
        print("  brew    Homebrew 换源配置")
        print("  docker  Docker 换源配置")
        print("  npm     npm 换源配置")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "list":
        print_mirrors()
    elif cmd in ("pip", "conda", "brew", "docker", "npm"):
        print(auto_setup(cmd))
    else:
        print(f"❌ 未知命令: {cmd}")
        print("运行 python3 sjtu_mirror.py 查看帮助")
        sys.exit(1)


if __name__ == "__main__":
    main()
