# 模板库

101 个模板，按"能直接用"的标准组织。每个模板都带 `observed_in` 和 `evidence`
—— 说清它在往届论文里的出现率，不是凭想象加的。

```bash
./core/mcm template list                # 列全部
./core/mcm template list --kind figure  # 只看图
./core/mcm template list -q 分布         # 搜（中英文都行）
./core/mcm template show fig.timeseries  # 看一个模板的完整说明
```

---

## 怎么找模板

模板一多，"我知道有这么个图但想不起叫什么"就是最常发生的事。
所以搜索支持**用自己的话**：

```bash
./core/mcm template list -q 分布      # -> fig.histogram_distribution
./core/mcm template list -q 热力      # -> fig.heatmap_matrix, fig.correlation_heatmap
./core/mcm template list -q 敏感性    # -> exp.sensitivity_oat, fig.sensitivity_line
./core/mcm template list -q 帕累托    # -> fig.pareto_frontier
```

面板的「生图工作台」页有同样的搜索框，输入即过滤。

中英对照表在 `core/mcmcore/templates.py` 的 `CN2EN`。常见的都能命中：
分布/热力/时间/趋势/箱线/小提琴/雷达/桑基/甘特/帕累托/曲面/瀑布/相图/
残差/ROC/累积/堆叠/地图/敏感性/蒙特卡洛。

---

## 语料告诉我们该先有什么

从 433 篇（155 篇 Outstanding）里挖出来的需求排序，模板库按这个顺序补：

| 图类型 | Outstanding 出现率 | 模板 |
|---|---|---|
| 时间序列/趋势 | **41.3%** | `fig.timeseries` |
| 流程/算法 | 37.4% | `fig.flowchart` |
| 分布/直方图 | **35.5%** | `fig.histogram_distribution` |
| 网络/图结构 | 32.3% | `fig.network_graph` |
| 对比/排序 | 30.3% | `fig.bar_comparison` |
| 模型结构 | 27.1% | `fig.model_structure` |
| 地理/空间 | 20.0% | `fig.map_choropleth` |
| 敏感性/扫描 | 18.7% | `fig.sensitivity_line` |
| 优化/解空间 | 17.4% | `fig.pareto_frontier` |
| 拟合/预测 | 14.2% | `fig.pred_vs_actual`, `fig.residual` |
| 三维 | 11.6% | `fig.surface_3d` |
| 热力/相关 | 7.1% | `fig.heatmap_matrix`, `fig.correlation_heatmap` |
| 收敛/迭代 | 5.2% | `fig.convergence` |
| 累积/生存 | 3.9% | `fig.cumulative_curve` |

模型侧的需求排序（同样是挖出来的）：图论/网络 45.2%、仿真/ABM 23.9%、
预测/回归 11.6%、优化/规划 9.0%、几何/物理 9.0%、评价 9.0%、排队 7.7%。

---

## 图模板（38）

### 数据关系
| 模板 | 什么时候用 |
|---|---|
| `fig.timeseries` | 量随时间演化。**最常用的一张图**。可叠观测序列做对照 |
| `fig.scatter_matrix` | 看多变量两两关系 |
| `fig.correlation_heatmap` | 看谁和谁一起动，**带正负号**（单色渐变分不清正负相关） |
| `fig.pred_vs_actual` | 拟合优度，带 y=x 参考线 |
| `fig.residual` | 残差诊断。**残差图里的系统性模式就是模型缺陷的指纹** |
| `fig.qq_plot` | 残差正态性。回归类题目的标配 |
| `fig.histogram_distribution` | 一个量的分布，标出均值/中位数 |
| `fig.box_violin` | 多组分布的形状对比（不只是中位数） |
| `fig.boxplot_grouped` | 分组箱线图，标注组内样本量 |
| `fig.errorbar_series` | 多次实验的均值±标准差。蒙特卡洛/交叉验证的结果图 |

### 模型与优化
| 模板 | 什么时候用 |
|---|---|
| `fig.sensitivity_line` | 单因子敏感性曲线 |
| `fig.surface_3d` | 目标值随两个参数变化 |
| `fig.heatmap_matrix` | 同上，二维形式；也用于相关矩阵 |
| `fig.pareto_frontier` | 两个冲突目标的权衡。**自动标出支配关系** |
| `fig.convergence` | 迭代收敛过程 |
| `fig.waterfall_contribution` | 把总量变化拆成各因素的贡献（增量蓝、减量红） |
| `fig.phase_portrait` | 动力学系统的相空间轨迹（ODE 类） |

