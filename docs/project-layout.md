# MCMtools 目录说明

这份文档回答一个问题：**哪个目录是什么，能不能删。**

判断标准只有一条：**它是不是软件本体的一部分。**

---

## 顶层

```
MCMtools/
├── start              一键启动（跨平台，Python）
├── start.sh           macOS / Linux 备用入口（权限丢失时用）
├── start.bat          Windows 双击入口
├── build-app.sh       生成 macOS 的 MCMtools.app（可选）
├── MCMtools.app       macOS 双击启动（build-app.sh 的产物，可删可重建）
│
├── core/              核心程序（Python）
├── web/               面板（浏览器界面）
├── templates/         模板库 ← 比赛期间的现成资产
├── docs/              文档
├── examples/          示例项目
└── .gitignore
```

**就这些。** 顶层没有别的东西 —— 没有 `results/`、没有 `figure/`、
没有 `project.yaml`。

### 为什么顶层没有项目目录

MCMtools 有两种目录，很容易搞混：

| | 软件本体 | 项目目录 |
|---|---|---|
| 是什么 | 程序本身 | 你的一次参赛 |
| 在哪 | `MCMtools/` | 任意位置，你自己选 |
| 内容 | `core/ web/ templates/ docs/` | `problems/ results/ paper/ figures/ …` |
| 谁创建 | 解压 / 拷贝得到 | `./start ~/我的项目` 自动创建 |

项目目录**不在软件本体里面**。你在哪里建项目都行：

```bash
./start ~/Desktop/2025美赛          # 建在这
./start /Volumes/U盘/我的项目        # 也可以
```

启动器发现目录不存在时会自动初始化（建 `project.yaml` 和各个子目录），
所以不需要预先准备。

> **为什么强调这一点**：本体目录里曾经混进过一整套项目骨架
> （空的 `results/`、`paper/`、`project.yaml`），是早期在本体目录里
> 直接启动留下的。后果是"这个 `project.yaml` 到底是谁的项目"变得
> 说不清，而且模板目录 `templates/figures/` 和项目目录 `figures/`
> 同名，拷来拷去极易搞错。现在本体保持纯净，只有一份。

---

## 本体内部

### core/ —— 核心程序

```
core/
├── mcm                命令行入口（./core/mcm --help）
├── mcmstart.py        启动器 shim
├── mcmcore/           核心包
│   ├── schemas/       数据结构定义（pydantic）
│   ├── compiler/      LaTeX 编译（main.tex / references.bib）
│   ├── templates.py   模板注册表
│   ├── sampledata.py  示例数据生成
│   ├── diyfig.py      自定图表引擎
│   ├── mcmplot.py     绘图中文字体处理
│   ├── citations.py   参考文献解析与核对
│   ├── validate.py    审计规则
│   ├── api.py         面板后端
│   ├── launcher.py    启动逻辑
│   ├── doctor.py      环境检查
│   └── deploy.py      部署自检
└── tests/             pytest 测试
```

**`launcher.py` 是唯一的启动逻辑**。`start`、`start.bat`、`MCMtools.app`
都只是外壳，都调用它 —— 所以命令行能跑通的，双击也一定跑得通。

### web/ —— 面板

```
web/
├── index.html         页面骨架
├── app.js             全部界面逻辑
├── app.css            样式
├── strings.js         中文文案（界面上的字都在这）
├── tests/             面板测试（jsdom）
├── package.json
└── node_modules/      仅测试需要，删掉不影响使用
```

没有打包器、没有构建步骤，是刻意的：比赛期间不该出现
"构建失败所以用不了"这种情况。`node_modules` 只被测试用到，
删掉面板照常运行。

### templates/ —— 模板库

**比赛期间最该看的目录。** 101 个模板，分六类：

```
templates/
├── figures/       38  数据图（时序、分布、热力、雷达、置信带…）
├── models/        17  模型骨架（ODE、优化、评价、仿真…）
├── tables/        13  三线表
├── experiments/    9  实验协议
├── paper/          8  论文结构、章节、参考文献
└── code/          16  可复制的 Python 代码骨架
```

