# 在其他电脑上部署 MCMtools

这份文档是写给**另一个 AI agent** 看的：把整个 MCMtools 文件夹拷到一台新机器上，
让 agent 照着这份文档把它跑起来、并按需打包成本机的一键启动方式。

它也可以直接给人看，但写法是按"agent 能逐步执行、每步都能验证"来组织的。

---

## 0. 先读懂它的结构

```
MCMtools/
├── start              跨平台启动器（Python，macOS/Linux 直接执行）
├── start.sh           同上，权限丢失时的备用入口（sh start.sh）
├── start.bat          Windows 双击入口
├── build-app.sh       在 macOS 上生成 MCMtools.app
├── core/
│   ├── mcm            命令行入口
│   ├── mcmstart.py    启动器 shim
│   ├── mcmcore/       核心包（Python）
│   └── tests/         pytest 测试（371 个）
├── web/               面板（原生 ES module，无构建步骤）
└── templates/         图表 / 实验 / 论文模板（比赛期间的现成资产）
```

**关键设计**：`start`、`start.bat`、`MCMtools.app` 三者都只是外壳，
真正的逻辑全在 `core/mcmcore/launcher.py`。所以**任何平台只要能跑起 `start`，
就等于完成了部署**，不需要为每个平台重写逻辑。

---

## 1. 目标机器上需要什么

| 依赖 | 是否必需 | 说明 |
|---|---|---|
| Python 3.9+ | **必需** | 唯一的硬要求。3.9 是下限，因为代码里统一用 `Optional[X]` 而非 `X \| None` |
| pip 依赖 | 必需 | pydantic / pyyaml / numpy / matplotlib / fastapi / uvicorn / pandas / jinja2 |
| TeX Live | 可选 | 没有它只是不能生成 PDF；审计和面板照常工作 |

Python 依赖**不需要你手动判断**——`start` 会自己检测，缺什么装什么。

---

## 2. 部署步骤

### 第 1 步：确认 Python 版本

```bash
python3 -c "import sys; print(sys.version_info[:2])"
# 期望 (3, 9) 或更大
```

Windows 上：

```bat
py -3 -c "import sys; print(sys.version_info[:2])"
```

**如果版本不够**，先装 Python 再继续。不要试图降级代码去适配老版本——
`core/mcmcore/schemas/` 里大量使用 pydantic v2 的写法，改动面比装 Python 大得多。

### 第 2 步：跑环境检查（不做任何修改）

```bash
cd MCMtools
./start --check
```

Windows：`py start --check`

这会打印一张表，每行是 `[正常]/[缺失]/[可选]`。**先跑这一步再动手**，
因为它只读不写，能让你知道到底缺什么。

### 第 3 步：安装缺失的依赖

```bash
./start --port 8420
```

`start` 会自动检测并安装缺失项，然后起服务、开浏览器。

如果自动安装失败（常见于企业网络、需要代理、pip 被限制），手动装：

```bash
python3 -m pip install --user pydantic pyyaml numpy matplotlib fastapi uvicorn pandas jinja2
```

**不要用 `sudo pip install`**——会把系统 Python 搞乱，而且 macOS 上大概率失败。

### 第 4 步：验证

```bash
python3 -m pytest core/tests -q
```

期望：`276 passed`。**这是判断部署成功的唯一标准**，不要靠"看起来起来了"。
测试全绿说明 schema、编译器、运行器、API、模式强制都正常。

再验证面板：

```bash
./core/mcm --dir examples/demo_pcql serve --port 8455
# 另一个终端：
curl -s http://127.0.0.1:8455/api/health
# 期望 {"ok":true,...}
```

面板测试（需要 Node.js 18+，可选）：

```bash
cd web && npm install && npm test
```

---

## 3. 按平台做一键启动

### macOS

```bash
./build-app.sh
open MCMtools.app
```

生成的是**指向当前目录的薄壳**，不打包代码。改了 `core/` 或 `web/`，
下次启动就是新的，不需要重新构建。

> ### ⚠️ 最重要的一条：不要放在桌面 / 文稿 / 下载 里
>
> macOS 用 TCC 保护 `~/Desktop`、`~/Documents`、`~/Downloads`。程序放在这三个
> 目录下时，**沙箱会在内核层拒绝它读取自己的文件**：
>
> ```
> kernel: (Sandbox) System Policy: Python(91272)
>         deny(1) file-read-data /Users/.../Desktop/MCMtools/core
> ```
>
> 表现是"双击了但什么都没发生"。这是内核拒绝，**Python 侧无法绕过**：
> 我试过 `exec ./start`、试过把引导代码用 `-c` 内联、试过 `exec python3 -c`，
> 全都会被拦 —— 因为 `import mcmcore` 本身就要读 `core/` 目录。
>
> **唯一的解法是把整个文件夹移出受保护目录**：
>
> ```bash
> mv ~/Desktop/MCMtools ~/MCMtools      # 主目录不受保护
> cd ~/MCMtools && ./build-app.sh
> open MCMtools.app
> ```
>
> `MCMtools.app` 里有预检：读不到自己的 `core/` 时会弹一个中文提示框告诉你
> 该怎么办，而不是静默失败。