### 结构与流程
| 模板 | 什么时候用 |
|---|---|
| `fig.flowchart` | 算法/方法流程。**输出可编辑的 .drawio** |
| `fig.model_structure` | 模型框架图、数据流 |
| `fig.network_graph` | 网络的节点-连边结构 |
| `fig.sankey_flow` | 流量在阶段间的分配（真贝塞尔带） |
| `fig.gantt_schedule` | 调度/排班方案 |
| `fig.stacked_area` | 总量构成随时间变化 |
| `fig.cumulative_curve` | 累积量、洛伦兹曲线 |

### 评价与分类
| 模板 | 什么时候用 |
|---|---|
| `fig.radar_compare` | 多方案多指标综合对比（**自动归一化**） |
| `fig.roc_curve` | 分类器判别能力，图例显示 AUC |
| `fig.bar_comparison` | 跨模型/跨方案的指标对比 |
| `fig.map_choropleth` | 地理分布 |

### 对照与诊断（后加的 10 个）
| 模板 | 什么时候用 |
|---|---|
| `fig.confidence_band` | 均值线 + 置信区间填充带。**预测/仿真的标准画法** |
| `fig.residual_hist_qq` | 残差诊断组合图：左看分布形状，右看是否偏离正态 |
| `fig.violin_split` | 两组分布左右分开的小提琴图，比箱线图信息更多 |
| `fig.dumbbell` | 两时点/两方案对比，连线一眼看出增减 |
| `fig.lollipop` | 排序后的火柴棒图，条目多时比柱状图清爽 |
| `fig.bump_chart` | 名次随时间变化，看谁在上升谁在掉队 |
| `fig.dual_axis` | 双纵轴：两个量纲不同的序列画在同一时间轴 |
| `fig.heatmap_annotated` | 带数值标注的混淆矩阵，每格写清数量 |
| `fig.model_metric_radar` | 多模型多指标归一化雷达对比 |
| `fig.grid_search_surface` | 网格搜索结果：左二维响应面，右单参数切片 |

---

## 模型模板（17）

模型模板**不含代码**，它是一份结构化清单：这类模型需要交代哪些字段、
评审会问什么。`defaults.checklist` 是精华部分。

| 家族 | 模板 | 关键清单项 |
|---|---|---|
| 动力学 | `model.ode_system` | 步长、收敛判据、初值 |
| 动力学 | `model.differential_discrete` | 稳定性条件、平衡点 |
| 网络 | `model.graph_network` | 节点/边的实际含义、边权来源、规模 |
| 优化 | `model.optimization_lp` | 目标、约束、解的唯一性 |
| 优化 | `model.mip_scheduling` | 变量定义域、big-M 取值、gap |
| 评价 | `model.evaluation_topsis` | 效益型/成本型、权重来源、CR 值 |
| 评价 | `model.evaluation_ahp` | 一致性检验 |
| 排队 | `model.queueing` | 到达/服务分布、ρ→1 的含义、稳态假设 |
| 仿真 | `model.simulation_abm` | 随机种子、重复次数 |
| 仿真 | `model.cellular_automata` | 邻域、边界条件、同步/异步 |
| 随机 | `model.markov_chain` | 行和为 1、不可约性、收敛时间 |
| 博弈 | `model.game_theory` | 均衡存在性、多均衡选哪个 |
| 预测 | `model.prediction_regression` | 交叉验证、过拟合检查 |
| 预测 | `model.regression_advanced` | 残差三件套、VIF、正则强度 |
| 预测 | `model.prediction_timeseries` | 平稳性、季节性 |
| 分类 | `model.classification` | 类别不平衡、评价指标选择 |
| 统计 | `model.statistical_inference` | 前提假设、效应量、多重比较校正 |

---

## 表模板（13）

| 模板 | 内容 |
|---|---|
| `tab.data_summary` | 每个数据集的来源、规模、跨度、局限 |
| `tab.assumption_register` | 每条假设 + 理由 + **在哪一节被检验** |
| `tab.parameter_settings` | 参数、取值、单位、**来源**（provenance） |
| `tab.notation_table` | 符号表（通常由 math/ 自动生成） |
| `tab.validation_metrics` | 模型的完整验证指标 |
| `tab.model_comparison` | 多模型多指标对比 |
| `tab.metric_comparison` | 逐格绑定到结果原子 |
| `tab.sensitivity_result` | 参数扫描 × 指标 |
| `tab.robustness_mean_std` | 多次运行的均值与离散度 |
| `tab.scenario_outcomes` | 各情景的方案与结果 |
| `tab.resource_allocation` | 资源在各接收方之间的分配 |
| `tab.convergence_report` | 分辨率/迭代增加时解的变化 |
| `tab.error_budget` | 不确定性按来源分解 |

