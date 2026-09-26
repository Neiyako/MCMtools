# 代码手使用指南

你负责：**把模型变成能跑出数字的代码**，并保证每个数字都能追溯。

面板给你搭好了项目结构，你只要往 `experiments/EXP-xxx/run.py` 里填模型。
这篇讲怎么填、怎么跑、数字怎么进论文。

> 工具还没跑起来？先看 [README 快速开始](../README.md)，
> 或整段复制[现成的部署提示词](AGENT_PROMPTS.md)让 AI 助手替你装好。

---

## 一、你要维护什么

```
你的项目/
├── data/              原始数据（放进去，只读）
├── experiments/
│   └── EXP-001/
│       ├── experiment.yaml   协议（面板生成，别手改）
│       └── run.py            ★ 你写
├── runs/              运行归档（自动生成）
└── results/
    └── atoms.yaml     结果原子（自动生成）
```

**你只写 `run.py`。** 其余由工具维护。
`runs/` 和 `build/` 是产物，删了能重跑出来。

---

## 二、运行脚本的确切契约

这是最容易写错的地方，先说清楚。

### 函数签名

```python
def run(trial: dict) -> dict:
    ...
```

协议里这样指向它：

```yaml
entrypoint: experiments/EXP-001/run.py:run
```

冒号后面是**函数名**。

> **整份参数字典作为「一个参数」传入**，不是展开成关键字参数。
> 即 `fn(dict(trial))`。这点和直觉相反，踩过坑。

### 返回值

**必须包在 `{"atoms": [...]}` 里。**

```python
def run(trial: dict) -> dict:
    w = trial["hard_mode_weight"]
    score = 1.0 / (1.0 + w)

    return {"atoms": [
        {"name": "score",
         "value": score,
         "macro_alias": "score",
         "direction": "higher_is_better",
         "unit": ""},
    ]}
```

| 返回 | 结果 |
|---|---|
| `{"atoms": [{"name":..., "value":...}]}` | ✅ 正确 |
| `[{"name":..., "value":...}, ...]` | ✅ 也可以，直接给列表 |
| `{"score": 0.79}` | ❌ **静默产生 0 个原子** |
| `None` | 不产生原子（只出图/存文件时用） |

**第三行是坑**：实验状态显示 `success`，不报任何错，结果页却是空的。
如果你跑完发现没有结果，"返回格式"是第一个要查的。

### 原子字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 结果名，会进原子 ID |
| `value` | 是 | 数值 |
| `atom_id` | 否 | 不填自动生成 `RES-EXP001-SCORE-001` |
| `macro_alias` | 否 | 短宏名，填了论文里写 `\numScore{}` |
| `direction` | 否 | `higher_is_better` / `lower_is_better` / `neutral` |
| `unit` | 否 | 单位 |
| `renderings` | 否 | 备用渲染，如 `{"pct": "79.1\\%"}` → `\numScorePct{}` |

**`direction` 只有那三个合法值。** 写成 `higher_better` 会报错，
报错信息很明确，照着改就行。

**强烈建议填 `macro_alias`。** 不填的话论文里得写
`\numRESEXPZeroZeroOneSCOREZeroZeroOne{}` 那种长名。

### 顺带产出文件

模型跑出来的中间数据想存下来：

```python
return {
    "atoms": [{"name": "score", "value": s}],
    "artifacts": ["output/sweep.csv"],   # 相对项目根目录
}
```

工具会把它们收进 `runs/EXP-001/RUN-001-001/` 并记录实际路径。

---

## 三、写一个实验：完整例子

### 0. 最快的一条路：用代码骨架

不用手写 `run.py`。步骤是：

**「实验」页 → 最下面「代码骨架」→ 选一个 → 填变动参数 → 建实验。**

工具会直接生成一个**能跑的** `run.py`：契约、atom 段落、模拟数据都
填好了，注释里标出「要改的就这三处」。建完脚本编辑器会自己打开，
改完点「保存并运行」，结果数字立刻进「结果」页。