`build-app.sh` 会调用 `xattr -cr` 清掉扩展属性。不清的话 `codesign` 会因为
"resource fork, Finder information, or similar detritus not allowed" 失败，
而且会**静默地**留下一个没签名的包。

另一个坑：`build-app.sh` 里生成启动脚本必须用**带引号**的 heredoc
（`<<'LAUNCHER'`）。用不带引号的 heredoc 或者一串 `echo '...'` 拼接时，
内容里只要出现一个 `${...}` 或 `$(...)` 就会在**构建期**被求值 ——
曾经因此让 `./build-app.sh` 卡死（它在打包阶段把服务器拉起来了），
或者生成出一个引号错位的脚本。

### Windows

直接双击 `start.bat`。它会依次尝试 `py -3` 和 `python`。

想做成桌面快捷方式：

```bat
powershell -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%USERPROFILE%\Desktop\MCMtools.lnk'); $s.TargetPath='C:\path\to\MCMtools\start.bat'; $s.WorkingDirectory='C:\path\to\MCMtools'; $s.Save()"
```

### Linux

```bash
chmod +x start.sh
./start.sh
```

桌面启动器（`.desktop` 文件）：

```ini
[Desktop Entry]
Type=Application
Name=MCMtools
Exec=/opt/MCMtools/start.sh
Path=/opt/MCMtools
Terminal=true
Categories=Education;Science;
```

`Terminal=true` 是必要的——用户需要看到首次运行的依赖安装进度。

---

## 4. 给人打包（拷贝给队友）

要拷给别人的话，**不要复制这些**：

```
web/node_modules/     # 面板测试用，接收方自己 npm install
**/__pycache__/
.pytest_cache/
examples/*/build/     # 构建产物，每次重新生成
MCMtools.app          # 与生成它的机器绑定，对方自己跑 build-app.sh
```

其余的都可以拷。接收方只需要有 Python 3.9+，然后 `./start`。

**验证打包是否完整**：在一台没装过依赖的机器上解压后跑
`./start --check`，再跑 `python3 -m pytest core/tests -q`。

---

## 5. 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `./start: Permission denied` | 权限位在传输中丢了 | `chmod +x start` 或改用 `sh start.sh` |
| `SyntaxError: unsupported operand type(s) for \|` | Python < 3.10 且读到了 PEP 604 写法 | 不应该发生；代码统一用 `Optional`。若出现，说明有文件被改坏了 |
| `Address already in use` | 端口被占 | 不用管，`start` 会自动换端口并提示 |
| 浏览器打开是"无法连接" | 服务还没起来就打开了 | 已处理：只有端口应答之后才开浏览器。若仍发生，手动刷新即可 |
| `ModuleNotFoundError: No module named 'mcmcore'` | 没通过 `start` / `core/mcm` 进入 | 用入口脚本，别直接 `python3 core/mcmcore/cli.py` |
| 面板显示"连不上 MCMtools 服务" | 服务已停，页面还开着 | 重新运行 `./start`，然后刷新 |
| macOS `.app` 报 Operation not permitted | TCC 保护目录 | 见上文第 3 节 macOS 部分 |
| pip 安装超时 | 网络/代理 | 用国内镜像：`-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 选了新版 Python 却报缺包 | 版本号不等于可用性 | 已处理：`mcmboot.py` 会逐个探测依赖，选齐全的那个 |
| `SSLCertificateError` 装不上包 | Python 缺根证书 | macOS 上跑一次 `/Applications/Python*/Install\ Certificates.command` |

---

## 5.5 部署完先跑一遍这些命令

```bash
./core/mcm doctor                 # 环境自检
./core/mcm status                 # 项目状态摘要
./core/mcm math show              # 看符号表、公式、假设
./core/mcm param list             # 看参数及其来源
./core/mcm exp run EXP-001        # 跑一个实验
./core/mcm exp runs EXP-001       # 看运行归档
./core/mcm paper scaffold         # 把论文填空骨架补进来
./core/mcm paper build            # 编译论文
./core/mcm validate               # 审计
./core/mcm overview               # 状态与待办
```

面板侧：`./start <项目目录>` 然后打开 http://127.0.0.1:8420 。
顺序建议 **总览 → 数学内容 → 参数 → 实验 → 生图工作台 → 论文**，
这也是侧栏的分组顺序。

模板库怎么用见 `docs/templates.md`。

---

## 6. 你不该做的事

- **不要引入打包器或框架**。面板刻意用原生 ES module。把它改成 Vue/React 会让
  用户在比赛期间运行的东西变成一条他无法检查的工具链的产物。
- **不要为某个平台重写启动逻辑**。逻辑在 `launcher.py` 里，外壳只负责找到
  Python 然后 exec 它。加平台分支会让三个入口慢慢漂移。
- **不要跳过测试来判断成功**。`pytest core/tests` 全绿才是部署完成。
- **不要在竞赛模式下联网**。`mode` 是 `competition` 时会装网络拦截；
  如果你的部署脚本在此时联网，会被拦截并记录在 `blocked_outbound` 里。
