# 交大助手 · 桌面客户端

把 [openclaw-sjtu](https://github.com/xhh678876/openclaw-sjtu) 的 CLI 子命令封装成图形应用：
**左侧按钮走脚本**（秒回、不消耗模型 token），**底部对话栏走 AI**（OpenClaw Gateway，自然语言）。

## 运行要求

| 依赖 | 用途 | 缺失后果 |
|---|---|---|
| Python 3.8+ | 技能脚本本身是 Python | 所有 Python 按钮不可用 |
| Node.js ≥18 | 水源社区、SJTU Date 是 `.mjs` | 那两个分组的按钮不可用 |
| openclaw-sjtu 仓库 | 提供 `scripts/` 与 `config.json` | 全部按钮不可用 |
| WebView2 运行时 | 渲染界面（Win11 自带） | 窗口打不开 |
| OpenClaw Gateway | 对话栏（可选） | 只有对话栏不可用，按钮不受影响 |

> 打包出的 exe **不是**自带 Python 的独立程序——技能本身就是 Python 脚本，所以 exe 是 GUI 外壳。

## 使用

```
双击「交大助手.exe」          # 打包版
python app.py                 # 源码直接运行
调试启动.bat                   # 源码 + 保留控制台，用于看报错
```

技能目录默认按 `SJTU_SKILL_DIR` → `E:\openclaw-sjtu` → `~/openclaw-sjtu` → `~/.openclaw/workspace/skills/openclaw-sjtu`
的顺序查找；换机器时设 `SJTU_SKILL_DIR` 即可。

## 构建

```
build_exe.bat                 # PyInstaller 单文件 exe → 交大助手.exe
python selftest_backend.py    # 无界面回归测试（17 项）
python make_icon.py           # 重新生成 app.ico
```

## 文件

| 文件 | 说明 |
|---|---|
| `app.py` | 后端：动作注册表、子进程流式执行、文件对话框、Gateway 探测 |
| `ui/` | 前端：`index.html` / `style.css` / `app.js` |
| `build_exe.bat` | 打包脚本（内容纯 ASCII，原因见下） |
| `post_build.py` | 打包后重命名为中文名 |
| `selftest_backend.py` | 后端回归测试 |
| `启动交大助手.vbs` | 源码版启动器（无控制台窗口） |
| `调试启动.bat` | 源码版调试启动器 |

## 三个环境相关的坑（都已在代码里处理）

1. **GBK 编码**：本机 `locale.getpreferredencoding()` 是 `cp936`，而脚本输出 UTF-8。
   子进程统一注入 `PYTHONIOENCODING=utf-8` 并按 UTF-8 解码回读，否则中文乱码或抛 `UnicodeDecodeError`。
2. **`.bat` / `.vbs` 内容必须是纯 ASCII**：`cmd.exe` 按 OEM 代码页读 `.bat`，WSH 按 ANSI 读 `.vbs`，
   UTF-8 中文会被误解码。文件名可以中文，文件内容不行。
3. **`.vbs` 窗口样式必须是 `1`**：样式 `0`（隐藏）会把 pywebview 创建的 GUI 窗口一起隐藏，
   表现为"进程活着但没有窗口"。`pythonw.exe` 是 GUI 子系统程序，用样式 `1` 也不会闪控制台。

## 适配 PyInstaller 的处理

打包后 `sys.executable` 是 exe 自身而不是解释器，`__file__` 指向临时解包目录，因此：

- `resolve_python()` 去系统里找真正的 Python（exe 不能当脚本运行器用）
- `resource_dir()` 用 `sys._MEIPASS` 定位 `ui/` 和 `app.ico`
- 构建时不能加 `--specpath`：PyInstaller 以 spec 文件所在目录解析相对 `--add-data` 路径