| 在面板里做 | 等价于 |
|---|---|
| 选骨架 + 建实验 | 写 `experiments/EXP-xxx/run.py` + 填好 `entrypoint` |
| 页内改脚本 | 用编辑器改 `run.py` |
| 「保存并运行」 | `./core/mcm exp run EXP-xxx` |

保存时会做语法检查：有错就指出**第几行**并且**不落盘** ——
不会让一个坏文件先写进去、等运行时才报。

下面是手工路线，想知道每一步在干什么时看它。

### 1. 面板上建协议

「实验」页 →「套模板」选 `exp.sensitivity_oat` → 填名字 → 创建。

### 2. 填变动参数

在「变动参数」里填：

| 参数名 | 取值 |
|---|---|
| `hard_mode_weight` | `0.1, 0.5, 1.0` |

**这一步决定实验会不会真的跑多次。** 留空的参数保持不变；
不填的话只跑一次，出图没有横轴。

> 取值逗号分隔（中英文逗号都行）。填了变动参数，工具会展开成
> 3 次试验，每次传一个不同的 `trial`。

### 3. 写 run.py

```python
"""权重敏感性：看难度权重怎么影响预测精度。"""
from __future__ import annotations

import numpy as np


def model(w: float, data: np.ndarray) -> float:
    """你的模型。替换成真的。"""
    return float(np.exp(-w * data.mean()))


def run(trial: dict) -> dict:
    w = float(trial["hard_mode_weight"])
    data = np.loadtxt("data/wordle.csv", delimiter=",", skiprows=1)

    score = model(w, data)

    return {"atoms": [
        {"name": "score",
         "value": score,
         "macro_alias": "score",
         "direction": "higher_is_better"},
        {"name": "weight",
         "value": w,
         "macro_alias": "weight"},
    ]}
```

**路径注意**：脚本的工作目录是**项目根目录**，所以写
`data/wordle.csv`，不是 `../../data/wordle.csv`。

### 4. 跑

面板「实验」页点「运行」。

跑完看两个地方：

- 「运行记录」页 —— 每次运行的完整归档，失败能看到 `stderr.txt`
- 「结果」页 —— 产生的**结果原子**，论文要引用的数字

---

## 四、调试

### 结果页是空的

按这个顺序查：

1. **返回值格式** —— 是不是漏了 `"atoms"` 外层？这是最常见的原因
2. **`runs/EXP-001/RUN-xxx-xxx/stderr.txt`** —— 真实报错在这
3. **参数名对不上** —— `trial["x"]` 用了协议里没有的参数名 → `KeyError`

### 运行状态是 failed

`stderr.txt` 里有完整 traceback。常见的：

| 报错 | 原因 |
|---|---|
| `KeyError: 'xxx'` | `trial` 里没有这个参数，检查变动参数的拼写 |
| `FileNotFoundError` | 路径写错，记住工作目录是项目根 |
| `ValidationError ... direction` | `direction` 值非法，只有三个合法值 |
| `ModuleNotFoundError` | 缺依赖，`./core/mcm doctor` 看装了什么 |

### 重跑会不会覆盖

不会撞车。运行号全局递增（`RUN-001-001`、`RUN-001-002`……），
重跑产生新记录，旧的还在。

**结果原子的 ID 是稳定的**：同一格试验位复用同一个 ID。
所以重新拟合参数后，论文里引用的宏会**自动指向新值**，
工具也会把受影响的图标记为过期。

---

## 五、可直接用的代码骨架

`templates/code/` 下 16 个骨架，复制改比从零写快：

