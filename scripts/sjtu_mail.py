#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上海交通大学邮箱 IMAP/SMTP 工具
功能：获取未读邮件、搜索邮件、发送邮件、邮箱概况
IMAP: mail.sjtu.edu.cn:993 (SSL)
SMTP: mail.sjtu.edu.cn:465 (SSL)
"""

import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import parsedate_to_datetime
import json
import os
import sys
import argparse
from datetime import datetime

IMAP_HOST = "mail.sjtu.edu.cn"
IMAP_PORT = 993
SMTP_HOST = "mail.sjtu.edu.cn"
SMTP_PORT = 465
TIMEOUT = 10
# 本地过滤式搜索最多回溯多少封邮件的件头（IMAP SEARCH 传不了非 ASCII 关键词）
HEADER_SCAN_LIMIT = 300

# config.json 在 scripts/ 的父目录（sjtu-canvas/config.json）
_script_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_script_dir)
CONFIG_PATH = os.path.join(_parent_dir, "config.json")
# 兼容: 也检查 scripts/ 目录下
if not os.path.exists(CONFIG_PATH):
    CONFIG_PATH = os.path.join(_script_dir, "config.json")


def _load_config():
    """从 config.json 加载凭证"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _decode_str(s):
    """解码邮件头部字符串"""
    if s is None:
        return ""
    parts = decode_header(s)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            charset = charset or "utf-8"
            try:
                result.append(part.decode(charset, errors="replace"))
            except (LookupError, UnicodeDecodeError):
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def _get_body_preview(msg, max_len=200):
    """提取邮件正文摘要"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                try:
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
                except Exception:
                    continue
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            body = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            body = "(无法解码正文)"
    # 清理并截断
    body = " ".join(body.split())
    return body[:max_len] + "..." if len(body) > max_len else body


def normalize_username(username):
    """补全 jAccount 用户名。

    `scripts/setup.py` 把 `sjtu_username` 存成裸用户名（它自己拼域名），但 IMAP/SMTP
    登录需要完整邮箱地址。两种写法都接受，避免照文档用向导配好后邮箱反而登录失败。
    """
    username = (username or "").strip()
    if username and "@" not in username:
        return username + "@sjtu.edu.cn"
    return username


def _connect_imap(username, password):
    """建立 IMAP 连接"""
    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=TIMEOUT)
        conn.login(username, password)
        return conn
    except imaplib.IMAP4.error as e:
        raise ConnectionError(f"IMAP 登录失败: {e}")
    except Exception as e:
        raise ConnectionError(f"IMAP 连接失败: {e}")


def _parse_mail(conn, mail_id):
    """解析单封邮件。

    用 BODY.PEEK[] 而不是 RFC822：后者等价于 BODY[]，会在服务端置上 \\Seen 标记，
    而「未读邮件」「邮箱概况」都是只读命令，不该改变邮箱状态。
    """
    _, data = conn.fetch(mail_id, "(BODY.PEEK[])")
    if not data or not data[0]:
        return None
    raw = data[0][1]
    msg = email.message_from_bytes(raw)
    subject = _decode_str(msg.get("Subject", ""))
    from_addr = _decode_str(msg.get("From", ""))
    date_str = msg.get("Date", "")
    try:
        date_obj = parsedate_to_datetime(date_str)
        date_display = date_obj.strftime("%Y-%m-%d %H:%M")
    except Exception:
        date_display = date_str
    preview = _get_body_preview(msg)
    return {
        "subject": subject,
        "from": from_addr,
        "date": date_display,
        "preview": preview,
    }


def get_unread_mails(username, password, limit=10):
    """获取未读邮件列表"""
    conn = _connect_imap(username, password)
    try:
        conn.select("INBOX")
        _, data = conn.search(None, "UNSEEN")
        mail_ids = data[0].split()
        if not mail_ids:
            return []
        # 取最新的 limit 封
        mail_ids = mail_ids[-limit:]
        mail_ids.reverse()
        results = []
        for mid in mail_ids:
            info = _parse_mail(conn, mid)
            if info:
                results.append(info)
        return results
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _fetch_headers(conn, mail_id):
    """只取 SUBJECT/FROM/DATE 三个头，用于本地关键词过滤。"""
    _, data = conn.fetch(mail_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
    if not data or not data[0]:
        return None
    msg = email.message_from_bytes(data[0][1])
    return {
        "subject": _decode_str(msg.get("Subject", "")),
        "from": _decode_str(msg.get("From", "")),
    }


def search_mails(username, password, keyword, limit=10):
    """按主题和发件人搜索邮件。

    IMAP SEARCH 无法可靠承载非 ASCII 关键词：RFC 3501 不允许 8-bit 字节出现在
    quoted string 中，而 imaplib 只会用 ASCII 编码 criteria。于是「作业」这类关键词
    要么在本地抛 `UnicodeEncodeError`，要么被服务端拒绝：

        SEARCH command error: BAD [b"parse error: illegal character ..."]

    所以改为拉取最近的件头在本地做大小写不敏感匹配，中英文关键词行为一致。
    """
    conn = _connect_imap(username, password)
    try:
        conn.select("INBOX")
        _, data = conn.search(None, "ALL")
        ids = data[0].split() if data and data[0] else []
        if not ids:
            return []

        # 只扫最近的 HEADER_SCAN_LIMIT 封，避免大邮箱把整箱件头都拉下来
        needle = keyword.casefold()
        matched = []
        for mid in reversed(ids[-HEADER_SCAN_LIMIT:]):
            head = _fetch_headers(conn, mid)
            if not head:
                continue
            if needle in head["subject"].casefold() or needle in head["from"].casefold():
                matched.append(mid)
                if len(matched) >= limit:
                    break

        results = []
        for mid in matched:
            info = _parse_mail(conn, mid)
            if info:
                results.append(info)
        return results
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def send_mail(username, password, to, subject, body, html=False):
    """发送邮件"""
    msg = MIMEMultipart()
    msg["From"] = username
    msg["To"] = to
    msg["Subject"] = subject
    content_type = "html" if html else "plain"
    msg.attach(MIMEText(body, content_type, "utf-8"))
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT) as server:
            server.login(username, password)
            server.send_message(msg)
        return {"success": True, "message": f"邮件已发送至 {to}"}
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "SMTP 认证失败，请检查用户名和密码"}
    except Exception as e:
        return {"success": False, "message": f"发送失败: {e}"}


def get_mail_summary(username, password):
    """返回邮箱概况"""
    conn = _connect_imap(username, password)
    try:
        conn.select("INBOX")
        # 总数
        _, data_all = conn.search(None, "ALL")
        all_ids = data_all[0].split() if data_all[0] else []
        total = len(all_ids)
        # 未读数
        _, data_unseen = conn.search(None, "UNSEEN")
        unseen_ids = data_unseen[0].split() if data_unseen[0] else []
        unread = len(unseen_ids)
        # 最近5封
        recent_ids = all_ids[-5:] if all_ids else []
        recent_ids.reverse()
        recent = []
        for mid in recent_ids:
            info = _parse_mail(conn, mid)
            if info:
                recent.append(info)
        return {
            "total": total,
            "unread": unread,
            "recent": recent,
        }
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _format_mail_list(mails, title="邮件列表"):
    """格式化邮件列表用于终端输出"""
    if not mails:
        print(f"\n📭 {title}: 无邮件\n")
        return
    print(f"\n📬 {title} (共 {len(mails)} 封)")
    print("=" * 60)
    for i, m in enumerate(mails, 1):
        print(f"\n  [{i}] 📧 {m['subject']}")
        print(f"      发件人: {m['from']}")
        print(f"      日期:   {m['date']}")
        print(f"      摘要:   {m['preview'][:80]}...")
    print()


def main():
    parser = argparse.ArgumentParser(description="上海交通大学邮箱工具")
    parser.add_argument("action", choices=["unread", "search", "send", "summary"],
                        help="操作: unread(未读) / search(搜索) / send(发送) / summary(概况)")
    parser.add_argument("--username", "-u", help="邮箱用户名")
    parser.add_argument("--password", "-p", help="邮箱密码")
    parser.add_argument("--limit", "-l", type=int, default=10, help="返回数量限制")
    parser.add_argument("--keyword", "-k", help="搜索关键词 (search 时必填)")
    parser.add_argument("--to", help="收件人 (send 时必填)")
    parser.add_argument("--subject", "-s", help="邮件主题 (send 时必填)")
    parser.add_argument("--body", "-b", help="邮件正文 (send 时必填)")
    parser.add_argument("--html", action="store_true", help="以 HTML 格式发送")
    args = parser.parse_args()

    # 加载凭证
    config = _load_config()
    username = args.username or config.get("sjtu_username", "")
    password = args.password or config.get("sjtu_password", "")

    if not username or not password:
        print("❌ 错误: 请提供用户名和密码 (命令行参数或 config.json)")
        sys.exit(1)

    username = normalize_username(username)

    try:
        if args.action == "unread":
            mails = get_unread_mails(username, password, args.limit)
            _format_mail_list(mails, "未读邮件")

        elif args.action == "search":
            if not args.keyword:
                print("❌ 错误: search 操作需要 --keyword 参数")
                sys.exit(1)
            mails = search_mails(username, password, args.keyword, args.limit)
            _format_mail_list(mails, f"搜索结果 (关键词: {args.keyword})")

        elif args.action == "send":
            if not all([args.to, args.subject, args.body]):
                print("❌ 错误: send 操作需要 --to, --subject, --body 参数")
                sys.exit(1)
            result = send_mail(username, password, args.to, args.subject, args.body, args.html)
            if result["success"]:
                print(f"✅ {result['message']}")
            else:
                print(f"❌ {result['message']}")
                sys.exit(1)

        elif args.action == "summary":
            summary = get_mail_summary(username, password)
            print(f"\n📊 邮箱概况")
            print("=" * 40)
            print(f"  📨 总邮件数: {summary['total']}")
            print(f"  📬 未读邮件: {summary['unread']}")
            _format_mail_list(summary["recent"], "最近邮件")

    except ConnectionError as e:
        print(f"❌ 连接错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
