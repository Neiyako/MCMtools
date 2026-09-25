# MCMtools 工作台使用指南

这份指南是从**真实走一遍 2023 MCM C 题（Wordle）**的过程里总结出来的。
不是功能清单，是一条能照着做的路径。全程约 3 小时。

产出：16 页论文 · 6 张矢量图 · 2 个实验 · 54 个结果原子 · 0 个审计错误。

---

## 0. 开工前 5 分钟

```bash
cd 项目目录
./core/mcm doctor          # 环境自检，缺什么会直接给安装命令
./start                    # 启动面板，浏览器自动打开
```

> **不要把项目放在桌面 / 文稿 / 下载**。macOS 的 TCC 会拦住从这些目录
> 启动的进程读文件，面板会白屏或报 Operation not permitted。
> 放在用户主目录下的普通文件夹里。

面板左侧是流程顺序，**照着从上往下走就行**：总览 → 数据 → 数学内容 →
参数 → 实验 → 运行记录 → 生图工作台 → 论文 → 审计。

---

## 1. 先看往年获奖论文（别跳过这步）

这一步决定了后面所有取舍。本地语料库有 433 篇论文，其中 155 篇 Outstanding。

```bash
python3 -c "
import json, collections, statistics as st
rows=[json.loads(l) for l in open('.analysis/corpus_v3.jsonl') if l.strip()]
out=[r for r in rows if r.get('ok') and r.get('award')=='Outstanding']
oth=[r for r in rows if r.get('ok') and r.get('award') not in ('Outstanding',None)]
for k,name in [('n_figures','图数'),('total_vector_paths','矢量图'),('n_eq_numbered','编号公式'),('pages','页数')]:
    f=lambda rs: st.median([r[k] for r in rs if isinstance(r.get(k),(int,float))] or [0])
    print(f'{name}: Outstanding {f(out):.0f} vs 其他 {f(oth):.0f}')
"
```

**三条最该记住的结论**：

| 发现 | 对你意味着什么 |
|---|---|
| Outstanding 论文图数是其他的 **1.7 倍**（10 vs 6） | 图要多画。一张图抵三段话 |
| Outstanding 论文矢量图是其他的 **4.62 倍**（217 vs 47） | 别贴截图。用生图工作台出 PDF |
| Outstanding 论文**100% 的图在正文被引用** | 每张图都要有 `\ref{}`。工具会查 |

还有一条反直觉的：**"Literature Review" 在 415 篇里出现 0 次**。
所以模板里没有这一节 —— 不要自己加。相关工作合并进引言。

---

## 2. 建立项目

```bash
./core/mcm init --project-id mcm2023-C
```

然后打开面板，在「总览」页确认阶段设为 `build`。

**项目区各自管什么**（这个划分决定了你会不会找不到东西）：

```
math/math.yaml       符号、公式、假设、目标函数
params/parameters.yaml   参数及其来源
experiments/         实验协议：跑什么、扫哪个参数
code/                建模代码（人写）
runs/                每次执行的归档（机器写，不要手改）
figures/             生成的图
paper/               论文正文
build/               编译产物（可再生）
```

---

## 3. 数据

把数据放到 `data/DS-001/raw/`，然后在「数据」页查看登记情况。

> **当前限制**：面板和 CLI 都没有"注册新数据集"的入口，
> 数据集只能读不能写。要登记得写几行脚本调 `store.save_dataset(...)`。
> 这是已知缺口。

**这一步真正要做的事是看清数据**：画个时序图，算几个基本统计量，
问自己三个问题：

1. 数据是单调的吗？（不是 → 排除纯增长模型）
2. 衰减快还是慢？（慢 → 必须有留存机制）
3. 会归零吗？（不归零 → 排除标准 SIR）

我在 Wordle 数据上得到的答案直接决定了模型结构。**这一步省不得** ——
先选模型再找数据的论文，评审一眼能看出来。

---

## 4. 数学内容（数学内容页）

在「数学内容」页登记符号、公式、假设。三个要点：

**符号表会自动生成进论文**，所以释义要写成论文里能直接用的样子
（英文）。写中文会导致 pdflatex 编译失败。

