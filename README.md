# MCMtools

数学建模竞赛（MCM/ICM）的生产工具链：**赛前用 AI 辅助开发，比赛期间全程本地离线运行。**

比赛那几天不该依赖任何在线服务 —— 网络会断、额度会用完、服务会排队。
所以核心功能（模板、生图、编译、审计）全部本地跑，不联网。

---

## 快速开始

```bash
git clone https://github.com/Neiyako/MCMtools.git
cd MCMtools

./start ~/Desktop/我的项目     # 指定项目目录（不存在会自动创建）
```

浏览器会自动打开面板。第一次运行会装几个 Python 包，终端里显示进度。

常用参数：

```bash
./start                # 在当前目录启动
./start --check        # 只检查环境，不启动
./start --port 8420    # 指定端口
```

**Windows**：双击 `start.bat`。
**macOS**：`./build-app.sh` 生成 `MCMtools.app` 后可双击启动。

**只要求系统里有 Python 3.9+**，不用预装别的。TeX Live 可选 ——
没有它只是不能编译 PDF，审计、面板、出图都照常。

### 确认装好了

```bash
./core/mcm deploy
```

```
[正常] 模板库完整  101 个（figures 38、models 17、…、code 16）
[正常] 模板全部可加载  101 个

结论：可以部署，一切就绪。
```

有问题时退出码非 0 并给出具体修法。

---

## 它解决什么问题

不是"帮你写论文" —— 是**把论文变成一件有据可查的事**。

比赛里最容易出的事故是：正文写"β = 0.31"，代码里跑出来是 0.313145，
而两者之间没有任何机制保证一致。改了一次参数，忘了改正文，
交上去的论文自己打自己。

MCMtools 的做法是让**每个数字只有一个来源**：

```
参数/实验  →  结果原子（数字）  →  正文里的宏  →  编译进 PDF
                    ↑                    ↓
                    └────── 审计：对不上就报错 ──────┘
```

正文里写 `\numBetaFit{}`，编译时替换成真实值。改了参数重跑，
正文自动跟着变，对不上的地方审计会报出来。

### 核心能力

| 能力 | 说明 |
|---|---|
| **模板库** | 101 个模板：图表 38、模型 17、表格 13、实验 9、论文 8、代码 16 |
| **结果追踪** | 数字有唯一来源，正文引用宏，改一处全篇一致 |
| **图表生成** | 一键出 PDF，中文字体已配好；另有自定图表工作台（27 种图型） |
| **论文编译** | LaTeX 一条命令编译，含参考文献 |
| **审计** | 检查数字是否绑定、图表是否被引用、占位符是否填完 |
| **离线** | 比赛期间不需要网络 |

---

## 模板库

比赛期间的现成资产，**101 个**：

```
templates/
├── figures/       38  时序、分布、热力、雷达、置信带、小提琴、排名变化…
├── models/        17  ODE、优化、评价、仿真、网络…
├── tables/        13  三线表
├── experiments/    9  实验协议
├── paper/          8  论文结构、章节骨架、参考文献
└── code/          16  可复制的 Python 代码骨架
```

`code/` 里的每个 `snippet.py` **直接能跑**（内置模拟数据），
改几处 TODO 就能换成你的数据。覆盖数据清洗、回归诊断、
时间序列、ODE 求解、参数拟合、蒙特卡洛、敏感性分析、
多目标优化、熵权 TOPSIS、AHP、元胞自动机、图论、聚类、排队论。

详见 [docs/template-library.md](docs/template-library.md)。

---

## 面板

| 页面 | 干什么 |
|---|---|
| 总览 | 当前阶段、待办、阻塞项 |
| 数据 | 数据集与字段 |
| 数学内容 | 符号、公式、假设 —— **可直接增删改** |
| 参数 | 参数表 —— **可直接增删改**，标注来源 |
| 实验 | 实验协议与运行 |
| 生图工作台 | 从模板一键出图 |
| 自定图表 | 27 种图型自己拼，可存成模板 |
| 参考文献 | **粘贴 BibTeX 导入**，自动核对正文引用 |
| 结果 | 结果原子（数字的唯一来源） |
| 论文 | 章节大纲与编译 |
| 审计 | 检查报告 |

---

## 文档

| 想了解 | 看 |
|---|---|
| **目录结构、什么能删** | [docs/project-layout.md](docs/project-layout.md) |
| 完整流程走一遍 | [docs/workbench-guide.md](docs/workbench-guide.md) |
| 部署到另一台机器 | [docs/DEPLOY.md](docs/DEPLOY.md) |
| 模板怎么用 | [docs/template-library.md](docs/template-library.md) |
| 面板怎么改参数、做图 | [docs/panel-editing.md](docs/panel-editing.md) |
| 架构与设计取舍 | [docs/mcmtools-architecture.md](docs/mcmtools-architecture.md) |
| **改代码 / 打补丁 / 排查故障** | [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) |

---

## 命令行

```bash
./core/mcm --dir ~/我的项目 status           # 项目状态
./core/mcm --dir ~/我的项目 validate         # 审计
./core/mcm --dir ~/我的项目 exp run EXP-001  # 跑实验
./core/mcm --dir ~/我的项目 paper build      # 编译论文
./core/mcm template list                     # 列出模板
./core/mcm deploy                            # 部署自检
./core/mcm doctor                            # 环境检查
./core/mcm report --out diag.txt             # 诊断报告（报 bug 时附上）
./core/mcm --version                         # 版本 + git 提交号
```

---

## 部署前自检

拷贝给别人之前，跑一下：

```bash
./core/mcm deploy
```

```
[正常] 模板库完整  101 个（figures 38、models 17、…、code 16）
[正常] 模板全部可加载  101 个

结论：可以部署，一切就绪。
```

**为什么需要它**：拷贝过程本身最容易出问题。漏拷一个
`templates/figures/`，模板会从 101 个变成 63 个 —— 而服务照常启动、
接口照常响应、**全程不报任何错**，用户要到想画图时才发现。
自检会数模板个数，就是防这个。

---

## 目录

软件本体和项目目录是分开的 —— 项目建在**任意位置**，不在本体里：

```
MCMtools/              软件本体
├── start              启动入口
├── core/              核心程序
├── web/               面板
├── templates/         模板库
├── docs/              文档
└── examples/          示例

~/我的项目/             项目目录（你自己定位置）
├── project.yaml
├── results/           结果原子
├── figures/  tables/  paper/
└── build/             编译产物
```

详见 [docs/project-layout.md](docs/project-layout.md)。

---

## 要求

- **Python 3.9+**（必需）
- **TeX Live / MacTeX**（可选，只有生成 PDF 需要）
- Node.js（可选，只有跑面板测试需要；面板本身不需要）

没有 pdflatex 也能用：审计、面板、出图都正常，只是不能编译 PDF。

---

## 设计原则

1. **比赛期间不依赖 AI、不依赖网络。** 核心功能全本地。
2. **数字只有一个来源。** 正文引用宏，不手抄数值。
3. **宁可报错，不要静默降级。** 模板加载失败就让启动失败，
   不装作没事 —— 少一半模板却"看起来正常"是最坏的情况。
4. **错误信息说人话。** 从 `Undefined control sequence` 猜病灶太难，
   所以报错直接说"缺哪个输入、该怎么填"。
5. **中文优先。** 字体、术语、报错都是中文 —— 中文字体不含
   `²`、`−` 这类字形，直接画会变成豆腐块，所以有专门的处理层。
