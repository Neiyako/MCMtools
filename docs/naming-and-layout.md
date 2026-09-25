# 命名、范式与存放位置

这份文档回答三个问题：

1. **东西叫什么** —— ID、文件名、宏名的规则
2. **按什么套路做** —— 为什么是这个流程，不是别的
3. **放在哪里** —— 每个文件该进哪个目录

规则都是**从真实论文生产流程反推**的，不是先定规范再套用。
每条规则后面都写了"为什么"，因为不知道原因的人改不动它。

---

## 一、命名

### 1.1 对象 ID

全部用 `前缀-序号` 或 `前缀-语义`，**前缀固定、全大写、三段式以内**。

| 对象 | 格式 | 例子 | 谁生成 |
|---|---|---|---|
| 题目 | `PROB-<字母>` | `PROB-C` | 面板按题号自动生成 |
| 数据集 | `DS-<名字>` | `DS-SAMPLE` | 面板按文件名生成，可改 |
| 实验 | `EXP-<三位数>` | `EXP-001` | 自动递增 |
| 运行 | `RUN-<实验号>-<三位数>` | `RUN-001-014` | 每次执行自动分配 |
| 结果原子 | `RES-<语义或序号>` | `RES-1001` | 由实验产出 |
| 图 | `FIG-<三位数>` | `FIG-001` | 自动递增 |
| 表 | `TAB-<三位数>` | `TAB-001` | 自动递增 |
| 论文章节 | `SEC-<三位数>` | `SEC-010` | 自动递增 |

**为什么实验号段是三位数**：一场比赛做十几个实验，三位够用，
而且排序稳定（`EXP-002` 排在 `EXP-010` 前面，`EXP-2` 就不是了）。

**为什么章节编号是 10 递增**：`SEC-010 / SEC-020 / SEC-030`。
中间要插一节时用 `SEC-015`，不用把后面全部重编号。
真实的论文会反复调整章节顺序，省下的是重编号的功夫。

**为什么 RUN 不带实验名**：早先用的是 `RUN-<实验>-<序号>`，
重跑实验时编号会和上一轮撞车，新一轮的产物覆盖旧记录。
现在按运行序号全局递增（`runstore.py:92`），重跑不会撞。

### 1.2 题目的状态

`candidate` → `analysed` → `chosen` / `rejected`。

比赛第一天真实的工作方式是：**六道题全部登记，边读边排除**，
最后锁定一道。所以允许先建后改，不要求一次填对。

### 1.3 LaTeX 宏名 —— 这条最容易被误解

正文引用数字时用宏，宏名由结果原子的 ID 生成：

```
RES-0142                    ->  \numRESZeroOneFourTwo
RES-0142（渲染方式 Pct）     ->  \numRESZeroOneFourTwoPct
```

**数字被拼成英文单词，不是排版讲究，是 LaTeX 的硬限制**：
控制序列只能是字母，`\numRES0142` 是不合法的。

其余字符（连字符、下划线、点）全部丢弃。别名走 camelCase：

```
r_squared  ->  \numRSquared
beta       ->  \numBeta
```

> **注意**：别名里带数字会被丢掉（`R0` → `\numR`）。这是刻意的 ——
> 作者写别名时手滑不稀奇，为这个报错会打断写作。
>
> 但**同一个别名被两个原子用**时不会静默覆盖：后一个自动退回长名
> （`\numRESZeroZeroTwo`）。覆盖会让论文里某个数字悄悄变成另一个数的值。

### 1.4 面板与代码里的命名

| 场景 | 规则 | 例子 |
|---|---|---|
| 面板路由 | 全小写单词 | `figures`、`references` |
| 面板 DOM id | `kebab-case` | `#build-btn`、`#exp-create` |
| 表单字段 id | `fld-<字段名>` | `#fld-letter` |
| 数据属性 | `data-<动作>` | `[data-lock]`、`[data-run]` |
| Python 变量 | `snake_case` | `problem_id` |
| 模板目录 | `snake_case` | `templates/figures/dual_axis/` |
| 模板 ID | `<类>.<目录名>` | `fig.dual_axis`、`exp.monte_carlo` |