---

## 论文模板（8）

### 五套题型骨架

不同题型，评审期待的结构不同。用同一套骨架会让论文显得答非所问。

```bash
./core/mcm paper scaffold --spine data_driven
```

| 骨架 | 适用 | 特有章节 |
|---|---|---|
| `general` | 不确定时 | 通用结构 |
| `data_driven` | C 题（数据挖掘、预测） | **Data Description and Preprocessing** |
| `physical` | A 题（机理、工程） | **Model Derivation**、**Numerical Scheme and Validation** |
| `policy` | B/D 题（运筹、政策） | **Solution and Scheme Design**、**Scenario Comparison** |
| `evaluation` | E 题（评价、可持续） | **Indicator System and Weighting** |

所有骨架都遵守语料里 100% 成立的先后序：引言→模型→敏感性→优缺点，
结论→参考文献。**都没有 Literature Review 节** —— 它在 415 篇里出现 0 次。

### 章节正文骨架

`paper.section_bodies` 给每节提供可直接填空的骨架：
哪里写什么、按什么顺序、哪里插图表、哪里引用结果数字。

**中文只在 `%` 注释里**，能排版出去的正文一律英文。
中文进 pdflatex 会直接编译失败 —— 这条踩过。

---

## 代码模板（16）

**可直接复制运行的 Python 骨架**，不是完整程序。每个 `snippet.py` 用内置
模拟数据就能跑通，改几处 `TODO` 换成你的数据即可。

```bash
python3 templates/code/kmeans_clustering/snippet.py
```

输出默认写到临时目录（`tempfile.mkdtemp()`），**不污染模板库**。
想留图就设环境变量：

```bash
MCM_CODE_OUT=./my_out python3 templates/code/arima_forecast/snippet.py
```

| 模板 | 解决什么 |
|---|---|
| `code.data_cleaning` | 去重、按列策略填补缺失、z 分数法识别异常值 |
| `code.descriptive_stats` | 描述性统计与正态性检验 |
| `code.correlation_vif` | 相关性分析与多重共线性（VIF） |
| `code.regression_diagnostics` | 回归建模与残差诊断 |
| `code.arima_forecast` | 时间序列分解与预测 |
| `code.ode_solve` | 常微分方程组求解 |
| `code.parameter_fitting` | 参数拟合（网格搜索 + Gauss-Newton 精化） |
| `code.monte_carlo_ci` | 蒙特卡洛模拟与置信区间 |
| `code.sensitivity_analysis` | 单因子与双因子敏感性分析 |
| `code.multiobjective_pareto` | 多目标优化与帕累托前沿 |
| `code.entropy_topsis` | 熵权法 + TOPSIS 综合评价 |
| `code.ahp_evaluation` | 层次分析法（含一致性检验 CR） |
| `code.cellular_automaton` | 元胞自动机 / 网格仿真 |
| `code.graph_shortest_path` | Dijkstra 与 Floyd 最短路（两者互验） |
| `code.kmeans_clustering` | K-means 聚类（肘部法选 K） |
| `code.queueing_metrics` | 排队论指标计算 |

### 这些骨架是核对过的，不是照着公式抄的

写模板时发现并修掉了几个**"看起来成功、其实错了"**的 bug：

- `parameter_fitting` 的 Gauss-Newton 漏了负号。后果极隐蔽：每步代价都变大 →
  阻尼逻辑一路拒绝 → 函数把初值原样返回，**"看起来收敛了其实一步没动"**，
  Bootstrap 置信区间退化成上下界相等。修后参数误差 1.3% / 3.0% / 1.6%。
- `regression_diagnostics` 的字典里 `p` 键写了两次，p 值被参数个数覆盖。
- `graph_shortest_path` 用 Dijkstra 与 Floyd 互验：A→H 都是 19.0，
  手工核对 2+3+5+3+6=19 一致。

这些是**代码模板最容易出的错**：公式抄对了但符号错了，
结果不报错、只是默默给一个错的数。所以模板的验收标准是
"结果要对得上独立算法或手算"，不是"能跑就行"。

