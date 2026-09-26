# 部署到另一台机器

把 MCMtools 拷到新电脑上，让它跑起来。原则上**只要有 Python 3.9+ 就能用**。

---

## 一、先搞清楚它的结构

```
MCMtools/
├── start              跨平台启动器（macOS/Linux 直接执行）
├── start.sh           备用入口（权限丢失时用 sh start.sh）
├── start.bat          Windows 双击入口
├── build-app.sh       macOS 上生成 MCMtools.app
├── core/
│   ├── mcm            命令行入口
│   └── mcmcore/       核心包
├── web/               面板（原生 ES module，无构建步骤）
└── templates/         101 个模板（比赛期间的现成资产）
```

**关键设计**：`start`、`start.bat`、`MCMtools.app` 都只是外壳，
真正的逻辑全在 `core/mcmcore/launcher.py`。

所以**任何平台只要能跑起 `start`，就等于部署完成**，
不需要为每个平台重写逻辑。

---

## 二、目标机器需要什么

| 依赖 | 是否必需 | 说明 |
|---|---|---|
| **Python 3.9+** | **必需** | 唯一的硬要求 |
| pip 依赖 | 必需 | pydantic / pyyaml / numpy / matplotlib / fastapi / uvicorn / pandas / jinja2 |
| TeX Live | 可选 | 没有它只是不能生成 PDF；审计和面板照常 |

Python 依赖**不用手动判断** —— `start` 会自己检测，缺什么装什么。

---

## 三、部署步骤

### 第 1 步：确认 Python 版本

```bash
python3 -c "import sys; print(sys.version_info[:2])"
# 期望 (3, 9) 或更大
```

Windows：

```bat
py -3 -c "import sys; print(sys.version_info[:2])"
```

版本不够就先装 Python，**不要改代码去适配老版本**。

### 第 2 步：环境检查（不做任何修改）

```bash
cd MCMtools
./core/mcm doctor
```

它会报告缺什么、给出现成的安装命令。这一步**只读**，不会装东西。

### 第 3 步：启动

```bash
./start ~/mcm/2026A
```

第一次运行会自动装缺失的依赖，终端里显示进度。
装完浏览器自动打开面板。

> 依赖装在哪：如果用系统 Python，是用户级安装（`pip install --user`），
> 不需要 sudo，也不会污染系统包。

### 第 4 步：验证

```bash
./core/mcm deploy
```

期望输出：

```
[正常] 模板库完整  101 个（figures 38、models 17、tables 13、experiments 9、paper 8、code 16）
[正常] 模板全部可加载  101 个

结论：可以部署，一切就绪。
```

再确认服务活着：

```bash
curl http://127.0.0.1:8420/api/health
# 期望 {"ok":true,...}
```

---

## 四、各平台的一键启动

### macOS

生成可双击的 App：

```bash
./build-app.sh
```

会生成 `MCMtools.app`。第一次双击时 macOS 会拦一下：

> 打开「系统设置 → 隐私与安全性」，点"仍要打开"。

**注意**：`MCMtools.app` 带着本机签名信息，**换机器要重新生成**，
不要直接拷贝。

### Windows

双击 `start.bat`。

如果提示缺少 Python，去 python.org 装 3.9 以上版本，
安装时**勾选 "Add Python to PATH"**。

### Linux

```bash
chmod +x start
./start ~/mcm/2026A
```

桌面环境里可以建个 `.desktop` 文件指向 `start`。

---

## 五、拷给队友

**整个 `MCMtools/` 文件夹拷过去就行**，但要先清理：

```bash
# 删掉不该带走的
rm -rf node_modules web/node_modules
rm -rf .pytest_cache **/__pycache__
rm -rf examples/*/build examples/*/runs examples/*/code/output
rm -rf MCMtools.app
```

然后打包：

```bash
cd ..
tar czf MCMtools.tar.gz MCMtools
# 或 zip -r MCMtools.zip MCMtools
```

**必带**：`start`、`core/`、`web/`、`templates/`、`start.bat`、`core/mcm`
**别带**：`node_modules/`、`__pycache__/`、`MCMtools.app/`、项目数据

> **最容易漏的是 `templates/`。** 漏了它模板会从 101 个变成几十个，
> 而服务照常启动、接口照常响应、**全程不报任何错**，
> 用户要到想画图时才发现。所以拷完一定跑 `./core/mcm deploy` 数一遍。

---

## 六、常见故障

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `Permission denied` 跑 `./start` | 拷贝时权限丢了 | `chmod +x start` 或 `sh start.sh` |
| `ModuleNotFoundError` | 依赖没装上 | `./core/mcm doctor` 看缺什么 |
| 模板数少于 101 | `templates/` 没拷全 | 重新拷，再跑 `deploy` |
| 端口被占 | 上一个进程没退 | `./start --port 8420` 换端口 |
| `.app` 双击读不到项目文件 | 项目放在了桌面 | 项目移到 `~/mcm/` 下 |
| 编译报缺字体 | 系统没中文字体 | `./core/mcm doctor` |
| 面板打不开 | 服务没起来 | 看终端输出，或 `./core/mcm serve` 看报错 |

### 关于"项目不能放桌面"

macOS 的 TCC 权限会**在内核层拒绝** launchd 启动的 App 读取
`~/Desktop`、`~/Documents`、`~/Downloads`。

从终端跑 `./start` 没事（终端自己有权限），
但双击 `MCMtools.app` 且项目在桌面时就会读不到文件。

**建议项目放 `~/mcm/` 或 `~/Projects/`。**
这条不是猜测 —— 系统日志里能看到 `file-read-data` 被拒。

---

## 七、部署完先跑一遍

```bash
./core/mcm doctor                        # 环境
./core/mcm deploy                        # 目录完整性 + 模板数
./core/mcm template list | head          # 模板能读出来
./core/mcm report --out diag.txt         # 诊断报告
```

`report` 会生成版本、系统、依赖、模板数、项目结构计数。
**不含论文正文**，只报数量 —— 出问题时附上这个文件即可。

---

## 八、升级

现在是 git 仓库，直接拉：

```bash
cd MCMtools
git pull
```

**不会影响你的项目目录** —— 项目在 `~/mcm/` 下，跟本体分开。

如果本体是拷贝来的（不是 clone），建议重新 clone 一份，
然后把项目目录指过去。

升级完跑一次 `./core/mcm deploy` 确认。

---

## 九、不要做的事

- **别用 `sudo` 跑 `./start`** —— 会把文件属主改乱，之后普通用户改不动
- **别把项目建在 `MCMtools/` 里面** —— 升级时会混在一起
- **别直接拷 `MCMtools.app`** —— 签名绑机器，拷过去打不开
- **别删 `templates/` 里的任何东西** —— 模板之间会互相引用
- **别在比赛期间升级** —— 除非遇到阻断性问题

---

## 相关

- 项目概览与快速开始 → [README](../README.md)
- 三个角色的使用指南 → [molderread.md](molderread.md) / [coderread.md](coderread.md) / [writerread.md](writerread.md)
