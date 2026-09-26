# 给 AI 助手的现成提示词（部署 / 打包 / 排障）

赛前没空自己动手时，把下面对应的一段**整块复制**给任意 AI 编码助手
（Claude Code、Cursor、DeepSeek、Codex 都行），它就能替你完成部署、
打包 `.app`、做分发包和排障。

提示词是**自包含**的：agent 没读过本仓库文档也能照做，每段都自带
背景、步骤、验收标准和禁区。它们只覆盖"把工具跑起来、包起来、修起来"；
比赛里怎么用工具，看三份角色指南（见 [README](../README.md) 的文档表）。

---

## 用之前知道三件事

1. **整段复制，别只复制命令。** 背景、验收标准、禁区都写在提示词里，
   拆开了给，agent 容易自作主张。
2. **验收以命令输出为准。** `./core/mcm deploy` 报 101 个模板、
   `/api/health` 返回 `{"ok":true,...}` 才算完成。
   agent 说"应该可以了"不算数。
3. **一次只给一段。** 做完一段、验收通过，再给下一段。

提示词里的 `<MCMtools>`、`<现象>` 这类尖括号是占位符：
复制前替换成实际值，或者原样发 —— agent 会先问你。

每段都写死了同一条纪律：**agent 不修改本仓库的代码和模板，只做部署动作；
不用 sudo；跑不通就原样报告输出，不要绕过。**

## 验收标准速查

| 检查 | 期望 |
|---|---|
| `python3 -c "import sys; print(sys.version_info[:2])"`（Windows 用 `py -3`） | `(3, 9)` 或更大 |
| `./core/mcm doctor` | 只读报告：缺什么、装什么，一个字不改 |
| `./core/mcm deploy` | `[正常] 模板库完整  101 个`、`[正常] 模板全部可加载  101 个`，结论"可以部署，一切就绪" |
| `curl http://127.0.0.1:8420/api/health` | `{"ok":true,...}` |
| `./core/mcm template list` | 能列出模板（figures 38、models 17、tables 13、experiments 9、paper 8、code 16） |

---

## 0. 通用部署 —— 任意机器，先给这段

````
你是在用户机器上工作的编码助手。请把 MCMtools（本地数学建模比赛工具链）
部署到可用状态。仓库位置用户会告诉你，下文记作 <MCMtools>。

【背景】
- 唯一硬依赖：Python ≥ 3.9。其余 pip 依赖（pydantic、pyyaml、numpy、
  matplotlib、fastapi、uvicorn、pandas、jinja2）由启动器自动安装，
  不要手动 pip install。
- 面板默认地址 http://127.0.0.1:8420。

【步骤】
1. 确认 Python 版本：
   - macOS/Linux：python3 -c "import sys; print(sys.version_info[:2])"
   - Windows：py -3 -c "import sys; print(sys.version_info[:2])"
   期望 (3, 9) 或更大。版本不够就停下，让用户先装 Python 3.9+。
   不要修改仓库代码去兼容旧版本。
2. 在 <MCMtools> 下跑 ./core/mcm doctor（Windows 上无法直接执行时，
   以 start.bat 的输出为准）。它只读、不做任何修改，会报告缺什么并
   给出安装命令。
3. 启动：
   - macOS/Linux：./start ~/mcm/2026A
     （报 Permission denied 时先 chmod +x start，或 sh start.sh）
   - Windows：命令行运行 start.bat
   项目目录不存在会自动创建。首次运行会装依赖，终端显示进度，等它装完。
   端口被占时换一个：./start --port 9000。
4. 另开一个终端按【验收】检查。

【验收（全部满足才算完成）】
- ./core/mcm deploy 输出两行 [正常]：模板库完整 101 个
  （figures 38、models 17、tables 13、experiments 9、paper 8、code 16）、
  模板全部可加载 101 个，结论"可以部署，一切就绪"