## 参考文献模板

`paper.references` 不是一个图，是**一套引用工作流**。面板的「参考文献」页
配合它用：

**粘贴 BibTeX 导入** —— 从期刊页或 Google Scholar 复制一段贴进去就行，
一次可以贴多条。不用手填 key/title/authors 字段。

**自动核对**（这才是这一页的价值）：

| 检查 | 为什么要查 |
|---|---|
| 引了但没条目 | 编译出来是 `[?]`，而 LaTeX 只给一句 warning |
| 有条目但没引 | 语料里 **707/707** 条文献都被正文引用过，没引的是缺陷 |
| 条目字段不全 | 缺作者/年份的条目，评审无法核实 |

**AI 工具自动识别**：标题里出现 ChatGPT / GPT-4 / Claude / Gemini 等，
会自动标成 `ai_generated`，导出时带上 COMAP 要求的声明。
COMAP 明确规定 AI 工具**必须列进参考文献**，只在正文或致谢里提一句不算。

**导出 .bib**：存档或投别的期刊都能用。

### 几条来自语料的规则

- **不要设「文献综述」章节** —— 415 篇里一次都没出现过。相关工作写在引言里。
- **正文统一用 `\cite{key}`**，不要手写 `[1]`。增删条目后手写编号会全部错位。
- 数据集、年鉴、网站也要进参考文献，不能只在正文提一句。
- 网络资源写访问日期。

## 图上文字不会互相压住

38 个图模板全部经过**自动重叠检测**（`core/tests/test_no_text_overlap.py`）：
渲染后量每个文字的 bbox，两两比对，重叠超过 15% 就判失败。

**为什么要自动查**：文字重叠靠肉眼看单张图很容易漏。最典型的是
"多个系列的数值标注落在同一个像素上"—— 图能生成、不报错、
打开看也不觉得异常，就是三行数字叠在一起只剩一行能读。

雷达图最容易出这个问题：**分数接近 ≠ 屏幕位置接近**。两个指标
取值相近时顶点挨着，多个系列的对应顶点甚至完全重合。

修法是把避让做成共享工具 `mcmplot.spread_labels()`：画完量 bbox，
把重叠的按序号绕扇形散开。

> 这里踩过一个坑：**不能按"相对圆心的方向"推开**。三个标注重合时
> 方向完全相同，它们会一起移动、永远保持重叠 —— 我第一版就是这么
> 写的，结果把标注推到了画布外 400 点。所以改成按序号给不同方向。
>
> 另外测试还检查"标注有没有跑出画布"：被推出画布的标注在 PDF 里
> 是被裁掉的，同样属于"看起来正常、其实丢了内容"。

## 加自己的模板

图模板 = 一个目录 + 两个文件：

```
templates/figures/my_chart/
  template.yaml     # 声明输入、用途、语料依据
  render.py         # def render(data, meta) -> Figure
```

三条硬规矩（测试会查）：

1. **`render(data, meta)` 是唯一入口**，返回 Figure，**不要自己 savefig**
   —— 落盘由上层负责，模板自己写文件会绕过归档
2. **缺数据抛中文 `ValueError`**，绝不画空图。
   空图看起来像"成功了但没结果"，比报错难查得多
3. **中文一律过 `mcmplot.safe()`** —— 中文字体画不出 `²` 和 `−`，
   直接写会变豆腐块

最小可用例子：

```python
def render(data, meta=None):
    meta = meta or {}
    y = list(data.get("y") or [])
    if not y:
        raise ValueError("缺少必填输入 y：请提供要画成曲线的数值序列。")
    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 3.7))
    ax.plot(y, "-", lw=1.9, color="#1f4e79")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig
```

写完跑一遍自检：

```bash
python3 -m pytest core/tests/test_template_library.py -q
```

它会检查：模板能否加载、`required_inputs` 有没有写错名字、
代码有没有真的读声明的输入、空数据会不会抛中文错、
骨架能不能编译、正文里有没有混进中文。

---

## 两条设计约束

**模板只管画，不管存。** 模板返回 Figure，上层决定写到哪、记不记进
图记录。这样同一张图既能在预览里渲染，也能在正式生成时落盘，
两处走的是同一份代码。

**模板不绑数据。** 图的数据通过 `Figure.bindings` 绑定到结果原子，
不写在模板里。所以同一个模板能画任何实验的结果 ——
模板里出现具体数值就是设计错了。
