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
    """解析单封邮件"""
    _, data = conn.fetch(mail_id, "(RFC822)")
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


def search_mails(username, password, keyword, limit=10):
    """搜索邮件（按主题和发件人）"""
    conn = _connect_imap(username, password)
    try:
        conn.select("INBOX")
        # 搜索主题
        _, data_subj = conn.search(None, f'SUBJECT "{keyword}"')
        # 搜索发件人
        _, data_from = conn.search(None, f'FROM "{keyword}"')
        ids_subj = set(data_subj[0].split()) if data_subj[0] else set()
        ids_from = set(data_from[0].split()) if data_from[0] else set()
        all_ids = sorted(ids_subj | ids_from, key=lambda x: int(x))
        if not all_ids:
            return []
        all_ids = all_ids[-limit:]
        all_ids.reverse()
        results = []
        for mid in all_ids:
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