- curl http://127.0.0.1:8420/api/health 返回 {"ok":true,...}
- 面板能在浏览器打开

【禁区】
- 不用 sudo 跑 ./start（会弄乱文件属主）
- 项目目录不要建在 <MCMtools> 里面（升级时会混在一起）；
  macOS 上还不要放 ~/Desktop、~/Documents、~/Downloads
  （双击 .app 启动时系统权限会拦住，读不到文件），放 ~/mcm/ 下最省事
- 不修改仓库里的任何代码、模板、文档

【汇报】完成后报告：Python 版本、装了哪些依赖、面板地址、deploy 的模板数。
任何一步没过，原样贴出命令输出，不要说"应该可以了"。
````

---

## 1. macOS：打包 `.app`

````
你是在 macOS 上工作的编码助手。MCMtools 仓库在 <MCMtools>（用户会告诉你）。
请生成并验证可双击的 MCMtools.app。

【背景】
- ./build-app.sh 生成 MCMtools.app。App 是自包含的：core/、templates/、
  web/ 会拷进 Contents/Resources/，所以 App 可以单独移动或拷到别的目录，
  不需要旁边留着仓库。
- 签名是 ad-hoc（本机）的，这是设计选择，不做公证。

【步骤】
1. cd <MCMtools> && ./build-app.sh，确认生成 MCMtools.app。
2. open MCMtools.app 做冒烟测试，等浏览器自动打开面板
   （默认 http://127.0.0.1:8420）。
3. 验证：./core/mcm deploy 必须报模板 101 个；
   curl http://127.0.0.1:8420/api/health 返回 {"ok":true,...}。
4. 向用户交代三件事：
   - 第一次双击 macOS 会拦（未公证）：到「系统设置 → 隐私与安全性」
     点"仍要打开"。拷到别的机器还会再拦一次，同样放行即可，
     App 本身自包含，不必重新构建。
   - App 启动时找代码的顺序：① 环境变量 MCMTOOLS_HOME 指到的仓库
     ② App 包内 Contents/Resources/ ③ 从 App 位置上溯到的仓库。
     仓库还在原处时跑的是仓库那份（改了 core/、web/ 下次启动生效，
     不用重建）；把 App 单独拷走时，自动退回包里那份。
   - 实际用的是哪条路径，看面板「设置 → 安装与路径」——
     那里显示的就是程序真正在用的值。以后"模板不见了"先看这里。
5. 提醒用户把项目目录放 ~/mcm/ 下：macOS 的 TCC 权限会在内核层拒绝
   双击启动的 App 读取 ~/Desktop、~/Documents、~/Downloads 下的文件。
   终端跑 ./start 不受影响，双击 .app 就会读不到项目文件。

【禁区】不要重新签名或公证；不要手动改动 App 包内的 Contents/Resources；
不要修改仓库代码。

【汇报】App 路径、deploy 的模板数、health 返回；没过的步骤原样贴输出。
````

---

## 2. Windows：部署

````
你是在 Windows 上工作的编码助手。请把 MCMtools 跑起来。仓库在 <MCMtools>。

【步骤】
1. py -3 -c "import sys; print(sys.version_info[:2])" 确认 ≥ (3, 9)。
   没有 Python 就去 python.org 装 3.9+，安装时必须勾选
   "Add Python to PATH"，装完重开终端再继续。版本不够不要改代码适配。
2. 命令行进入 <MCMtools>，运行 start.bat（Windows 的启动入口）。
3. 首次运行会自动安装 pip 依赖（pydantic、pyyaml、numpy、matplotlib、
   fastapi、uvicorn、pandas、jinja2），终端显示进度，等它装完，
   不要手动 pip install。
4. 验证：
   - 浏览器打开 http://127.0.0.1:8420，面板能显示、模板数正常
   - curl http://127.0.0.1:8420/api/health 返回 {"ok":true,...}
   - 如果 core\mcm 在你的环境里无法直接调用，就以 start.bat 的输出
     和面板显示为准，不要为这件事修改任何文件
