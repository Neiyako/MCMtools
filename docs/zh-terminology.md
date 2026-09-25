# 中文文案与术语表

本文件是 MCMtools 所有用户可见文字的**唯一用词依据**。改文案前先查这里，
新增术语后补进这里。没有这份表，同一个概念会出现好几种叫法，用户就要靠猜。

---

## 1. 总原则

1. **技术标识符永远保留英文原样。** `RES-0142`、`FIG_STALE`、`EXP-001`、
   `build`（阶段名）、`sensitivity_oat`（模板名）都是**数据**，不是文案。
   翻译它们会让用户无法把界面上的东西和 `project.yaml`、报错、文档对上。
2. **句子翻译，术语保留。** 界面写「这张图已过期」，不写「stale」；但提及机制时
   可以说「已标记为 stale」。
3. **不留半英半中的句子。** 「Running…」必须变成「正在运行…」，
   而不是「Running 中」。

---

## 2. 核心术语（保留英文）

这些词在中文句子里**直接用英文**，因为它们同时是代码里的字段名或枚举值，
翻译会导致界面和文件对不上：

| 保留英文 | 含义 | 举例 |
|---|---|---|
| `ResultAtom` | 论文里每个数字的唯一来源 | 「这个数字绑定到 3 个 ResultAtom」 |
| `stale` | 绑定的结果变了、产物还没重生成 | 「FIG-001 已过期（stale）」 |
| `blocker` | 阻塞项：有明确下一步动作的问题 | 「当前有 2 个 blocker」 |
| `run` | 一次实验执行 | 「3 个 run 全部成功」 |
| `footprint`/`atom_id` | 字段名 | 原样保留 |

## 3. 需要翻译的术语

这些是**概念**而非字段名，中文可读性明显更好：

| 英文 | 中文 | 说明 |
|---|---|---|
| experiment | 实验 | |
| model | 模型 | |
| figure / table | 图 / 表 | |
| section | 章节 | |
| page budget | 页数预算 | |
| audit | 审计 | |
| finding | 审计发现 | 指一条具体的检查结果 |
| severity: error / warning / info | 错误 / 警告 / 提示 | |
| verdict | 结论 | |
| submission gate | 提交门禁 | |
| regenerate | 重新生成 | 指图/表从当前结果重画 |
| sensitivity analysis | 敏感性分析 | |
| one-at-a-time (OAT) | 单因子轮换（OAT） | |
| held fixed | 固定不变 | |
| protocol | 实验协议 | |
| trial | 试验 | 协议展开后的一次具体执行 |
| provenance | 来源 | 参数/数字的出处 |
| assumptions | 假设 | |
| notation table | 符号表 | |
| summary sheet | 摘要页 | COMAP 第 1 页 |
| page-limit-exempt | 不计入页数 | 「Report on Use of AI」的性质 |
| competition mode | 竞赛模式 | |
| development mode | 开发模式 | |
| workspace / project | 项目 | |

## 4. 界面用语

| 场景 | 用这个 | 不要用 |
|---|---|---|
| 加载中 | 正在加载… | Loading… |
| 空状态 | 暂无数据集 | No datasets |
| 按钮：执行 | 运行 | Run / 执行 |
| 按钮：构建 | 生成 PDF | Build PDF |
| 按钮：重画 | 重新生成 | Regenerate |
| 按钮：查看 | 查看 LaTeX | Show LaTeX |
| 确认：可提交 | 可以提交 | READY TO SUBMIT |
| 确认：不可提交 | 请勿提交 | DO NOT SUBMIT |
| 计数 | 3 个错误 · 2 个警告 | 3 error(s) |

**量词**：用「个」而非「条」表示 finding 和 blocker（口语更自然）；
页数用「页」；图/表用「张」/「个」。

---

## 5. 标点与排版

- 中文句子用**全角**标点：，。：；！？
- 中英混排时，英文两侧留一个半角空格：「打开 PDF 文件」
- 省略号用 `…`，不用 `...`
- 数字与单位之间不加空格：「25 页」「3 个 run」
- 括号用全角（）包中文，半角 () 包纯英文内容

---

## 6. 报错文案的写法

一条好的报错必须包含**三件事**：出了什么问题、为什么、怎么解决。

```
✗  模型 M01 的参数 gamma 缺少来源。
   论文里的每个参数都要能追溯出处，否则审阅时无法解释这个数字。
   → 在 model.yaml 里给它加上 source 字段（literature / fitted / assumed）。
```

不要在报错里写「Error」「失败」了事 —— 用户已经知道出错了，他要的是下一步。