**模板 ID 和目录名必须对应**：`fig.dual_axis` 就是
`templates/figures/dual_axis/`。找模板时不用查表。

---

## 二、范式

### 2.1 核心范式：数字只有一个来源

**这是整个工具的立身之本。**

```
实验脚本  ->  结果原子（RES-xxx）  ->  宏（\numXxx）  ->  正文
                    ^                                    |
                    +---------- 审计比对 ------------------+
```

正文里**不允许出现手写的数字**。要引用某个结果就写宏：

```latex
Wordle 的预测精度为 \numRESOneZeroZeroOne{}，RMSE 为 \numRESOneZeroZeroTwo{}。
```

**为什么值得这么麻烦**：改一个参数重跑，正文自动跟着变。
没有这条链，改完参数要手工把正文里所有相关数字找出来改一遍 ——
漏一个就是"正文说 0.82，代码跑出来 0.79"，审稿人会抓住这个。

审计规则 `NUMERIC_UNBOUND` 会扫出正文里没绑定的数字。
不是结果数字的（页数、题目字母）用 `\lit{1}` 明确标为例外。

### 2.2 一切结论都要有来源

每个结果原子必须标明它是怎么来的：

| 来源 | 含义 | 论文里怎么写 |
|---|---|---|
| `literature` | 来自文献 | 引文献 |
| `dataset` | 从数据直接算出 | 说明数据来源 |
| `fitted` | 拟合得到 | 写清拟合方法和误差 |
| `assumed` | 假设值 | **必须说明这是假设** |

**这是诚实性问题，不是格式问题**。把假设值写得像测量值，
是建模论文最常见也最严重的毛病。

工具对此的处理：模拟数据一律标 `simulated`，
PCQL 的峰值预测失败（预测第 40 天，实际第 93 天）原样保留、不做调参美化。

### 2.3 模板是"从真实论文反推"的

每个模板的 `observed_in` 和 `evidence` 字段记录它来自哪几篇论文：

```yaml
observed_in: ~42% of 346 tagged papers have a numbered 'Sensitivity Analysis' section
evidence:
- '2023 C/2301192: ''In each parameter analysis, we only varied that parameter...'''
```

**为什么保留这些**：模板不是拍脑袋设计的，是统计出来的。
有人说"这个模板没用"时，可以拿证据反驳；发现证据过时了，也能改。

语料是 433 篇往届论文，现在放在仓库外（1.1G，且是版权作品）。

### 2.4 宁可启动失败，不要静默降级

模板的 YAML 校验是 `extra="forbid"`：写错字段名**不会报错，
模板会直接消失**。

曾经因此从 74 个模板掉到 28 个，而服务照常启动、接口照常响应、
全程不报错。现在加载走 `load_strict()`，缺模板会让启动失败。

**代价是启动更脆，收益是问题在第一时间暴露。**

### 2.5 报错要说人话

| 不好的报错 | 工具的报错 |
|---|---|
| `Undefined control sequence` | 缺哪个输入、该怎么填 |
| `no entrypoint declared` | `Set entrypoint: experiments/<exp>/run.py:run` |
| `invalid choice: 'data'` | 面板直接提供导入入口，不再让用户跑命令 |

### 2.6 界面不许承诺做不到的事

数据页曾经写着"用命令行导入数据"，而那条命令**从来不存在**。选题页曾经只显示状态、没有锁定按钮。

现在有测试盯着这两类问题：
- `test_docs_commands.py` 把文档里提到的命令逐条比对真实子命令
- `problems.test.mjs` 驱动真实 DOM 点按钮

**页面渲染正常不代表能干活** —— 坏掉的页面看起来很好看。

---

## 三、存放位置

### 3.1 两个"目录"要分清

这是最容易搞混的一点：

```
MCMtools/                    <- ① 软件本体（一份，克隆下来就不动）
├── core/                      核心代码
├── web/                       面板
├── templates/                 模板库
├── docs/                      文档
├── examples/                  示例项目
└── start  start.sh  start.bat

~/Desktop/我的比赛项目/        <- ② 项目目录（每场比赛一个）
├── project.yaml
├── problems/  data/  math/  params/
├── experiments/  runs/  results/
├── figures/  tables/  paper/
└── export/
```