5. 项目目录建议放 C:\mcm\2026A 这类独立位置，不要放在 <MCMtools> 里面。

【禁区】不用管理员权限跑 start.bat；不改仓库代码、模板、文档。
start.bat 与 macOS/Linux 的 ./start 是同一套外壳逻辑（见 DEPLOY.md），
参数不生效时以运行输出提示为准。

【汇报】Python 版本、装了哪些依赖、面板地址；没过的步骤原样贴输出。
````

---

## 3. Linux：部署

````
你是在 Linux 上工作的编码助手。请把 MCMtools 跑起来。仓库在 <MCMtools>。

【步骤】
1. python3 -c "import sys; print(sys.version_info[:2])" 确认 ≥ (3, 9)。
   版本不够就停下让用户先装，不要改代码适配。
2. cd <MCMtools>；拷贝过来权限丢失时：chmod +x start（或直接 sh start.sh）。
3. ./start ~/mcm/2026A。首次运行自动装依赖，等它装完。
   端口被占时 ./start --port 9000。
4. 验证：./core/mcm deploy 报模板 101 个；
   curl http://127.0.0.1:8420/api/health 返回 {"ok":true,...}。
5. 可选：桌面环境里建一个 .desktop 文件，Exec 指向 <MCMtools>/start。
   做完告诉用户文件放在哪。

【禁区】不用 sudo 跑 ./start；项目目录不放 <MCMtools> 里面；
不修改仓库代码。

【汇报】Python 版本、装了哪些依赖、面板地址、deploy 的模板数。
````

---

## 4. 打分发包给队友

````
你在用户的机器上工作。任务：把 MCMtools 打成干净的压缩包，
交给没用过的队友。仓库在 <MCMtools>。

