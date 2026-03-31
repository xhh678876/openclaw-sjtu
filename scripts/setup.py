#!/usr/bin/env python3
"""openclaw-sjtu 交互式配置向导

运行方式：python3 scripts/setup.py
功能：引导用户配置所有服务凭证，生成 config.json
"""

import os
import sys
import json
import getpass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")
EXAMPLE_PATH = os.path.join(PROJECT_DIR, "config.example.json")

# ANSI 颜色
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════╗
║       🎓 openclaw-sjtu 配置向导                  ║
║       上海交通大学全能 AI 校园助手                ║
╚══════════════════════════════════════════════════╝{RESET}
""")


def load_existing():
    """加载已有配置"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    if os.path.exists(EXAMPLE_PATH):
        with open(EXAMPLE_PATH) as f:
            return json.load(f)
    return {}


def prompt(label, default="", secret=False, required=False):
    """交互式输入，支持默认值和密码模式"""
    if default and not secret:
        hint = f"{DIM}(当前: {default[:20]}{'...' if len(str(default)) > 20 else ''}){RESET}"
    elif default and secret:
        hint = f"{DIM}(已配置，回车保留){RESET}"
    else:
        hint = f"{DIM}(可选，回车跳过){RESET}" if not required else f"{RED}(必填){RESET}"

    while True:
        if secret:
            val = getpass.getpass(f"  {label} {hint}: ")
        else:
            val = input(f"  {label} {hint}: ").strip()

        if not val:
            if default:
                return default
            if required:
                print(f"  {RED}⚠ 此项为必填，请输入{RESET}")
                continue
            return ""
        return val


def test_canvas(token, base_url):
    """测试 Canvas Token 是否有效"""
    try:
        import requests
        r = requests.get(
            f"{base_url}/api/v1/users/self",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if r.status_code == 200:
            name = r.json().get("name", "未知")
            print(f"  {GREEN}✅ Canvas 连接成功！用户: {name}{RESET}")
            return True
        else:
            print(f"  {RED}❌ Canvas 认证失败 (HTTP {r.status_code}){RESET}")
            return False
    except ImportError:
        print(f"  {YELLOW}⚠ 需要 requests 库来测试连接: pip install requests{RESET}")
        return None
    except Exception as e:
        print(f"  {RED}❌ 连接失败: {e}{RESET}")
        return False


def test_mail(username, password):
    """测试邮箱连接"""
    try:
        import imaplib
        conn = imaplib.IMAP4_SSL("mail.sjtu.edu.cn", 993, timeout=10)
        conn.login(f"{username}@sjtu.edu.cn", password)
        conn.logout()
        print(f"  {GREEN}✅ 邮箱连接成功！{RESET}")
        return True
    except Exception as e:
        print(f"  {RED}❌ 邮箱连接失败: {e}{RESET}")
        return False


def section(title, desc=""):
    """打印配置区块标题"""
    print(f"\n{BOLD}{CYAN}━━━ {title} ━━━{RESET}")
    if desc:
        print(f"  {DIM}{desc}{RESET}")
    print()


def main():
    banner()
    config = load_existing()
    is_update = os.path.exists(CONFIG_PATH)

    if is_update:
        print(f"{YELLOW}📝 检测到已有配置文件，将在此基础上更新{RESET}")
        print(f"{DIM}   直接回车可保留当前值{RESET}\n")
    else:
        print(f"  首次配置，将引导你逐步设置各项服务\n")

    # ━━━ 1. Canvas ━━━
    section(
        "📋 Canvas LMS（核心功能）",
        "DDL 追踪、成绩查询、课件下载等功能必需"
    )
    print(f"  {DIM}获取方式: oc.sjtu.edu.cn → 左下角「设置」→「新建访问许可证」{RESET}\n")

    config["base_url"] = "https://oc.sjtu.edu.cn"
    token = prompt("Canvas API Token", config.get("canvas_token", ""), secret=True, required=True)
    config["canvas_token"] = token
    config["save_dir"] = prompt("课件下载目录", config.get("save_dir", "~/Downloads/Canvas课件"))
    config["calendar_name"] = prompt("日历名称", config.get("calendar_name", "Canvas作业"))

    # 测试连接
    print()
    test_canvas(token, config["base_url"])

    # ━━━ 2. 邮箱 ━━━
    section(
        "📧 交大邮箱（可选）",
        "用于查看未读邮件、搜索、发送邮件"
    )
    print(f"  {DIM}使用 jAccount 账号登录 IMAP/SMTP{RESET}\n")

    username = prompt("jAccount 用户名", config.get("sjtu_username", ""))
    config["sjtu_username"] = username

    if username:
        password = prompt("jAccount 密码", config.get("sjtu_password", ""), secret=True)
        config["sjtu_password"] = password

        if password:
            print()
            yn = input(f"  是否测试邮箱连接？{DIM}(y/N){RESET}: ").strip().lower()
            if yn == "y":
                test_mail(username, password)
    else:
        config["sjtu_password"] = ""

    # ━━━ 3. 选课社区 ━━━
    section(
        "⭐ 选课社区（可选）",
        "课程评价、老师对比等功能"
    )
    print(f"  {DIM}受 CDN 反爬限制，推荐通过 OpenClaw 浏览器代理模式使用{RESET}")
    print(f"  {DIM}如有 cookie 也可手动填入{RESET}\n")

    config["course_sjtu_cookie"] = prompt("选课社区 Cookie", config.get("course_sjtu_cookie", ""))

    # ━━━ 4. 水源社区 ━━━
    section(
        "💧 水源社区（可选）",
        "搜索和浏览交大水源论坛帖子"
    )
    print(f"  {DIM}获取方式: 运行 node scripts/shuiyuan_discourse.mjs auth init{RESET}\n")

    config["shuiyuan_user_api_key"] = prompt(
        "水源 User API Key",
        config.get("shuiyuan_user_api_key", "")
    )
    config["shuiyuan_user_api_client_id"] = prompt(
        "水源 API Client ID",
        config.get("shuiyuan_user_api_client_id", "")
    )

    # ━━━ 保存 ━━━
    print(f"\n{BOLD}{CYAN}━━━ 保存配置 ━━━{RESET}\n")

    # 统计配置了多少项
    configured = []
    if config.get("canvas_token") and config["canvas_token"] != "YOUR_CANVAS_API_TOKEN":
        configured.append("Canvas")
    if config.get("sjtu_username"):
        configured.append("邮箱")
    if config.get("course_sjtu_cookie"):
        configured.append("选课社区")
    if config.get("shuiyuan_user_api_key"):
        configured.append("水源社区")

    print(f"  已配置服务: {GREEN}{', '.join(configured) if configured else '无'}{RESET}")
    print(f"  配置文件路径: {CONFIG_PATH}")
    print()

    yn = input(f"  确认保存？{DIM}(Y/n){RESET}: ").strip().lower()
    if yn == "n":
        print(f"\n  {YELLOW}已取消，配置未保存{RESET}")
        return

    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"\n  {GREEN}{BOLD}✅ 配置完成！{RESET}")
    print(f"  {DIM}配置已保存到 {CONFIG_PATH}{RESET}")
    print(f"""
{CYAN}现在你可以：{RESET}
  • 直接和 AI 对话：{BOLD}"我有什么作业没交？"{RESET}
  • 或手动运行脚本：{BOLD}python3 scripts/canvas_api.py ddls{RESET}

{DIM}如需修改配置，重新运行 python3 scripts/setup.py 即可{RESET}
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {YELLOW}已取消{RESET}")
        sys.exit(0)