**审计会查两件事**：
- 同一个符号两种含义 → **错误**（一篇论文只有一张符号表）
- 公式编号重复 → **错误**

**每条假设必须给理由**。这是评审最爱挑的地方。写"假设参数恒定"是没写完，
要写"假设参数恒定 —— 这是刻意的简化，敏感性分析会测它的代价，
残差图会暴露它留下的痕迹"。

---

## 5. 参数（参数页）

每个参数都要有**来源**：

| 来源 | 什么时候用 |
|---|---|
| `literature` | 从文献抄的，要写清哪篇 |
| `dataset` | 从数据直接算的 |
| `fitted` | 拟合出来的，要写清哪个实验 |
| `assumed` | 拍的，要说明为什么可以拍 |

**没来源的参数审计会警告，`--strict` 下直接阻塞提交**。
这条检查是有依据的：105/237 篇现代论文会标注参数来源。

> **一个真实的坑**：实验的 `held_fixed` 列表里的参数，
> 如果在参数区找不到，会以 `None` 传给你的脚本，
> 报 `TypeError: float() argument must be ... not 'NoneType'`。
> 先填参数区，再跑敏感性实验。

---

## 6. 写代码（`code/`）

**入口函数的签名**（这个约定不直观，但必须遵守）：

```python
def run(params_in=None, **kwargs):
    p = dict(params_in or {})
    # 运行器把整份参数表作为**一个字典**传进来，不是散参数
    ...
    return {"atoms": [...], "artifacts": [...]}
```

**每个结果原子的格式**：

```python
{"name": "r2", "value": 0.8202, "unit": "/", "format": "%.4f",
 "metric_def": "预测序列对观测序列的决定系数",
 "macro_alias": "r_squared"}      # 短宏名，只用字母
```

`metric_def` 必须写 —— 没写的话论文里没人说得清这个数是什么。

`macro_alias` 决定正文里怎么写：有别名写 `\numRSquared{}`，
没有就只得写 `\numRESEXPZeroZeroOneRTwoZeroZeroOne{}`。

> **`\num` 这类宏在 numpy 标量上会炸**：`np.mean()` 返回 `np.float64`，
> 归档写 YAML 时不认。工具已经修了，但自己写脚本时
> 用 `float(...)` 包一下更省事。

---

## 7. 注册并运行实验

实验目前要手写 `experiments/EXP-001/experiment.yaml`（没有 `mcm exp add`）。
两个必须有的字段：

```yaml
id: EXP-002
kind: sensitivity_oat          # 单因子敏感性
entrypoint: code/pcql.py:run
varied:
  - name: beta
    values: [0.20, 0.25, 0.31, 0.38, 0.45]
held_fixed: [gamma, lambda, phi]    # 只变一个参数时必须写清固定了哪些
```

```bash
./core/mcm exp trials EXP-002    # 先看会展开成几次
./core/mcm exp run EXP-002       # 跑
./core/mcm exp runs EXP-002      # 看归档
```

**归档里会留下什么**：参数、产出文件、代码 SHA-256、失败时的完整 traceback。
跑失败的那次也会留档 —— 这正是你要的，不是垃圾。

> **只变一个参数时，"其他参数固定不变"必须写在论文里**。
> 审计有硬性检查。不写的话敏感性分析在方法上就是无效的。

---

## 8. 生图工作台（重点）

这是这个工具最省时间的部分。流程：**选模板 → 填数据 → 预览 → 导出**。

面板「生图工作台」页：

1. **选模板**。12 个模板，每个都显示用途和语料依据。
2. **预览**。预览是服务端渲染的**真实 PDF**，所见即论文里插进去的效果。
   不满意就改数据重来，不用先绑进论文再看。
3. **导出**。数据图出 PDF；流程图/结构图出**可编辑的 `.drawio`**。

### 绑数据到图（两种方式）

**标量绑定** —— 图的内容是几个数（敏感性曲线上的点）：

```python
Figure(id="FIG-001", template_id="fig.sensitivity_line",
       bindings=[Binding(atom_id="RES-EXP002-BETA-003", role="x"),
                 Binding(atom_id="RES-EXP002-PEAK-DAY-001", role="y"), ...])
```