**软件本体里不放任何一场比赛的数据**。升级工具时直接 `git pull`，
不会碰到你的论文。

### 3.2 项目目录里有什么

| 目录 | 放什么 | 谁写的 |
|---|---|---|
| `project.yaml` | 阶段、锁定题目、队伍号 | 面板 |
| `problems/` | 候选题目与读题笔记 | 面板 |
| `data/` | 原始数据文件 | 你自己放 |
| `datasets/` | 数据集登记（列名、类型、缺失值） | 导入时自动生成 |
| `math/` | 符号、公式、假设、目标、约束 | 面板 |
| `params/` | 参数、取值、来源 | 面板 |
| `experiments/` | 实验协议 + 运行脚本 | 面板建协议，脚本你写 |
| `runs/` | 每次运行的完整归档 | 运行实验时自动 |
| `results/` | 结果原子（正文引用的数字） | 运行实验时自动 |
| `figures/` | 图的声明 + PDF | 生图时自动 |
| `tables/` | 表的声明 | 面板 |
| `paper/` | 章节正文 | 正文你写，骨架工具补 |
| `build/` | LaTeX 中间产物和成品 PDF | 编译时自动 |
| `export/` | 打包提交用 | 导出时自动 |

**只有 `data/` 和 `paper/` 里的正文是你要手写的东西**，
其余由工具维护。`runs/`、`build/` 是产物，删了能重跑出来。

### 3.3 实验脚本放哪

```
experiments/EXP-001/
├── experiment.yaml      <- 协议（工具生成，别手改）
└── run.py               <- 你要写的脚本
```

协议里指向脚本：

```yaml
entrypoint: experiments/EXP-001/run.py:run
```

冒号后面是**函数名**。函数的契约：

```python
def run(trial: dict) -> dict:
    """收到一个参数字典，返回一组结果。

    trial 是本次试验的参数，例如 {'hard_mode_weight': 0.5}。
    返回的每个键值对会成为一个结果原子，正文用宏引用。
    """
    w = trial["hard_mode_weight"]
    return {"score": 1.0 / (1.0 + w)}
```

**注意是整份参数字典作为单个参数传入**，不是展开的关键字参数。
这一点踩过坑。

### 3.4 路径不要放桌面（macOS）

macOS 的 TCC 权限会**在内核层拒绝** launchd 启动的 App 读取
`~/Desktop`、`~/Documents`、`~/Downloads`。

从终端跑 `./start` 没问题（终端自己有权限），
但从 `MCMtools.app` 双击启动、项目又在桌面时，会读不到文件。

**建议放在 `~/mcm/` 或 `~/Projects/` 下。**
这条不是猜测 —— 是内核拒绝 `file-read-data`，日志里能看到。

### 3.5 哪些不入库

`.gitignore` 里排除了运行产物：

```
node_modules/        面板测试依赖（npm install 装回来）
examples/*/build/    编译中间产物
examples/*/runs/     运行归档
examples/*/code/output/   实验输出
__pycache__/  *.pyc  .pytest_cache/
MCMtools.app/        build-app.sh 的产物，带本机签名
```

**比赛项目本身也不该进工具仓库**。要备份就用 git 单独管你的项目目录。

---

## 四、一页速查

```
ID          PROB-C  DS-X  EXP-001  RUN-001-014  RES-1001  FIG-001  TAB-001  SEC-010
宏          \numRESOneZeroZeroOne{}    别名  \numRSquared{}
实验脚本    experiments/EXP-001/run.py:run
函数契约    def run(trial: dict) -> dict
软件本体    MCMtools/           （git pull 升级）
项目目录    ~/mcm/我的比赛/      （别放桌面）
要手写的    data/  和  paper/ 正文
```

改这些规则之前，先看这条规则后面写的"为什么"。
多数规则背后都对应一个真实踩过的坑。
