"""交大助手桌面客户端 —— 把 openclaw-sjtu 技能封装成图形应用。

左侧功能按钮直接调用仓库内的 CLI 脚本（秒回，不消耗模型 token）；
右侧对话栏走 OpenClaw Gateway 的 agent（自然语言 + AI）。

几点必须遵守的约束：

* 脚本按仓库根定位 `config.json` / `templates` / `fonts`，所以每个子进程的 cwd 固定为
  技能目录（SKILL_DIR）。
* 本机 locale 是 GBK(cp936)，而脚本输出是 UTF-8，因此子进程统一注入
  `PYTHONIOENCODING=utf-8` 并按 UTF-8 解码回读，否则中文会乱码或抛 UnicodeDecodeError。
* 打包成单文件 exe 后 `sys.executable` 是 exe 自己而不是解释器，`__file__` 指向临时解包目录，
  所以解释器与资源目录都必须单独解析。
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import webview


def resource_dir():
    """静态资源（ui/、app.ico）所在目录，兼容 PyInstaller 单文件解包。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resolve_skill_dir():
    """定位 openclaw-sjtu 仓库根。

    优先看本目录的上级：客户端按 `desktop-client/` 放进仓库时，技能目录就是它的父目录，
    这样换机器、换盘符都不用改配置。其次才用显式环境变量与常见安装位置。
    """
    parent = os.path.dirname(APP_DIR)
    candidates = [
        parent,
        os.environ.get("SJTU_SKILL_DIR", ""),
        os.path.expanduser("~/openclaw-sjtu"),
        os.path.expanduser("~/.openclaw/workspace/skills/openclaw-sjtu"),
        r"E:\openclaw-sjtu",
    ]
    for path in candidates:
        if path and os.path.isfile(os.path.join(path, "SKILL.md")):
            return path
    return parent


def resolve_python():
    """返回运行技能脚本的命令前缀。

    打包后 sys.executable 是本 exe 而非解释器，直接用它会把 exe 当成脚本运行器，
    所以必须去系统里找一个真正的 Python。技能脚本本身是 Python，因此这是硬依赖。
    """
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    local = os.environ.get("LOCALAPPDATA", "")
    for version in ("Python314", "Python313", "Python312", "Python311", "Python310"):
        exe = os.path.join(local, "Programs", "Python", version, "python.exe")
        if os.path.isfile(exe):
            return [exe]
    for name in ("python.exe", "python3.exe", "py.exe"):
        found = shutil.which(name)
        if found:
            return [found]
    return ["python"]