【步骤】
1. 清理不该带走的东西（在 <MCMtools> 下）：
   rm -rf node_modules web/node_modules
   rm -rf .pytest_cache **/__pycache__
   rm -rf examples/*/build examples/*/runs examples/*/code/output
   rm -rf MCMtools.app
2. 打包（在 <MCMtools> 的上一级目录）：
   tar czf MCMtools.tar.gz MCMtools    # 或 zip -r MCMtools.zip MCMtools
3. 核对必带清单：start、core/（含 core/mcm）、web/、templates/、start.bat。
   建议把 docs/ 也带上，队友可以自助排障。
4. 核对别带：node_modules/、__pycache__/、MCMtools.app/、
   任何项目数据或论文。
5. 模拟验收：把压缩包解到一个临时目录，按"通用部署"流程走一遍 ——
   至少跑 ./core/mcm deploy，必须报 101 个模板。

【重点】templates/ 是最容易漏的目录。漏了它服务照常启动、接口照常响应、
全程不报错，用户要到想画图时才发现模板少了一半。
所以验收必须数模板数，不能只看服务起没起来。

【汇报】包的路径和大小、解包验收的 deploy 输出。

【禁区】不修改仓库内容；不把用户的项目数据打进包里。
````

---

## 5. 排障

````
你在用户的机器上工作。用户报告 MCMtools 出了问题。
现象：<让用户填，例如"面板打不开"/"模板数不对"/"实验跑完结果页是空的"/
"PDF 编译失败">。仓库在 <MCMtools>，项目目录通常在 ~/mcm/ 下。

【工作方式：先收集，再动手】
1. 收集信息（全部只读）：
   - cd <MCMtools> && ./core/mcm doctor
   - ./core/mcm report --out diag.txt —— 生成版本、系统、依赖、模板数、
     项目结构计数，不含论文正文；让用户把这个文件发给你
   - 启动失败：./core/mcm serve 看真实报错
   - 实验失败：<项目>/runs/EXP-xxx/RUN-xxx-xxx/stderr.txt 有完整 traceback
2. 按这张表逐个对照：

   | 现象 | 原因 | 处理 |
   |---|---|---|
   | Permission denied 跑 ./start | 拷贝时权限丢了 | chmod +x start 或 sh start.sh |
   | ModuleNotFoundError | 依赖没装上 | ./core/mcm doctor 看缺什么 |
   | 模板数少于 101 | templates/ 没拷全 | 重新拷，再跑 deploy |
   | 端口被占 | 上一个进程没退 | ./start --port 9000 换端口 |
   | .app 双击读不到项目文件 | 项目放在了桌面 | 项目移到 ~/mcm/ 下 |
   | 面板里模板数 0 / 找不到模板 | 路径没指对 | 面板「设置 → 安装与路径」看实际路径 |
   | 编译报缺字体 | 系统没中文字体 | ./core/mcm doctor |
   | 面板打不开 | 服务没起来 | 看终端输出，或 ./core/mcm serve 看报错 |

3. 诊断时先看三件事：版本对不对、模板数够不够（应 101）、
   依赖齐不齐（没有 pdflatex 只影响出 PDF，不影响审计、面板、跑实验）。

【禁区】不要改仓库代码来"修"问题；不要 sudo；
不要重装系统级 Python；不要在比赛期间做 git pull 升级。

【汇报】原因判断、做了什么、用户自己怎么复验。
修不了就把 diag.txt 和相关 stderr 原样交给用户。
````

---

## 6. 比赛前的离线就绪检查

````
你在用户的机器上工作。任务：比赛开始前做一次离线就绪检查。
仓库在 <MCMtools>。全程可以断网做 —— 比赛期间不依赖网络是这套工具的设计目标。

【步骤】
1. cd <MCMtools> && ./core/mcm doctor
2. ./core/mcm deploy —— 必须报模板 101 个
3. ./core/mcm template list | head —— 模板能读出来
4. ./core/mcm --dir ~/mcm/2026A paper engine —— 看有哪些 TeX 引擎。
   （还没有项目目录的话，先 ./start ~/mcm/2026A 启动一次，自动创建。）
   没有 pdflatex 只是不能编译 PDF，审计、面板、出图都正常；
   比赛要交 PDF 就得装 TeX Live / MacTeX，由用户决定。
5. 断网（或关 Wi-Fi）状态下再 ./start 起一次面板，
   确认能打开、模板数正常。
6. ./core/mcm report --out diag.txt 存一份 ——
   比赛期间出问题可以直接把这个文件发出去。

【汇报】逐项列结果：通过 / 不通过 + 关键输出。
有不通过的项，改用"排障"提示词处理。

【禁区】不要升级（比赛前不做 git pull，除非遇到阻断性问题）；
不改代码。
````

---

## 7. 升级（平时；比赛期间别做）

````
你在用户的机器上工作。任务：把 MCMtools 升级到最新版。
仅限平时执行；比赛期间不要跑这一段。仓库在 <MCMtools>。
用户的项目目录在别处（通常 ~/mcm/ 下），升级不碰它。

【步骤】
1. cd <MCMtools> && git pull
2. ./core/mcm deploy —— 确认模板仍是 101 个
3. 如果 <MCMtools> 不是 git 仓库（是当初拷贝来的）：不要就地覆盖。
   问用户之后，重新 clone 一份到旁边，确认新目录 deploy 通过，
   旧目录的去留由用户决定。
4. 提醒用户：项目目录与本体分开，git pull 不会影响论文和数据；
   升级完各端下次启动自动用新代码。

【禁区】不动项目目录；不删旧目录；不改代码。
````

---

## 相关

- 部署原理与各平台细节 → [DEPLOY.md](DEPLOY.md)
- 项目概览与快速开始 → [README](../README.md)
- 三个角色的使用指南 → [molderread.md](molderread.md) / [coderread.md](coderread.md) / [writerread.md](writerread.md)