每个模板是一个目录，含 `template.yaml`（声明）和可选的
`render.py` / `snippet.py`（实现）。

`code/` 是**可复制粘贴的骨架**，不是完整程序。每个 `snippet.py`
直接 `python3` 就能跑（用内置模拟数据），改几处 TODO 就能换成你的数据。
输出默认写到临时目录，不污染模板库。

详见 `docs/template-library.md`。

### docs/ —— 文档

| 文件 | 讲什么 |
|---|---|
| `project-layout.md` | 本文件：哪个目录是什么 |
| `DEPLOY.md` | 部署到另一台机器 |
| `workbench-guide.md` | 从零跑通一遍的完整流程 |
| `template-library.md` | 101 个模板怎么用（含参考文献） |
| `panel-editing.md` | 面板里怎么改参数、做自定图表 |
| `mcmtools-architecture.md` | 架构与设计取舍 |
| `zh-terminology.md` | 中英术语对照 |
| `phase1-core.md` … `phase5-panel.md` | 分阶段的实现记录 |

### examples/ —— 示例

```
examples/
├── demo_pcql/         完整项目示例（可直接启动看效果）
├── mcm2023_C/         真实赛题样例论文（含 PDF 成品）
├── experiments/       实验协议示例
└── phase1_demo.py     最小演示脚本
```

示例项目里的 `build/`（LaTeX 产物）和 `runs/`（实验输出）**不入库**，
它们是运行产物，需要时重新生成：

```bash
./core/mcm --dir examples/demo_pcql exp run EXP-001
./core/mcm --dir examples/demo_pcql paper build
```

---

## 项目目录（你自己建的）

由 `./start <路径>` 创建，结构如下：

```
我的项目/
├── project.yaml       项目元信息：名称、阶段、模式、锁定的题目
├── problems/          题目与附件
├── data/              数据
├── math/              符号、公式、假设
├── params/            参数
├── models/            模型
├── experiments/       实验协议
├── runs/              运行记录
├── results/           结果原子（数字的唯一来源）
├── figures/           图表
├── tables/            表格
├── paper/             论文（paper.yaml + references.yaml + sections/）
├── build/             LaTeX 编译产物
├── audit/             审计报告
└── export/            导出
```

这些目录**不存在也没关系** —— 启动器会自动补齐缺的。
手动删掉某个空目录不会出问题。

---

## 什么可以删

| 能删 | 代价 |
|---|---|
| `MCMtools.app/` | 失去 macOS 双击启动，`./start` 照常；`./build-app.sh` 可重建 |
| `web/node_modules/` | 只影响跑面板测试，界面照常 |
| `examples/*/build/`、`examples/*/runs/` | 示例的编译/运行产物，可重新生成 |
| `docs/` | 只是文档 |
| `examples/` | 只是示例 |
| `__pycache__/`、`.pytest_cache/` | 缓存 |

## 什么不能删

| 不能删 | 为什么 |
|---|---|
| `core/` | 程序本体 |
| `web/`（除 `node_modules`） | 面板本体 |
| `templates/` | 模板库 —— 删了工具还是"能跑"，但你找不到任何现成资产 |
| `start` / `start.sh` / `start.bat` | 启动入口 |

> `templates/` 值得单独说：删掉一部分（比如只删 `figures/`）**不会报任何错**，
> 服务照常启动、接口照常响应，你到想画图时才会发现少了一半模板。
> 这正是 `./start --check` 会数字模板个数的原因。

---

## 部署前自检

```bash
./core/mcm deploy
```

它会检查：本体文件齐不齐、`start` 有没有执行权限、模板数对不对、
模板能不能真的加载、路径里有没有中文或空格。

```
[正常] 模板库完整  101 个（figures 38、models 17、tables 13、experiments 9、paper 8、code 16）
[正常] 模板全部可加载  101 个

结论：可以部署，一切就绪。
```

有问题时退出码非 0，并给出具体怎么修。