def resolve_node():
    """返回运行 .mjs 脚本的命令前缀（水源、SJTU Date 需要 Node ≥18）。"""
    candidates = [
        r"D:\node.exe",
        r"C:\Program Files\nodejs\node.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "nodejs", "node.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return [path]
    found = shutil.which("node.exe") or shutil.which("node")
    return [found] if found else ["node"]


APP_DIR = resource_dir()
SKILL_DIR = resolve_skill_dir()
# realpath: SKILL_DIR may be reached through a directory junction, and deriving
# the courseware folder from the junction path would put downloads on the wrong
# drive. Resolving the link first keeps the data next to the real checkout.
SKILL_REAL = os.path.realpath(SKILL_DIR)
COURSEWARE_DIR = os.path.join(os.path.dirname(SKILL_REAL), "SJTU-Courseware")
UI_INDEX = os.path.join(APP_DIR, "ui", "index.html")
ICON_PATH = os.path.join(APP_DIR, "app.ico")

PYTHON = resolve_python()
NODE = resolve_node()

OPENCLAW_ENTRY = os.path.join(
    os.environ.get("APPDATA", ""), "npm", "node_modules", "openclaw", "dist", "index.js",
)
GATEWAY_HEALTH = "http://127.0.0.1:18789/health"

SCRIPT_TIMEOUT = 300
CHAT_TIMEOUT = 600

# pywebview renamed the dialog constants to FileDialog.*; the old module-level
# attributes still work but warn. Only touch them when FileDialog is absent, so
# modern installs never trigger the deprecation path.
_DIALOG_ENUM = getattr(webview, "FileDialog", None)
DIALOG_OPEN = (getattr(_DIALOG_ENUM, "OPEN", None) if _DIALOG_ENUM is not None
               else getattr(webview, "OPEN_DIALOG", 10))
DIALOG_FOLDER = (getattr(_DIALOG_ENUM, "FOLDER", None) if _DIALOG_ENUM is not None
                 else getattr(webview, "FOLDER_DIALOG", 20))

MD_FILTER = ("Markdown (*.md;*.markdown)", "所有文件 (*.*)")
TXT_FILTER = ("文本 (*.txt)", "所有文件 (*.*)")
DOC_FILTER = ("课件 (*.pptx;*.ppt;*.pdf;*.docx;*.txt;*.md)", "所有文件 (*.*)")


def A(aid, group, label, argv, interp="python", prompt=None, dialog=None, filters=None):
    """构造一条动作定义。argv 里可用 {arg} {path} {pathdir} {pathstem} {pathname}。"""
    return {
        "id": aid, "group": group, "label": label, "argv": argv,
        "interp": interp, "prompt": prompt, "dialog": dialog,
        "filters": filters or (),
    }


ACTIONS = [
    # ── 作业与学习 ────────────────────────────────────────────────
    A("ddls", "作业与学习", "未交作业", ["scripts/canvas_api.py", "ddls"]),
    A("ddls_all", "作业与学习", "学期 DDL 全景", ["scripts/canvas_api.py", "ddls-all"]),
    A("courses", "作业与学习", "我的课程", ["scripts/canvas_api.py", "courses"]),
    A("grades", "作业与学习", "成绩", ["scripts/canvas_api.py", "grades"]),
    A("auto_scan", "作业与学习", "自动扫描作业", ["scripts/auto_homework.py", "scan"]),
    A("auto_urgent", "作业与学习", "紧急作业 (48h)",
      ["scripts/auto_homework.py", "urgent", "48"]),
    A("ics", "作业与学习", "导出日历 (.ics)",
      ["scripts/sjtu_timetable_ics.py", "all", os.path.join(COURSEWARE_DIR, "sjtu_timetable.ics")]),
    A("review", "作业与学习", "课程评价查询",
      ["scripts/sjtu_course_review.py", "search", "{arg}"], prompt="课程名或老师名，如 传热学"),
    A("review_compare", "作业与学习", "老师评分对比",
      ["scripts/sjtu_course_review.py", "compare", "{arg}"], prompt="课程名，如 传热学"),

    # ── 校园生活 ──────────────────────────────────────────────────
    A("canteen", "校园生活", "食堂推荐", ["scripts/sjtu_canteen.py", "recommend"]),
    A("canteen_menu", "校园生活", "食堂菜单", ["scripts/sjtu_canteen.py", "menu", "{arg}"],
      prompt="食堂简称：一餐/二餐/三餐/四餐/五餐/哈乐/玉兰苑"),
    A("week", "校园生活", "当前教学周", ["scripts/sjtu_info.py", "week"]),
    A("calendar", "校园生活", "校历", ["scripts/sjtu_info.py", "calendar"]),
    A("bus", "校园生活", "校园巴士", ["scripts/sjtu_info.py", "bus"]),
    A("library", "校园生活", "图书馆", ["scripts/sjtu_library.py", "info"]),
    A("library_seats", "校园生活", "图书馆座位预约", ["scripts/sjtu_library.py", "seats"]),
    A("classroom", "校园生活", "全部教室清单", ["scripts/sjtu_classroom.py", "empty"]),
    A("classroom_b", "校园生活", "按教学楼查教室",
      ["scripts/sjtu_classroom.py", "empty", "--building", "{arg}"], prompt="教学楼名，如 东上院"),

    # ── 资讯与资源 ────────────────────────────────────────────────
    A("news_jwc", "资讯与资源", "教务处通知", ["scripts/sjtu_news.py", "jwc", "10"]),
    A("news", "资讯与资源", "交大要闻", ["scripts/sjtu_news.py", "news", "10"]),
    A("news_media", "资讯与资源", "媒体聚焦",
      ["scripts/sjtu_news.py", "news", "10", "--column", "mtjj"]),
    A("software", "资讯与资源", "正版软件", ["scripts/sjtu_software.py", "list"]),
    A("software_search", "资讯与资源", "软件搜索",
      ["scripts/sjtu_software.py", "search", "{arg}"], prompt="关键词，如 MATLAB"),
    A("survive", "资讯与资源", "生存手册目录", ["scripts/sjtu_survive.py", "toc"]),
    A("survive_search", "资讯与资源", "生存手册搜索",
      ["scripts/sjtu_survive.py", "search", "{arg}"], prompt="关键词，如 bao-yan / gpa"),
    A("survive_read", "资讯与资源", "生存手册阅读",
      ["scripts/sjtu_survive.py", "read", "{arg}"], prompt="章节 id，如 bao-yan"),
    A("visual", "资讯与资源", "视觉交大相册", ["scripts/sjtu_visual.py", "themes"]),
    A("visual_search", "资讯与资源", "视觉交大搜图",
      ["scripts/sjtu_visual.py", "search", "{arg}"], prompt="关键词，如 图书馆"),
    A("tools", "资讯与资源", "校内在线工具", ["scripts/sjtu_tools.py", "list"]),
    A("mail", "资讯与资源", "未读邮件", ["scripts/sjtu_mail.py", "unread", "--limit", "10"]),
    A("mail_summary", "资讯与资源", "邮箱概况", ["scripts/sjtu_mail.py", "summary"]),
    A("mail_search", "资讯与资源", "邮件搜索",
      ["scripts/sjtu_mail.py", "search", "--keyword", "{arg}"], prompt="关键词，如 作业"),
    A("legacy", "资讯与资源", "传承交大资料",
      ["scripts/sjtu_legacy.py", "search", "{arg}"], prompt="课程名，如 传热学"),

    # ── 水源社区（Node，需先 auth init 授权）──────────────────────
    A("sy_latest", "水源社区", "最新话题",
      ["scripts/shuiyuan_discourse.mjs", "latest", "--max-results", "30"], interp="node"),
    A("sy_search", "水源社区", "搜索帖子",
      ["scripts/shuiyuan_discourse.mjs", "search", "{arg}", "--max-results", "10"],
      interp="node", prompt="关键词，如 转专业"),
    A("sy_categories", "水源社区", "全部版块",
      ["scripts/shuiyuan_discourse.mjs", "categories"], interp="node"),
    A("sy_auth", "水源社区", "授权状态",
      ["scripts/shuiyuan_discourse.mjs", "auth", "status"], interp="node"),

    # ── SJTU Date（Node，需先 login）──────────────────────────────
    A("date_dashboard", "SJTU Date", "Dashboard",
      ["scripts/sjtudate.mjs", "dashboard"], interp="node"),
    A("date_match", "SJTU Date", "最新匹配", ["scripts/sjtudate.mjs", "match"], interp="node"),
    A("date_round", "SJTU Date", "轮次状态",
      ["scripts/sjtudate.mjs", "round-status"], interp="node"),
    A("date_shoots", "SJTU Date", "收到的心动",
      ["scripts/sjtudate.mjs", "shoot-received"], interp="node"),
    A("date_survey", "SJTU Date", "问卷信息", ["scripts/sjtudate.mjs", "survey"], interp="node"),
    A("date_profile", "SJTU Date", "个人资料", ["scripts/sjtudate.mjs", "profile"], interp="node"),

    # ── 学术工具 ──────────────────────────────────────────────────
    A("ppt_tpl", "学术工具", "PPT 模板列表", ["scripts/generate_ppt.py", "--list-templates"]),
    A("ppt_gen", "学术工具", "用模板生成 PPT",
      ["scripts/generate_ppt.py", "--title", "{arg}", "--markdown", "{path}",
       "--output", "{pathstem}.pptx"],
      prompt="PPT 标题", dialog="file", filters=MD_FILTER),
    A("extract_file", "学术工具", "课件提取文本",
      ["scripts/file_extractor.py", "{path}"], dialog="file", filters=DOC_FILTER),
    A("extract_dir", "学术工具", "课件批量转 Markdown",
      ["scripts/file_extractor.py", "{path}", os.path.join("{path}", "markdown")],
      dialog="dir"),
    A("handwrite", "学术工具", "生成手写体 PDF",
      ["scripts/handwrite_pdf.py", "{path}", "{pathstem}.pdf", "--style", "casual"],
      dialog="file", filters=TXT_FILTER),
    A("mirror_pip", "学术工具", "pip 换交大源", ["scripts/sjtu_mirror.py", "pip"]),
    A("mirror_conda", "学术工具", "conda 换交大源", ["scripts/sjtu_mirror.py", "conda"]),
    A("mirror_npm", "学术工具", "npm 换交大源", ["scripts/sjtu_mirror.py", "npm"]),
]

ACTION_BY_ID = {a["id"]: a for a in ACTIONS}


def child_env():
    """子进程环境：强制 UTF-8 输出，避免 GBK locale 下中文乱码。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


class Bridge:
    """暴露给前端的 JS API。耗时操作都在后台线程跑，结果通过事件推回前端。"""

    def __init__(self):
        self.window = None
        self.proc_lock = threading.Lock()
        self.proc = None

    # ── 前端事件推送 ──────────────────────────────────────────────
    def emit(self, kind, payload):
        if not self.window:
            return
        script = "window.__onEvent && window.__onEvent({}, {})".format(
            json.dumps(kind), json.dumps(payload, ensure_ascii=False)
        )
        try:
            self.window.evaluate_js(script)
        except Exception:
            # 窗口在任务跑完前被关闭；没有其它调用方需要这个失败
            pass

    # ── 元信息 ────────────────────────────────────────────────────
    def bootstrap(self):
        return {
            "actions": [
                {"id": a["id"], "group": a["group"], "label": a["label"],
                 "prompt": a["prompt"], "dialog": a["dialog"]}
                for a in ACTIONS
            ],
            "skillDir": SKILL_DIR,
            "coursewareDir": COURSEWARE_DIR,
            "python": " ".join(PYTHON),
            "node": " ".join(NODE),
            "frozen": bool(getattr(sys, "frozen", False)),
            "skillsPresent": os.path.isfile(os.path.join(SKILL_DIR, "SKILL.md")),
            "gateway": self.gateway_health(),
        }

    def gateway_health(self):
        try:
            with urllib.request.urlopen(GATEWAY_HEALTH, timeout=4) as resp:
                return {"up": resp.status == 200}
        except (urllib.error.URLError, OSError, ValueError):
            return {"up": False}

    # ── 文件 / 目录选择 ───────────────────────────────────────────
    def pick_path(self, action_id):
        """给带 dialog 的动作弹出系统文件对话框，返回选中路径。"""
        action = ACTION_BY_ID.get(action_id)
        if not action or not action["dialog"]:
            return {"ok": False, "error": "该功能不需要选择路径"}
        try:
            if action["dialog"] == "dir":
                picked = self.window.create_file_dialog(DIALOG_FOLDER)
            else:
                picked = self.window.create_file_dialog(
                    DIALOG_OPEN, allow_multiple=False,
                    file_types=action["filters"] or ("所有文件 (*.*)",),
                )
        except Exception as exc:
            return {"ok": False, "error": "打开文件对话框失败: {}".format(exc)}
        if not picked:
            return {"ok": False, "cancelled": True}
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        return {"ok": True, "path": path}

    # ── 运行动作 ──────────────────────────────────────────────────
    def _expand(self, argv, arg, path):
        """把占位符替换成实际值。"""
        stem = os.path.splitext(path)[0] if path else ""
        mapping = {
            "{arg}": str(arg or "").strip(),
            "{path}": path or "",
            "{pathdir}": os.path.dirname(path) if path else "",
            "{pathstem}": stem,
            "{pathname}": os.path.basename(path) if path else "",
        }
        out = []
        for token in argv:
            for key, value in mapping.items():
                token = token.replace(key, value)
            out.append(token)
        return out

    def run_action(self, action_id, arg="", path=""):
        action = ACTION_BY_ID.get(action_id)
        if action is None:
            return {"ok": False, "error": "未知功能: " + str(action_id)}
        if action["dialog"] and not path:
            return {"ok": False, "error": "请先选择文件或目录"}
        if action["prompt"] and not str(arg).strip():
            return {"ok": False, "error": "该功能需要一个参数：" + action["prompt"]}
        if not os.path.isfile(os.path.join(SKILL_DIR, "SKILL.md")):
            return {"ok": False, "error": "找不到技能目录: " + SKILL_DIR}

        prefix = list(NODE) if action["interp"] == "node" else list(PYTHON)
        argv = prefix + self._expand(action["argv"], arg, path)
        title = "{}/{}".format(action["group"], action["label"])
        threading.Thread(
            target=self.stream,
            args=("action", title, argv, SKILL_DIR, SCRIPT_TIMEOUT),
            daemon=True,
        ).start()
        return {"ok": True, "started": True}

    def ask(self, message):
        text = str(message or "").strip()
        if not text:
            return {"ok": False, "error": "请输入内容"}
        if not os.path.exists(OPENCLAW_ENTRY):
            return {"ok": False, "error": "找不到 OpenClaw 入口: " + OPENCLAW_ENTRY}
        if not self.gateway_health()["up"]:
            return {"ok": False, "error": "OpenClaw Gateway 未运行。先执行 openclaw gateway 启动。"}
        argv = list(NODE) + [OPENCLAW_ENTRY, "agent", "-m", text]
        threading.Thread(
            target=self.stream, args=("chat", text, argv, SKILL_DIR, CHAT_TIMEOUT),
            daemon=True,
        ).start()
        return {"ok": True, "started": True}

    def cancel(self):
        with self.proc_lock:
            proc = self.proc
        if proc and proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, creationflags=0x08000000)
            return {"ok": True}
        return {"ok": False, "error": "当前没有正在运行的任务"}

    # ── 子进程流式执行 ────────────────────────────────────────────
    def stream(self, channel, title, argv, cwd, timeout):
        self.emit("start", {"channel": channel, "title": title})
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, env=child_env(),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        except OSError as exc:
            self.emit("done", {"channel": channel, "ok": False,
                               "text": "启动失败: {}\n命令: {}".format(exc, " ".join(argv))})
            return

        with self.proc_lock:
            self.proc = proc

        lines = []
        timer = threading.Timer(timeout, self._kill, args=(proc,))
        timer.start()
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                lines.append(line)
                self.emit("chunk", {"channel": channel, "line": line})
            proc.wait()
            code = proc.returncode
            ok = code == 0
        finally:
            timer.cancel()
            with self.proc_lock:
                self.proc = None

        body = "\n".join(lines).strip()
        if code != 0 and not body:
            body = "命令退出码 {}，且没有输出。".format(code)
        self.emit("done", {"channel": channel, "ok": ok, "code": code, "text": body})

    def _kill(self, proc):
        if proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, creationflags=0x08000000)
            self.emit("chunk", {"channel": "action", "line": "[已超时，任务被终止]"})

    # ── 打开目录 ──────────────────────────────────────────────────
    def open_dir(self, which):
        target = {"skill": SKILL_DIR, "courseware": COURSEWARE_DIR}.get(which)
        if not target:
            return {"ok": False, "error": "未知目录"}
        try:
            os.makedirs(target, exist_ok=True)
            os.startfile(target)
        except OSError as exc:
            return {"ok": False, "error": "打开失败: {}".format(exc)}
        return {"ok": True}


def main():
    bridge = Bridge()
    window = webview.create_window(
        "交大助手 · openclaw-sjtu",
        url=UI_INDEX,
        js_api=bridge,
        width=1220, height=780, min_size=(940, 620),
        background_color="#12141a",
    )
    bridge.window = window
    webview.start(
        debug=os.environ.get("SJTU_CLIENT_DEBUG") == "1",
        icon=ICON_PATH if os.path.isfile(ICON_PATH) else None,
    )


if __name__ == "__main__":
    main()
