# 模板库使用说明

模板库是 MCMtools 的核心资产：**比赛期间不需要 AI，靠的就是这些现成的模板。**
所有模板都在 `templates/` 下，纯文本、可读可改，不依赖任何专有格式。

---

## 1. 图模板（`templates/figures/`）

12 个模板，每个都自带**可执行的绘制代码**，不是只有说明。

| 模板 | 画什么 | 什么时候用 |
|---|---|---|
| `sensitivity_line` | 单参数扫描曲线 | 敏感性分析（86% 的论文都做） |
| `bar_comparison` | 分组柱状图 | 方案对比、模型对比 |
| `boxplot_grouped` | 分组箱线图 | 多次重复实验的分布 |
| `convergence` | 收敛曲线 | 迭代算法、优化过程 |
| `heatmap_matrix` | 热力图 | 双参数响应面 |
| `scatter_matrix` | 散点矩阵 | 变量相关性 |
| `pred_vs_actual` | 预测 vs 实测 | 模型拟合效果 |
| `residual` | 残差图 | 诊断模型假设 |
| `network_graph` | 网络图 | 关系结构、传播网络 |
| `map_choropleth` | 区域填色图 | 地理分布 |
| `flowchart` | 流程图（drawio） | 算法步骤、求解流程 |
| `model_structure` | 结构图（drawio） | 技术路线图 |

### 生成数据图

```python
import importlib.util

spec = importlib.util.spec_from_file_location(
    "myfig", "templates/figures/sensitivity_line/render.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fig = mod.render({"x": [0.1, 0.177, 0.25], "y": [119299, 172428, 198780]},
                 {"caption": "峰值人数随 beta 的变化"})
fig.savefig("out.pdf")
```

> **注意**：每个模板文件都叫 `render.py`。用普通的 `import render`
> 会让它们互相顶掉（第二次 import 拿到的是第一次的缓存），
> 必须用 `spec_from_file_location` 按路径加载。项目里的
> `FigureGenerator._load_template()` 已经处理了这件事。

### 生成 drawio 图

流程图和结构图输出的是**可编辑的 `.drawio` 文件**，不是位图 ——
答辩前一定会改措辞、挪方框，能改比好看重要。

```python
fig = mod.render_to_file({"nodes": [...], "edges": [...]}, out_dir="figures", name="flow")
# → figures/flow.drawio（可在 app.diagrams.net 打开编辑）
```

有装 drawio 命令行版时会顺带导出 PDF；没装也能用，源文件照样能打开。

### 在面板里用

「生图工作台」页：选模板 → 填数据 → 预览 → 导出。
预览是服务端渲染的真实 PDF，所见即论文里插进去的效果。

---

## 2. 中文字体（重要）

matplotlib 默认字体不含中文字形。用中文当轴标签**不会报错**，
只会在图上印出一排空心方框 —— 图照常生成、照常导出、照常排版，
等发现时已经晚了。所以每个模板都必须调用 `mcmplot.setup()`：

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot
mcmplot.setup()
```

`mcmplot` 还会处理另一个坑：**中文字体缺 `²` 和 `−`**。
`R²` 的上标在中文字体里没有字形，所以 `mcmplot.safe()` 会把它换成 `R^2`。
测试 `test_no_template_uses_unrenderable_glyphs` 会拦住新写的模板。

---

## 3. 论文模板（`templates/paper/`）

| 模板 | 作用 |
|---|---|
| `section_spine` | 章节**顺序**。来自 152 篇论文的两两先后关系，14 组关系 100% 成立 |
| `section_bodies` | 每节的**填空骨架** + 自查项 + 篇幅预算 |
| `comap_latex` | COMAP 官方 LaTeX 模板 |

### 骨架长什么样

```yaml
- kind: sensitivity
  budget_pages: 1.5
  body: |
    % 86% 的论文做敏感性分析。只变一个参数时**必须说明其他参数
    % 固定不变** —— 否则分析无效。
    我们采用单因子轮换法：固定 {{held_fixed}}，
    依次改变 {{varied}}，观察 {{metric}} 的变化。
  checklist:
  - 是否说明了其他参数保持不变
  - 是否有图或表支撑结论
```

`{{...}}` 是占位符。未填的占位符会被审计查出来（`SUMMARY_PLACEHOLDER`），
所以"忘了填"不会溜过去。

### 生成骨架

```bash
mcm paper scaffold          # 补空章节，不覆盖已写正文
```

或在面板「论文」页操作。**已有的正文永远不会被覆盖** —— 这是硬保证，
有测试盯着（`test_does_not_overwrite_existing_body`）。

### 篇幅预算

8 节共 11.5 页建议篇幅。语料显示 **72.1% 的 2022–2025 论文正好 25 页**，
所以动笔时就知道每节该写多长，不至于写到最后发现超页。

---

## 4. 语料依据

模板不是拍脑袋定的，每条都标注了 `observed_in` 和 `evidence`：

- Introduction 在 108/152 篇里排第一（71.1%）
- **Literature Review 在 415 篇里出现 0 次** —— 所以绝不模板化
- 83% 的论文讨论弱点
- 69% 的论文在正文里重复同一个精确数字
- 只有 37% 的图被正文交叉引用
- 74% 的嵌入图片宽不到 500px

在面板里选模板时会显示对应的语料依据。

---

## 5. 加自己的模板

```
templates/figures/my_chart/
    template.yaml    元数据：template_id、inputs、purpose、evidence
    render.py        def render(data, meta) -> matplotlib Figure
```

`template.yaml` 声明了输入名之后，面板会自动把它列进工作台，
`FigureGenerator` 也能自动发现它 —— **不需要改核心代码**。
模板注册表每次调用都重新读盘，新模板立刻可见。
