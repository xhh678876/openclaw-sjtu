"""Headless regression check for the desktop client backend.

Runs the real Bridge against the real skill scripts (no GUI), covering the
encoding path, node actions, placeholder expansion, and the sjtudate.mjs
Windows regression.
"""
import importlib.util
import json
import os
import sys

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")

spec = importlib.util.spec_from_file_location("sjtu_client_app", APP)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

bridge = mod.Bridge()
events = []
bridge.emit = lambda kind, payload: events.append((kind, payload))

failures = []


def check(name, ok, detail=""):
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name, ("  -> " + detail) if detail else ""))
    if not ok:
        failures.append(name)


def capture(argv, channel="action", limit=10, timeout=120):
    events.clear()
    bridge.stream(channel, "t", argv, mod.SKILL_DIR, timeout)
    chunks = [p["line"] for k, p in events if k == "chunk"]
    done = [p for k, p in events if k == "done"]
    return chunks, (done[-1] if done else None)


print("=" * 64)
print("1) 元信息与动作注册表")
print("=" * 64)
boot = bridge.bootstrap()
acts = boot["actions"]
ids = [a["id"] for a in acts]
check("动作数量 >= 45", len(acts) >= 45, "got %d" % len(acts))
check("动作 id 无重复", len(ids) == len(set(ids)))
groups = sorted({a["group"] for a in acts})
print("     分组:", " / ".join(groups))
check("技能目录存在", boot["skillsPresent"], boot["skillDir"])
check("课件目录与技能目录同盘",
      os.path.splitdrive(mod.COURSEWARE_DIR)[0] == os.path.splitdrive(mod.SKILL_REAL)[0],
      "%s vs %s" % (mod.COURSEWARE_DIR, mod.SKILL_REAL))
check("python 解释器已解析", bool(boot["python"]), boot["python"])
check("node 已解析", bool(boot["node"]), boot["node"])
check("gateway 在线", boot["gateway"]["up"])

print()
print("=" * 64)
print("2) 占位符展开")
print("=" * 64)
p = r"E:\some dir\notes.md"
out = mod.Bridge()._expand(["{path}", "{pathdir}", "{pathstem}", "{pathname}", "{arg}"], "标题", p)
check("{path}", out[0] == p, out[0])
check("{pathdir}", out[1] == r"E:\some dir", out[1])
check("{pathstem}", out[2] == r"E:\some dir\notes", out[2])
check("{pathname}", out[3] == "notes.md", out[3])
check("{arg}", out[4] == "标题", out[4])

print()
print("=" * 64)
print("3) 参数 / 路径校验")
print("=" * 64)
check("缺参数被拒", bridge.run_action("review", "")["ok"] is False)
check("缺路径被拒", bridge.run_action("extract_file", "", "")["ok"] is False)
check("未知动作被拒", bridge.run_action("nope")["ok"] is False)
check("无需路径的动作定义完整",
      mod.ACTION_BY_ID["ppt_tpl"]["prompt"] is None
      and mod.ACTION_BY_ID["ppt_tpl"]["dialog"] is None)

print()
print("=" * 64)
print("4) Python 脚本（含中文输出与凭证）")
print("=" * 64)
chunks, done = capture(mod.PYTHON + ["scripts/canvas_api.py", "ddls"])
check("未交作业退出码 0", done and done["ok"], str(done and done.get("code")))
check("中文未乱码", any("未交作业" in c for c in chunks),
      " | ".join(chunks[:2]))

print()
print("=" * 64)
print("5) Node 脚本（sjtudate.mjs 的 HOME bug 回归）")
print("=" * 64)
chunks, done = capture(mod.NODE + ["scripts/sjtudate.mjs"], timeout=60)
blob = "\n".join(chunks)
check("无参数不再崩溃", "ERR_INVALID_ARG_TYPE" not in blob and "process.env.HOME" not in blob)
check("打印出用法", "SJTU Date CLI" in blob, blob.splitlines()[0][:70] if blob else "(空)")

chunks, done = capture(mod.NODE + ["scripts/shuiyuan_discourse.mjs", "auth", "status"], timeout=60)
blob = "\n".join(chunks)
check("水源 auth status 可运行", done is not None, blob.splitlines()[0][:70] if blob else "(空)")

print()
print("=" * 64)
print("6) 文件 / 目录对话框")
print("=" * 64)
check("OPEN 常量已解析", isinstance(mod.DIALOG_OPEN, int), str(mod.DIALOG_OPEN))
check("FOLDER 常量已解析", isinstance(mod.DIALOG_FOLDER, int), str(mod.DIALOG_FOLDER))
check("无 dialog 的动作被拒", bridge.pick_path("ddls").get("ok") is False)
check("未知动作被拒", bridge.pick_path("nope").get("ok") is False)
check("需要文件的动作已登记", mod.ACTION_BY_ID["extract_file"]["dialog"] == "file")
check("需要目录的动作已登记", mod.ACTION_BY_ID["extract_dir"]["dialog"] == "dir")
check("PPT 生成同时要文件与标题",
      mod.ACTION_BY_ID["ppt_gen"]["dialog"] == "file"
      and bool(mod.ACTION_BY_ID["ppt_gen"]["prompt"]))

print()
print("=" * 64)
print("7) OpenClaw agent")
print("=" * 64)
chunks, done = capture(mod.NODE + [mod.OPENCLAW_ENTRY, "agent", "-m", "只回复两个字：就绪"],
                       channel="chat", timeout=420)
check("agent 应答", done and done["ok"], str(done and done.get("code")))
print("     ", " ".join(chunks)[:90])

print()
print("=" * 64)
print("结果: %d 项失败" % len(failures))
if failures:
    for f in failures:
        print("   FAIL:", f)
print("=" * 64)
sys.exit(1 if failures else 0)