| 骨架 | 用途 |
|---|---|
| `sensitivity_analysis` | 单因子/双因子扫描 + Sobol 近似 |
| `monte_carlo_ci` | 蒙特卡洛 + 置信区间 |
| `data_cleaning` | 缺失值、异常值处理 |
| `descriptive_stats` | 描述统计 |
| `correlation_vif` | 相关性 + 多重共线性诊断 |
| `regression_diagnostics` | 回归诊断 |
| `parameter_fitting` | 参数拟合（最小二乘） |
| `ode_solve` | 常微分方程求解 |
| `ahp_evaluation` | 层次分析法 |
| `entropy_topsis` | 熵权 + TOPSIS |
| `kmeans_clustering` | K-means 聚类 |
| `arima_forecast` | 时间序列预测 |
| `cellular_automaton` | 元胞自动机 |
| `graph_shortest_path` | 最短路 / 网络 |
| `queueing_metrics` | 排队论指标 |
| `multiobjective_pareto` | 多目标 Pareto 前沿 |

看用法：

```bash
./core/mcm template show code.sensitivity_analysis
```

**面板里直接就能用**：「实验」页底部的「代码骨架」面板列出这 16 个，
选中 → 建实验 → 生成的 `run.py` 直接可跑，脚本编辑器就开在旁边。
不用手抄，也不用自己接协议。

每个骨架开头都写了「**要改哪几行**」，照着改就行。
里面的模型是模拟的，**记得替换成你自己的**。

> 生成的 `run.py` 是一层**适配**，不是骨架的副本：骨架本身是独立脚本
> （有自己的 `main()`、自己造数据、把图写到临时目录），签名和实验协议
> `run(trial) -> {"atoms": [...]}` 对不上。适配层保留契约、内嵌一个最小
> 模型，你只需要换掉 MODEL 那一段。

---

## 六、性能与健壮性

### 慢的模型

单次超过几分钟的话，先在小参数集上调试，别一上来就跑全网格。
`experiment.yaml` 里的 `repeat` 是重复次数，调试时设 1。

### 随机性

**固定随机种子**，否则重跑结果不一致，论文里的数字对不上：

```python
rng = np.random.default_rng(20240101)   # 别用 np.random.rand()
```

### 数值稳定性

- 除以可能为 0 的量之前先判断
- 优化前先归一化，量纲差太大会不收敛
- 记录迭代次数和收敛标志，别把"没收敛"当"最优解"

---

## 七、诚实性要求

这几条是硬要求，不是建议：

1. **模拟数据必须标 `simulated`** —— 在「数据」页选来源时如实选
2. **拟合值要报告误差** —— 只给点估计不给区间，评委会问
3. **失败的结果不要藏** —— 模型预测不准就写清楚偏了多少，
   比假装准确安全得多
4. **别硬编码数字** —— 正文引用走宏，不要手抄

> 一个真实例子：某次峰值预测，模型说第 40 天，实际第 93 天。
> 这个失败被原样保留在报告里，没有调参掩盖。
> 建模比赛里，"知道自己的模型在哪儿不行"是加分项。

---

## 八、命令速查

```bash
# 跑实验
./core/mcm --dir ~/mcm/2026A exp run EXP-001

# 看会展开成几次试验（不真跑）
./core/mcm --dir ~/mcm/2026A exp trials EXP-001

# 看运行归档
./core/mcm --dir ~/mcm/2026A exp runs EXP-001

# 看结果原子（论文要引用的数字）
./core/mcm --dir ~/mcm/2026A result list

# 环境检查
./core/mcm doctor

# 部署自检
./core/mcm deploy
```

---

## 九、卡住了

```bash
./core/mcm report --out diag.txt
```

生成诊断报告：版本、系统、依赖、模板数、项目结构计数。
**不含论文正文**，只报数量。

先看三件事：版本对不对、模板数够不够（应该是 101）、
依赖齐不齐（没 pdflatex 只影响出 PDF，不影响跑实验）。

---

## 相关

- 全局操作流程 → [README](../README.md)
- 部署到别的机器 → [DEPLOY](DEPLOY.md)
- 论文手怎么用你产出的数字 → [writerread.md](writerread.md)
- 建模手怎么定义参数和模型 → [molderread.md](molderread.md)