x 轴的值不用单独绑 —— 工具会从每个 y 原子的 `condition` 里解析出来。

**序列绑定** —— 图的内容是一整条曲线（400 天的观测 vs 预测）：

```python
Binding(atom_id="SER-actual", role="actual",
        source="artifact", artifact_path="trajectory.csv", column="observed")
```

**结构图** 没有数据可绑，用字面绑定：

```python
Binding(atom_id="LIT-nodes", role="nodes", source="literal",
        value=[{"id": "n1", "label": "读取数据", "kind": "input"}, ...])
```

### 三个防呆（都会给中文原因）

- **actual 和 predicted 绑到同一批数** → 拒绝。否则会画出一条完美对角线，
  标着 R²=1、RMSE=0 —— 图看着正常，结论全错。这种错最危险。
- **流程图为空** → 报"缺少必填输入 nodes"。
- **数据长度不一致** → 报"x 有 2 个点，y 有 3 个点，数量必须一致"。

### 图引用了才不会被标警告

写完论文后每张图都要有 `\ref{}`。审计会扫正文，
查不到引用就报 `ARTIFACT_NOT_CITED`。这条警告不是在挑刺：
**Outstanding 论文 100% 的图都被引用过**。

---

## 9. 写论文

```bash
./core/mcm paper scaffold     # 补填空骨架，绝不覆盖已写正文
```

然后在面板「论文」页编辑各节。骨架里 `{{...}}` 是占位符，填完审计才干净。

### 数字绝不能手写

正文里的数字写成宏引用：

| 情况 | 怎么写 |
|---|---|
| 实验结果 | `\numRSquared{}` |
| 结果之间的比较 | 也用宏，两个宏相减不行就写成文字 |
| 日期、页数、阈值 | `\lit{2022}`、`\lit{25}`、`\lit{1}` |

`\lit{}` 是逃生口，标记"这个数字换次实验也不会变"。
**漏标会被警告，`--strict` 下阻塞提交**。

这条不是为了好看。Wordle 那次我把拟合值写进正文，
后来重新拟合参数变了，正文差点留着旧数字。宏引用让这件事不可能发生。

### 篇幅

模板给的建议篇幅合计 11.5 页（上限 25 页）。
**没写满不是错误**，审计会提示但不会阻塞 —— 语料显示
72.1% 的 2022–2025 论文正好 25 页，那是上限不是目标。

---

## 10. 编译与审计

```bash
./core/mcm paper build        # 编译 PDF
./core/mcm validate           # 审计
./core/mcm validate --strict  # 提交门禁：阻塞性警告也算不过
```

审计分三级：

- **错误**：必须修。摘要占位、符号重定义、公式重号、悬空引用
- **警告**：该修。图未引用、参数无来源、数字未绑定
- **提示**：看看就好

`--strict` 只把这几条升级为阻塞：图/表过期、产物文件缺失、
数字未绑定、图表未引用、参数无来源、符号重定义。

### 编译失败怎么查

报错信息有时指向的不是真原因。按这个顺序排：

1. 看 `build/main.log` 里**第一条** `!` 开头的错误，不是最后一条
2. `Undefined control sequence` → 十有八九是正文里留了 `\lit{}`
   或写了个不存在的宏名
3. `reading PDF image failed` → 图不是真 PDF（可能是 drawio 的 XML）
4. `Unicode character not set up` → 有中文进了 pdflatex 能到的地方

---

## 附：这次实测暴露的工具链缺口

走完整流程才发现的，记录在此避免重复踩：

| 缺口 | 影响 | 绕过办法 |
|---|---|---|
| 没有 `mcm data add` | 数据集只能读不能写 | 写脚本调 `store.save_dataset` |
| 没有 `mcm exp add` | 实验协议要手写 YAML | 照 `experiments/EXP-*/experiment.yaml` 抄 |
| 中文字符串不能进 pdflatex | 符号表释义写中文会编译失败 | 释义写英文；或改用 xelatex |
| drawio 命令行非必需但推荐 | 没有它时流程图退化成示意图 | 装 drawio desktop，或用 .drawio 自己导出 |
